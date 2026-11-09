"""Step 9 observation-only verification of bounded candidate simulation."""

from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
import platform
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd
import torch

from final_model_adapter import sha256

from .candidate_inputs import (
    DEFAULT_CONSUMPTION_CONFIGURATION, create_decision_snapshot,
    load_consumption_configuration,
)
from .candidate_search import (
    DEFAULT_SEARCH_CONFIGURATION, generate_bolus_candidates,
    load_search_configuration, simulate_bolus_candidates,
)
from .checkpoint import load_frozen_gru
from .configuration import FROZEN_CHECKPOINT_SHA256, PREDICTION_HORIZON_STEPS
from .data import read_optimization_data
from .episodes import ALLOWED_SPLITS, EXPECTED_SOURCE_HASHES, build_episode_definitions, initialize_episode
from .events import (
    DEFAULT_TRIGGER_CONFIGURATION, acknowledge_evaluation, create_detector_state,
    detect_evaluation_event, load_trigger_configuration,
)
from .history import complete_interval, current_glucose_mg_dl
from .parameter_updates import RefreshConfiguration, refresh_parameters_if_due
from .physiology import PARAMETER_NAMES, STATE_NAMES
from .verify_history_updates import select_diagnostic_episodes, verify_arm_refresh_schedule


RELEVANT_SOURCE_FILES = (
    "final_model_adapter.py", "optimize.py", "test.py", "bolus_optimization/configuration.py",
    "bolus_optimization/checkpoint.py", "bolus_optimization/data.py",
    "bolus_optimization/physiology.py", "bolus_optimization/episodes.py",
    "bolus_optimization/history.py", "bolus_optimization/parameter_updates.py",
    "bolus_optimization/verify_history_updates.py", "bolus_optimization/events.py",
    "bolus_optimization/candidate_inputs.py", "bolus_optimization/candidate_search.py",
    "bolus_optimization/verify_candidate_search.py",
)


