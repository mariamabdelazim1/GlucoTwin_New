"""Step 8 observation-only verification of four-hour candidate input construction."""

from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from final_model_adapter import sha256

from .candidate_inputs import (
    DEFAULT_CONSUMPTION_CONFIGURATION, build_candidate_inputs,
    create_decision_snapshot, load_consumption_configuration,
    validate_decision_snapshot,
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
from .physiology import PARAMETER_NAMES, PHYSIOLOGICAL_INPUT_NAMES, STATE_NAMES
from .verify_history_updates import select_diagnostic_episodes, verify_arm_refresh_schedule


RELEVANT_SOURCE_FILES = (
    "final_model_adapter.py", "optimize.py", "test.py", "bolus_optimization/configuration.py",
    "bolus_optimization/checkpoint.py", "bolus_optimization/data.py",
    "bolus_optimization/physiology.py", "bolus_optimization/episodes.py",
    "bolus_optimization/history.py", "bolus_optimization/parameter_updates.py",
    "bolus_optimization/verify_history_updates.py", "bolus_optimization/events.py",
    "bolus_optimization/candidate_inputs.py",
    "bolus_optimization/verify_candidate_inputs.py",
)


def _versions():
    values = {"python": platform.python_version(), "platform": platform.platform()}
    for name in ("numpy", "pandas", "pyarrow", "torch"):
        try:
            values[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            values[name] = "unavailable"
    return values


def _snapshot_row(definition, snapshot):
    row = {
        "episode_id": snapshot.episode_id, "dataset": definition.dataset,
        "patient_id": snapshot.patient_id, "split": definition.split,
        "arm": snapshot.arm_name, "evaluation_event_id": snapshot.evaluation_event_id,
        "event_type": snapshot.event_type, "decision_timestamp": snapshot.decision_timestamp,
        "parameter_estimation_timestamp": snapshot.parameter_estimation_timestamp,
        "current_basal_rate_u_per_hour": snapshot.current_basal_rate_u_per_hour,
        "current_announced_carbs_g": snapshot.current_announced_carbs_g,
        "known_outstanding_carbs_g": sum(x.remaining_carbs_g for x in snapshot.outstanding_meals),
        "outstanding_meal_count": len(snapshot.outstanding_meals),
        "outstanding_meals_json": json.dumps([
            {
                "meal_identity": x.meal_identity,
                "announcement_timestamp": x.announcement_timestamp.isoformat(),
                "announced_carbs_g": x.announced_carbs_g,
                "consumed_carbs_g": x.consumed_carbs_g,
                "remaining_carbs_g": x.remaining_carbs_g,
            } for x in snapshot.outstanding_meals
        ]),
        "unmatched_historical_consumption_g": snapshot.unmatched_historical_consumption_g,
    }
    row.update({f"state_{name}": float(value) for name, value in zip(STATE_NAMES, snapshot.physiological_state)})
    row.update({f"parameter_{name}": float(value) for name, value in zip(PARAMETER_NAMES, snapshot.parameters)})
    return row


def _template_rows(definition, batch):
    candidate = batch.candidates[0]
    return [{
        "episode_id": batch.snapshot.episode_id, "dataset": definition.dataset,
        "patient_id": batch.snapshot.patient_id, "split": definition.split,
        "arm": batch.snapshot.arm_name,
        "evaluation_event_id": batch.snapshot.evaluation_event_id,
        "candidate_id": candidate.candidate_id, "candidate_bolus_u": candidate.bolus_u,
        "interval_index": index, "interval_timestamp": interval,
        "output_timestamp": output, "basal_source": batch.basal_source,
        "basal_availability_timestamp": batch.basal_availability_timestamp,
        "consumption_profile_name": batch.consumption_profile_name,
        "basal_rate_u_per_hour": float(candidate.future_inputs[index, 0]),
        "bolus_u": float(candidate.future_inputs[index, 1]),
        "consumed_carbs_g": float(candidate.future_inputs[index, 2]),
    } for index, (interval, output) in enumerate(zip(
        batch.interval_timestamps, batch.output_timestamps
    ))]


def _arm_unchanged(arm, before) -> bool:
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
        and arm.refresh_log == before["refresh_log"]
    )


def run_candidate_input_diagnostic(
    dataset_path: str | Path,
    checkpoint_path: str | Path,
    output_directory: str | Path,
    *,
    trigger_configuration_path: str | Path = DEFAULT_TRIGGER_CONFIGURATION,
    consumption_configuration_path: str | Path = DEFAULT_CONSUMPTION_CONFIGURATION,
    episodes_per_patient: int = 1,
    refresh_minutes: int = 120,
    weight_kg: float = 70.0,
    substeps: int = 5,
) -> dict:
    started = time.perf_counter()
    dataset_path, checkpoint_path, out = Path(dataset_path), Path(checkpoint_path), Path(output_directory)
    out.mkdir(parents=True, exist_ok=True)
    trigger, trigger_hash = load_trigger_configuration(trigger_configuration_path)
    consumption, consumption_hash = load_consumption_configuration(consumption_configuration_path)
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
    snapshot_rows, template_rows, check_rows, failure_rows, schedule_checks = [], [], [], [], []
    attempted_arms = completed_arms = detected_events = lifecycle_failures = 0
    paired_checks = paired_failures = 0
    for definition in selected:
        episode = initialize_episode(
            groups[(definition.dataset, definition.patient_id)], definition, frozen,
            weight_kg=weight_kg, substeps=substeps,
        )
        if episode.initialization_status != "initialized":
            failure_rows.append({
                "episode_id": definition.episode_id, "patient_id": definition.patient_id,
                "arm": "paired", "timestamp": definition.start_timestamp,
                "phase": "initialization", "reason": episode.failure.reason if episode.failure else "unknown",
            })
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
            results = []
            for arm, current_events in zip(arms, current):
                try:
                    current_glucose_mg_dl(arm, weight_kg=weight_kg)
                    refresh_parameters_if_due(arm, frozen, current_events, refresh)
                    result = detect_evaluation_event(
                        arm, current_events, trigger, arm.detector_state, weight_kg=weight_kg
                    )
                    results.append(result)
                    if result.event is not None:
                        detected_events += 1
                        before = {
                            "state": arm.physiological_state.clone(),
                            "parameters": arm.parameters.clone(), "timestamp": arm.current_timestamp,
                            "estimation": arm.parameter_estimation_timestamp,
                            "history": arm.history.clone(), "ledger": copy.deepcopy(arm.meal_ledger),
                            "pending": arm.detector_state.pending_event_id,
                            "deliveries": copy.deepcopy(arm.detector_state.deliveries),
                            "refresh_log": copy.deepcopy(arm.refresh_log),
                        }
                        snapshot = create_decision_snapshot(
                            arm, current_events, result.event, arm.detector_state
                        )
                        batch = build_candidate_inputs(snapshot, [0.0], consumption)
                        snapshot_rows.append(_snapshot_row(definition, snapshot))
                        template_rows.extend(_template_rows(definition, batch))
                        candidate = batch.candidates[0]
                        checks = {
                            "episode_id": definition.episode_id,
                            "patient_id": definition.patient_id, "arm": arm.arm_name,
                            "evaluation_event_id": result.event.event_id,
                            "decision_timestamp": arm.current_timestamp,
                            "horizon_48_intervals": len(batch.interval_timestamps) == PREDICTION_HORIZON_STEPS,
                            "interval_alignment_pass": all(
                                right - left == pd.Timedelta(minutes=5)
                                for left, right in zip(batch.interval_timestamps, batch.interval_timestamps[1:])
                            ) and batch.output_timestamps[-1] == arm.current_timestamp + pd.Timedelta(hours=4),
                            "input_order_pass": batch.input_names == PHYSIOLOGICAL_INPUT_NAMES,
                            "consumption_conservation_pass": np.isclose(
                                float(batch.assumed_consumed_carbs_g.sum()), batch.outstanding_carbs_g,
                                rtol=0.0, atol=max(consumption.sum_tolerance, 1e-5),
                            ),
                            "bolus_once_at_zero_pass": float(candidate.future_inputs[0, 1]) == 0.0
                            and int(torch.count_nonzero(candidate.future_inputs[:, 1])) == 0,
                            "constant_current_basal_pass": bool(torch.all(
                                candidate.future_inputs[:, 0] == candidate.future_inputs[0, 0]
                            ).item()),
                            "construction_no_mutation_pass": _arm_unchanged(arm, before),
                            "fixed_parameters_match_snapshot": torch.equal(
                                candidate.fixed_parameters, snapshot.parameters
                            ),
                            "state_matches_snapshot": torch.equal(candidate.initial_state, snapshot.physiological_state),
                            "shared_snapshot_validation_pass": validate_decision_snapshot(snapshot) is snapshot,
                            "materialized_inputs_valid_pass": bool(
                                torch.isfinite(candidate.future_inputs).all().item()
                                and (candidate.future_inputs >= 0).all().item()
                            ),
                        }
                        check_rows.append(checks)
                        acknowledge_evaluation(
                            arm.detector_state, result.event.event_id,
                            status="completed", outcome="diagnostic_only_no_optimization",
                            acknowledgement_timestamp=arm.current_timestamp,
                        )
                    recorded_action = current[0].recorded_bolus_u
                    completion = complete_interval(
                        arm, current_events, recorded_action,
                        weight_kg=weight_kg, substeps=substeps,
                    )
                    if not completion.success:
                        raise RuntimeError(completion.failure_reason)
                except Exception as error:
                    arm.status = "failed_step8_diagnostic"
                    arm.failure_reason = f"{type(error).__name__}:{error}"
                    failure_rows.append({
                        "episode_id": definition.episode_id, "patient_id": definition.patient_id,
                        "arm": arm.arm_name, "timestamp": arm.current_timestamp,
                        "phase": arm.status, "reason": arm.failure_reason,
                    })
            if len(results) == 2:
                paired_checks += 1
                paired_failures += int(not (
                    results[0].evaluation_eligible == results[1].evaluation_eligible
                    and results[0].trigger_reasons == results[1].trigger_reasons
                    and results[0].suppression_reasons == results[1].suppression_reasons
                ))
        for arm in arms:
            completed = arm.status == "active" and arm.current_timestamp == definition.end_timestamp
            completed_arms += int(completed)
            if arm.detector_state.pending_event_id is not None:
                lifecycle_failures += 1
            schedule_checks.append(verify_arm_refresh_schedule(arm, refresh, definition.end_timestamp))

    snapshots = pd.DataFrame(snapshot_rows)
    templates = pd.DataFrame(template_rows)
    checks = pd.DataFrame(check_rows)
    failure_columns = ["episode_id", "patient_id", "arm", "timestamp", "phase", "reason"]
    failures = pd.DataFrame(failure_rows, columns=failure_columns)
    snapshots.to_parquet(out / "decision_snapshots.parquet", index=False)
    templates.to_parquet(out / "future_input_templates.parquet", index=False)
    checks.to_csv(out / "construction_checks.csv", index=False)
    failures.to_csv(out / "failures.csv", index=False)
    source_hashes = {path: sha256(path) for path in RELEVANT_SOURCE_FILES}
    dataset_hash = sha256(dataset_path)
    checkpoint_dataset_hash = frozen.checkpoint.get("data_sha256")
    configuration = {
        "step": 8, "scope": "candidate input construction only",
        "dataset": str(dataset_path.resolve()), "dataset_sha256": dataset_hash,
        "checkpoint": str(checkpoint_path.resolve()), "checkpoint_sha256": frozen.checkpoint_sha256,
        "checkpoint_dataset_sha256": checkpoint_dataset_hash,
        "dataset_hash_discrepancy": {
            "status": "unresolved",
            "current_dataset_matches_checkpoint_record": dataset_hash == checkpoint_dataset_hash,
        },
        "splits": list(ALLOWED_SPLITS), "testing_patients_used": False,
        "horizon_intervals": 48, "interval_minutes": 5, "horizon_minutes": 240,
        "physiological_input_order": list(PHYSIOLOGICAL_INPUT_NAMES),
        "candidate_values": [0.0], "candidate_value_purpose": "construction placeholder, not a search grid",
        "consumption_configuration": {
            "path": str(Path(consumption_configuration_path).resolve()),
            "sha256": consumption_hash, "configuration_version": consumption.configuration_version,
            "profile_name": consumption.profile_name,
            "interval_fractions": list(consumption.interval_fractions),
            "sum_tolerance": consumption.sum_tolerance, "intended_use": consumption.intended_use,
        },
        "trigger_configuration_sha256": trigger_hash,
        "default_basal_contract": "Hold the current available U/hour rate constant for 48 intervals.",
        "known_basal_schedule_caveat": "Availability metadata is a caller contract, not proof the schedule was genuinely known.",
        "future_data_contract": "No future CGM, basal, bolus or actual consumption is read by candidate construction.",
        "fixed_parameter_contract": "The snapshot parameter vector is held fixed for the full candidate horizon.",
        "snapshot_validation_contract": (
            "Creation and materialization share validation of simulator state rules, "
            "parameter bounds, causal timestamps, default basal and meal conservation."
        ),
        "loader_audit": loader_audit, "source_hashes": source_hashes,
        "expected_preserved_source_hashes": EXPECTED_SOURCE_HASHES,
        "software_versions": _versions(),
    }
    (out / "configuration.json").write_text(json.dumps(configuration, indent=2, default=str) + "\n")
    boolean_columns = [
        "horizon_48_intervals", "interval_alignment_pass", "input_order_pass",
        "consumption_conservation_pass", "bolus_once_at_zero_pass",
        "constant_current_basal_pass", "construction_no_mutation_pass",
        "fixed_parameters_match_snapshot", "state_matches_snapshot",
        "shared_snapshot_validation_pass", "materialized_inputs_valid_pass",
    ]
    failed_check_rows = int((~checks[boolean_columns].all(axis=1)).sum()) if len(checks) else detected_events
    checks_pass = bool(len(checks) == detected_events and failed_check_rows == 0)
    schedule_pass = bool(
        len(schedule_checks) == attempted_arms
        and all(x["ordered_exact_match"] for x in schedule_checks)
    )
    preservation_pass = bool(
        frozen.checkpoint_sha256 == FROZEN_CHECKPOINT_SHA256
        and all(source_hashes[path] == expected for path, expected in EXPECTED_SOURCE_HASHES.items())
    )
    implementation_pass = bool(
        checks_pass and schedule_pass and preservation_pass and lifecycle_failures == 0
        and paired_failures == 0 and len(snapshots) == detected_events
        and len(templates) == detected_events * PREDICTION_HORIZON_STEPS
    )
    completion_pass = bool(completed_arms == attempted_arms and failures.empty)
    summary = {
        "scope": "four-hour candidate input construction; no forecasting, scoring or delivery",
        "episodes_attempted": len(selected), "arms_attempted": attempted_arms,
        "arms_completed_288_intervals": completed_arms,
        "events_with_snapshots": detected_events,
        "decision_snapshots": len(snapshots), "future_template_rows": len(templates),
        "construction_checks": len(checks), "construction_check_failures": failed_check_rows,
        "paired_trigger_checks": paired_checks, "paired_trigger_failures": paired_failures,
        "lifecycle_failures": lifecycle_failures,
        "strict_step6_refresh_schedule_pass": schedule_pass,
        "preservation_checks_pass": preservation_pass,
        "implementation_verification_pass": implementation_pass,
        "simulation_completion_pass": completion_pass,
        "overall_pass": bool(implementation_pass and completion_pass),
        "dataset_hash_discrepancy": "unresolved",
        "runtime_seconds": time.perf_counter() - started,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    (out / "summary.md").write_text("\n".join([
        "# Step 8 candidate-input verification", "",
        f"Implementation verification: **{'PASS' if implementation_pass else 'FAIL'}**",
        f"Simulation completion: **{'PASS' if completion_pass else 'FAIL'}**",
        f"Overall result: **{'PASS' if summary['overall_pass'] else 'FAIL'}**", "",
        f"Episodes attempted: {len(selected)}", f"Arms completed: {completed_arms}/{attempted_arms}",
        f"Decision snapshots: {len(snapshots)}", f"Future template rows: {len(templates)}", "",
        "Templates used one caller-supplied zero-bolus placeholder and never influenced delivered actions.",
        "The checkpoint/dataset hash discrepancy remains unresolved.",
        "No dose search, forecast scoring, ranking, selection or optimizer delivery was performed.", "",
    ]))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--checkpoint", default="baseline/model.pt")
    parser.add_argument("--out", default="results/bolus_optimization_migrated_final/step8_candidate_inputs")
    parser.add_argument("--trigger-configuration", default=str(DEFAULT_TRIGGER_CONFIGURATION))
    parser.add_argument("--consumption-configuration", default=str(DEFAULT_CONSUMPTION_CONFIGURATION))
    parser.add_argument("--episodes-per-patient", type=int, default=1)
    parser.add_argument("--refresh-minutes", type=int, default=120)
    parser.add_argument("--weight-kg", type=float, default=70.0)
    parser.add_argument("--substeps", type=int, default=5)
    args = parser.parse_args()
    if args.episodes_per_patient < 0 or args.weight_kg <= 0 or args.substeps <= 0:
        parser.error("episode count must be nonnegative; weight and substeps must be positive")
    summary = run_candidate_input_diagnostic(
        args.dataset, args.checkpoint, args.out,
        trigger_configuration_path=args.trigger_configuration,
        consumption_configuration_path=args.consumption_configuration,
        episodes_per_patient=args.episodes_per_patient,
        refresh_minutes=args.refresh_minutes, weight_kg=args.weight_kg,
        substeps=args.substeps,
    )
    print(Path(args.out) / "summary.json")
    if not summary["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