def _versions():
    result = {"python": platform.python_version(), "platform": platform.platform()}
    for name in ("numpy", "pandas", "pyarrow", "torch"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = "unavailable"
    return result


def _capture_arm(arm):
    return {
        "state": arm.physiological_state.clone(), "parameters": arm.parameters.clone(),
        "timestamp": arm.current_timestamp, "estimation": arm.parameter_estimation_timestamp,
        "history": arm.history.clone(), "ledger": copy.deepcopy(arm.meal_ledger),
        "pending": arm.detector_state.pending_event_id,
        "deliveries": copy.deepcopy(arm.detector_state.deliveries),
        "refreshes": copy.deepcopy(arm.refresh_log),
    }


def _arm_unchanged(arm, before):
    return bool(
        torch.equal(arm.physiological_state, before["state"])
        and torch.equal(arm.parameters, before["parameters"])
        and arm.current_timestamp == before["timestamp"]
        and arm.parameter_estimation_timestamp == before["estimation"]
        and arm.history.completed_timestamps == before["history"].completed_timestamps
        and all(torch.equal(getattr(arm.history, name), getattr(before["history"], name)) for name in (
            "completed_glucose_mg_dl", "completed_basal_u_per_hour", "completed_bolus_u",
            "completed_announced_carbs_g", "completed_consumed_carbs_g",
        ))
        and arm.meal_ledger == before["ledger"]
        and arm.detector_state.pending_event_id == before["pending"]
        and arm.detector_state.deliveries == before["deliveries"]
        and arm.refresh_log == before["refreshes"]
    )


def _search_event_row(definition, result):
    return {
        "evaluation_event_id": result.evaluation_event_id,
        "episode_id": result.episode_id, "dataset": definition.dataset,
        "patient_id": result.patient_id, "split": definition.split,
        "arm": result.arm_name, "decision_timestamp": result.decision_timestamp,
        "parameter_estimation_timestamp": result.parameter_estimation_timestamp,
        "search_configuration_hash": result.search_configuration_hash,
        "event_status": result.event_status,
        "expected_candidate_count": result.expected_candidate_count,
        "generated_candidate_count": result.generated_candidate_count,
        "simulated_candidate_count": result.simulated_candidate_count,
        "valid_candidate_count": result.valid_candidate_count,
        "failed_candidate_count": result.failed_candidate_count,
        "outstanding_carbs_g": result.candidate_inputs.outstanding_carbs_g,
        "consumption_profile_name": result.candidate_inputs.consumption_profile_name,
        "basal_source": result.candidate_inputs.basal_source,
        "score": result.score, "score_status": result.score_status,
        "runtime_seconds": result.runtime_seconds,
    }


def _candidate_row(definition, search, candidate):
    row = {
        "evaluation_event_id": search.evaluation_event_id,
        "episode_id": search.episode_id, "dataset": definition.dataset,
        "patient_id": search.patient_id, "split": definition.split,
        "arm": search.arm_name, "decision_timestamp": search.decision_timestamp,
        "candidate_index": candidate.candidate_index,
        "candidate_id": candidate.candidate_id, "dose_u": candidate.dose_u,
        "simulation_status": candidate.simulation_status,
        "failure_reason": candidate.failure_reason,
        "first_failing_interval": candidate.first_failing_interval,
        "first_failing_substep": candidate.first_failing_substep,
        "available_prediction_count": candidate.available_prediction_count,
        "roundoff_corrections": candidate.roundoff_corrections,
        "trajectory_min_mg_dl": candidate.trajectory_min_mg_dl,
        "trajectory_max_mg_dl": candidate.trajectory_max_mg_dl,
        "endpoint_glucose_mg_dl": candidate.endpoint_glucose_mg_dl,
        "score": candidate.score, "score_status": candidate.score_status,
    }
    row.update({f"final_{name}": float(value) for name, value in zip(STATE_NAMES, candidate.final_state)})
    return row


def _prediction_rows(definition, search, candidate):
    return [{
        "evaluation_event_id": search.evaluation_event_id,
        "episode_id": search.episode_id, "dataset": definition.dataset,
        "patient_id": search.patient_id, "split": definition.split,
        "arm": search.arm_name, "candidate_index": candidate.candidate_index,
        "candidate_id": candidate.candidate_id, "dose_u": candidate.dose_u,
        "prediction_index": index, "prediction_timestamp": timestamp,
        "horizon_minutes": (index + 1) * 5,
        "predicted_glucose_mg_dl": float(candidate.predicted_glucose_mg_dl[index]),
        "simulation_status": candidate.simulation_status,
    } for index, timestamp in enumerate(candidate.prediction_timestamps)]


def _results_equal(first, second):
    return bool(
        len(first.candidates) == len(second.candidates)
        and all(
            left.candidate_id == right.candidate_id
            and left.dose_u == right.dose_u
            and left.simulation_status == right.simulation_status
            and torch.allclose(
                left.predicted_glucose_mg_dl, right.predicted_glucose_mg_dl,
                rtol=0.0, atol=0.0, equal_nan=True,
            )
            and torch.allclose(left.final_state, right.final_state, rtol=0.0, atol=0.0, equal_nan=True)
            for left, right in zip(first.candidates, second.candidates)
        )
    )


def run_candidate_search_diagnostic(
    dataset_path: str | Path,
    checkpoint_path: str | Path,
    output_directory: str | Path,
    *,
    trigger_configuration_path: str | Path = DEFAULT_TRIGGER_CONFIGURATION,
    consumption_configuration_path: str | Path = DEFAULT_CONSUMPTION_CONFIGURATION,
    search_configuration_path: str | Path = DEFAULT_SEARCH_CONFIGURATION,
    episodes_per_patient: int = 1,
    refresh_minutes: int = 120,
    weight_kg: float = 70.0,
    substeps: int = 5,
):
    started = time.perf_counter()
    dataset_path, checkpoint_path, out = Path(dataset_path), Path(checkpoint_path), Path(output_directory)
    out.mkdir(parents=True, exist_ok=True)
    trigger, trigger_hash = load_trigger_configuration(trigger_configuration_path)
    consumption, consumption_hash = load_consumption_configuration(consumption_configuration_path)
    search_configuration, search_hash = load_search_configuration(search_configuration_path)
    expected_grid = generate_bolus_candidates(search_configuration)
    single_batch_configuration = replace(search_configuration, candidate_batch_size=1)
    refresh = RefreshConfiguration(refresh_minutes)
    data, patient_splits, loader_audit = read_optimization_data(dataset_path)
    frozen = load_frozen_gru(checkpoint_path, expected_sha256=FROZEN_CHECKPOINT_SHA256)
    if patient_splits != frozen.checkpoint["patient_splits"]:
        raise ValueError("Patient splits differ from the frozen checkpoint")
    selected = select_diagnostic_episodes(build_episode_definitions(data), episodes_per_patient)
    groups = {
        (str(dataset), str(patient)): group.sort_values("timestamp").reset_index(drop=True)
        for (dataset, patient), group in data[data["split"].isin(ALLOWED_SPLITS)].groupby(
            ["dataset", "patient_id"], sort=False
        )
    }
    episode_rows, event_rows, candidate_rows, prediction_rows = [], [], [], []
    candidate_failure_rows, verification_rows = [], []
    attempted_arms = completed_arms = lifecycle_failures = ongoing_failures = 0
    event_construction_failures = paired_checks = paired_failures = 0
    batch_checks = batch_failures = 0
    schedule_checks = []
    for definition in selected:
        episode = initialize_episode(
            groups[(definition.dataset, definition.patient_id)], definition, frozen,
            weight_kg=weight_kg, substeps=substeps,
        )
        if episode.initialization_status != "initialized":
            episode_rows.append({
                "episode_id": definition.episode_id, "dataset": definition.dataset,
                "patient_id": definition.patient_id, "split": definition.split,
                "arm": "paired", "start_timestamp": definition.start_timestamp,
                "end_timestamp": definition.end_timestamp, "status": "failed_initialization",
                "failure_reason": episode.failure.reason if episode.failure else "unknown",
            })
            ongoing_failures += 1
            continue
        arms = (episode.baseline_arm, episode.optimized_arm)
        for arm in arms:
            arm.detector_state = create_detector_state(arm, definition)
        attempted_arms += 2
        for _ in range(288):
            if not all(arm.status == "active" for arm in arms):
                break
            current = (
                episode.environment.reveal(episode.baseline_arm),
                episode.environment.reveal(episode.optimized_arm),
            )
            boundary_detection = []
            boundary_searches = []
            for arm, current_events in zip(arms, current):
                search = None
                try:
                    current_glucose_mg_dl(arm, weight_kg=weight_kg)
                    refresh_parameters_if_due(arm, frozen, current_events, refresh)
                    detection = detect_evaluation_event(
                        arm, current_events, trigger, arm.detector_state, weight_kg=weight_kg
                    )
                    boundary_detection.append(detection)
                    if detection.event is not None:
                        before = _capture_arm(arm)
                        try:
                            snapshot = create_decision_snapshot(
                                arm, current_events, detection.event, arm.detector_state
                            )
                            search = simulate_bolus_candidates(
                                snapshot, search_configuration, consumption,
                                weight_kg=weight_kg, substeps=substeps,
                                search_configuration_hash=search_hash,
                            )
                            individual = simulate_bolus_candidates(
                                snapshot, single_batch_configuration, consumption,
                                weight_kg=weight_kg, substeps=substeps,
                                search_configuration_hash=search_hash,
                            )
                            batch_checks += 1
                            batch_agrees = _results_equal(search, individual)
                            batch_failures += int(not batch_agrees)
                            event_rows.append(_search_event_row(definition, search))
                            for candidate in search.candidates:
                                candidate_rows.append(_candidate_row(definition, search, candidate))
                                prediction_rows.extend(_prediction_rows(definition, search, candidate))
                                if candidate.simulation_status == "simulation_failed":
                                    candidate_failure_rows.append({
                                        "evaluation_event_id": search.evaluation_event_id,
                                        "episode_id": search.episode_id,
                                        "patient_id": search.patient_id, "arm": search.arm_name,
                                        "candidate_index": candidate.candidate_index,
                                        "candidate_id": candidate.candidate_id,
                                        "dose_u": candidate.dose_u,
                                        "failure_reason": candidate.failure_reason,
                                        "first_failing_interval": candidate.first_failing_interval,
                                        "first_failing_substep": candidate.first_failing_substep,
                                        "available_prediction_count": candidate.available_prediction_count,
                                    })
                            inventory = len(search.candidates) == len(expected_grid)
                            complete_outputs = all(len(x.predicted_glucose_mg_dl) == 48 for x in search.candidates)
                            score_absent = search.score is None and all(x.score is None for x in search.candidates)
                            no_mutation = _arm_unchanged(arm, before)
                            verification_rows.append({
                                "evaluation_event_id": search.evaluation_event_id,
                                "episode_id": search.episode_id, "patient_id": search.patient_id,
                                "arm": search.arm_name, "decision_timestamp": search.decision_timestamp,
                                "candidate_inventory_pass": inventory,
                                "candidate_order_pass": [x.candidate_id for x in search.candidates]
                                == [x.candidate_id for x in expected_grid],
                                "trajectory_shape_pass": complete_outputs,
                                "batch_individual_agreement_pass": batch_agrees,
                                "search_no_mutation_pass": no_mutation,
                                "scores_null_pass": score_absent,
                                "pending_event_preserved_pass": arm.detector_state.pending_event_id
                                == detection.event.event_id,
                                "no_search_delivery_pass": arm.detector_state.deliveries == before["deliveries"],
                            })
                        except Exception as error:
                            event_construction_failures += 1
                            event_rows.append({
                                "evaluation_event_id": detection.event.event_id,
                                "episode_id": definition.episode_id, "dataset": definition.dataset,
                                "patient_id": definition.patient_id, "split": definition.split,
                                "arm": arm.arm_name, "decision_timestamp": arm.current_timestamp,
                                "event_status": "event_construction_failed",
                                "failure_reason": f"{type(error).__name__}:{error}",
                            })
                            raise
                        acknowledge_evaluation(
                            arm.detector_state, detection.event.event_id,
                            status="completed", outcome="diagnostic_only_no_selection_or_delivery",
                            acknowledgement_timestamp=arm.current_timestamp,
                        )
                    boundary_searches.append(search)
                    completion = complete_interval(
                        arm, current_events, current[0].recorded_bolus_u,
                        weight_kg=weight_kg, substeps=substeps,
                    )
                    if not completion.success:
                        ongoing_failures += 1
                        raise RuntimeError(completion.failure_reason)
                except Exception as error:
                    arm.status = "failed_step9_diagnostic"
                    arm.failure_reason = f"{type(error).__name__}:{error}"
            if len(boundary_detection) == 2:
                paired_checks += 1
                paired_ok = bool(
                    boundary_detection[0].evaluation_eligible == boundary_detection[1].evaluation_eligible
                    and boundary_detection[0].trigger_reasons == boundary_detection[1].trigger_reasons
                    and boundary_detection[0].suppression_reasons == boundary_detection[1].suppression_reasons
                )
                if len(boundary_searches) == 2 and all(item is not None for item in boundary_searches):
                    paired_ok = paired_ok and _results_equal(boundary_searches[0], boundary_searches[1])
                paired_failures += int(not paired_ok)
        for arm in arms:
            completed = arm.status == "active" and arm.current_timestamp == definition.end_timestamp
            completed_arms += int(completed)
            lifecycle_failures += int(arm.detector_state.pending_event_id is not None)
            schedule_checks.append(verify_arm_refresh_schedule(arm, refresh, definition.end_timestamp))
            episode_rows.append({
                "episode_id": definition.episode_id, "dataset": definition.dataset,
                "patient_id": definition.patient_id, "split": definition.split,
                "arm": arm.arm_name, "start_timestamp": definition.start_timestamp,
                "end_timestamp": definition.end_timestamp,
                "status": "completed" if completed else arm.status,
                "failure_reason": arm.failure_reason,
            })

    events = pd.DataFrame(event_rows)
    candidates = pd.DataFrame(candidate_rows)
    predictions = pd.DataFrame(prediction_rows)
    failure_columns = [
        "evaluation_event_id", "episode_id", "patient_id", "arm", "candidate_index",
        "candidate_id", "dose_u", "failure_reason", "first_failing_interval",
        "first_failing_substep", "available_prediction_count",
    ]
    candidate_failures = pd.DataFrame(candidate_failure_rows, columns=failure_columns)
    checks = pd.DataFrame(verification_rows)
    pd.DataFrame(episode_rows).to_csv(out / "evaluated_episodes.csv", index=False)
    events.to_parquet(out / "search_events.parquet", index=False)
    candidates.to_parquet(out / "candidate_results.parquet", index=False)
    predictions.to_parquet(out / "candidate_predictions.parquet", index=False)
    candidate_failures.to_csv(out / "candidate_failures.csv", index=False)
    checks.to_csv(out / "verification_checks.csv", index=False)

    source_hashes = {path: sha256(path) for path in RELEVANT_SOURCE_FILES}
    dataset_hash = sha256(dataset_path)
    checkpoint_dataset_hash = frozen.checkpoint.get("data_sha256")
    configuration = {
        "step": 9, "scope": "bounded candidate generation and numerical simulation only",
        "dataset": str(dataset_path.resolve()), "dataset_sha256": dataset_hash,
        "checkpoint": str(checkpoint_path.resolve()), "checkpoint_sha256": frozen.checkpoint_sha256,
        "checkpoint_dataset_sha256": checkpoint_dataset_hash,
        "dataset_hash_discrepancy": {
            "status": "unresolved",
            "current_dataset_matches_checkpoint_record": dataset_hash == checkpoint_dataset_hash,
        },
        "splits": list(ALLOWED_SPLITS), "testing_patients_used": False,
        "search_configuration": {
            "path": str(Path(search_configuration_path).resolve()), "sha256": search_hash,
            **search_configuration.__dict__,
            "grid_rule": "zero plus integer increment ticks; stop below a nondivisible maximum",
            "clinical_status": "experimental search settings; not patient-specific safe limits",
        },
        "generated_grid": [{"candidate_id": x.candidate_id, "dose_u": x.bolus_u} for x in expected_grid],
        "consumption_configuration_sha256": consumption_hash,
        "trigger_configuration_sha256": trigger_hash,
        "horizon_intervals": 48, "horizon_minutes": 240,
        "weight_kg": weight_kg, "substeps": substeps,
        "action_source": "externally supplied recorded action, identical in both arms",
        "candidate_trajectories_influenced_actions": False,
        "scoring": "not_implemented_step10", "selection": "not_implemented_step10",
        "future_data_contract": "No future dataset CGM, basal, bolus, meal or consumption is consulted by search.",
        "source_hashes": source_hashes,
        "expected_preserved_source_hashes": EXPECTED_SOURCE_HASHES,
        "loader_audit": loader_audit, "software_versions": _versions(),
    }
    (out / "configuration.json").write_text(json.dumps(configuration, indent=2, default=str) + "\n")

    check_columns = [name for name in checks.columns if name.endswith("_pass")]
    verification_failures = int((~checks[check_columns].all(axis=1)).sum()) if len(checks) else len(events)
    schedule_pass = bool(
        len(schedule_checks) == attempted_arms
        and all(item["ordered_exact_match"] for item in schedule_checks)
    )
    preservation_pass = bool(
        frozen.checkpoint_sha256 == FROZEN_CHECKPOINT_SHA256
        and all(source_hashes[path] == expected for path, expected in EXPECTED_SOURCE_HASHES.items())
    )
    expected_total = len(events) * len(expected_grid)
    inventory_pass = len(candidates) == expected_total and len(predictions) == expected_total * 48
    implementation_pass = bool(
        verification_failures == 0 and event_construction_failures == 0
        and batch_failures == 0 and paired_failures == 0 and lifecycle_failures == 0
        and schedule_pass and preservation_pass and inventory_pass
    )
    simulation_completion_pass = bool(completed_arms == attempted_arms and ongoing_failures == 0)
    valid_count = int((candidates["simulation_status"] == "simulation_valid").sum()) if len(candidates) else 0
    failed_count = int((candidates["simulation_status"] == "simulation_failed").sum()) if len(candidates) else 0
    complete_trajectories = int((candidates["available_prediction_count"] == 48).sum()) if len(candidates) else 0
    partial_trajectories = len(candidates) - complete_trajectories
    all_failed_events = int((events.get("event_status", pd.Series(dtype=str)) == "all_candidate_simulations_failed").sum())
    failure_reasons = candidate_failures["failure_reason"].value_counts().to_dict() if len(candidate_failures) else {}
    summary = {
        "scope": "candidate generation and simulation; no scoring, ranking, selection or delivery",
        "episodes_attempted": len(selected), "arms_attempted": attempted_arms,
        "arms_completed_288_intervals": completed_arms,
        "evaluated_events": len(events), "candidates_expected": expected_total,
        "candidates_generated": len(candidates), "candidates_simulated": len(candidates),
        "valid_candidates": valid_count, "failed_candidates": failed_count,
        "all_candidate_simulations_failed_events": all_failed_events,
        "complete_trajectories": complete_trajectories,
        "partial_trajectories": partial_trajectories,
        "candidate_failure_reasons": failure_reasons,
        "event_construction_failures": event_construction_failures,
        "ongoing_episode_failures": ongoing_failures,
        "verification_failures": verification_failures,
        "batch_chunk_agreement_checks": batch_checks,
        "batch_chunk_agreement_failures": batch_failures,
        "paired_arm_checks": paired_checks, "paired_arm_failures": paired_failures,
        "lifecycle_failures": lifecycle_failures,
        "strict_step6_refresh_schedule_pass": schedule_pass,
        "preservation_checks_pass": preservation_pass,
        "split_isolation_pass": not bool((events.get("split", pd.Series(dtype=str)) == "testing").any()),
        "implementation_verification_pass": implementation_pass,
        "simulation_completion_pass": simulation_completion_pass,
        "overall_pass": bool(implementation_pass and simulation_completion_pass),
        "score_status": "not_implemented_step10",
        "dataset_hash_discrepancy": "unresolved",
        "runtime_seconds": time.perf_counter() - started,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    (out / "summary.md").write_text("\n".join([
        "# Step 9 bounded candidate-search verification", "",
        f"Implementation verification: **{'PASS' if implementation_pass else 'FAIL'}**",
        f"Simulation completion: **{'PASS' if simulation_completion_pass else 'FAIL'}**",
        f"Overall result: **{'PASS' if summary['overall_pass'] else 'FAIL'}**", "",
        f"Events: {len(events)}", f"Candidates: {len(candidates)}/{expected_total}",
        f"Valid/failed candidates: {valid_count}/{failed_count}",
        f"Complete/partial trajectories: {complete_trajectories}/{partial_trajectories}",
        f"Batch agreement failures: {batch_failures}", f"Paired-arm failures: {paired_failures}", "",
        "Scores are null; Step 10 scoring, ranking, selection and delivery are not implemented.",
        "Grid bounds are experimental diagnostic settings, not patient-specific safe limits.",
        "The checkpoint/dataset hash discrepancy remains unresolved.", "",
    ]))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--checkpoint", default="baseline/model.pt")
    parser.add_argument("--out", default="results/bolus_optimization_migrated_final/step9_candidate_search")
    parser.add_argument("--trigger-configuration", default=str(DEFAULT_TRIGGER_CONFIGURATION))
    parser.add_argument("--consumption-configuration", default=str(DEFAULT_CONSUMPTION_CONFIGURATION))
    parser.add_argument("--search-configuration", default=str(DEFAULT_SEARCH_CONFIGURATION))
    parser.add_argument("--episodes-per-patient", type=int, default=1)
    parser.add_argument("--refresh-minutes", type=int, default=120)
    parser.add_argument("--weight-kg", type=float, default=70.0)
    parser.add_argument("--substeps", type=int, default=5)
    args = parser.parse_args()
    if args.episodes_per_patient < 0 or args.weight_kg <= 0 or args.substeps <= 0:
        parser.error("episode count must be nonnegative; weight and substeps must be positive")
    summary = run_candidate_search_diagnostic(
        args.dataset, args.checkpoint, args.out,
        trigger_configuration_path=args.trigger_configuration,
        consumption_configuration_path=args.consumption_configuration,
        search_configuration_path=args.search_configuration,
        episodes_per_patient=args.episodes_per_patient,
        refresh_minutes=args.refresh_minutes, weight_kg=args.weight_kg,
        substeps=args.substeps,
    )
    print(Path(args.out) / "summary.json")
    if not summary["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
