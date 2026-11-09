"""Step 7 observation-only meal and high-glucose event verification."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import time
from pathlib import Path

import pandas as pd
import torch

from final_model_adapter import sha256

from .checkpoint import load_frozen_gru
from .configuration import FROZEN_CHECKPOINT_SHA256
from .data import read_optimization_data
from .episodes import ALLOWED_SPLITS, EXPECTED_SOURCE_HASHES, build_episode_definitions, initialize_episode
from .events import (
    DEFAULT_TRIGGER_CONFIGURATION, acknowledge_evaluation, create_detector_state,
    detect_evaluation_event, load_trigger_configuration,
)
from .history import complete_interval, current_glucose_mg_dl
from .parameter_updates import RefreshConfiguration, refresh_parameters_if_due
from .verify_history_updates import select_diagnostic_episodes, verify_arm_refresh_schedule


RELEVANT_SOURCE_FILES = (
    "final_model_adapter.py", "optimize.py", "test.py", "bolus_optimization/configuration.py",
    "bolus_optimization/checkpoint.py", "bolus_optimization/data.py",
    "bolus_optimization/physiology.py", "bolus_optimization/episodes.py",
    "bolus_optimization/history.py", "bolus_optimization/parameter_updates.py",
    "bolus_optimization/verify_history_updates.py", "bolus_optimization/events.py",
    "bolus_optimization/verify_events.py",
)


def _decision_row(definition, arm, result, refresh_count_before, refresh_count_after):
    return {
        "episode_id": definition.episode_id, "dataset": definition.dataset,
        "patient_id": definition.patient_id, "split": definition.split,
        "arm": arm.arm_name, "timestamp": result.timestamp,
        "evaluation_eligible": result.evaluation_eligible,
        "event_id": result.event.event_id if result.event else None,
        "event_type": result.event.event_type if result.event else None,
        "trigger_reasons": "|".join(result.trigger_reasons),
        "suppression_reasons": "|".join(result.suppression_reasons),
        "current_glucose_mg_dl": result.current_glucose_mg_dl,
        "high_persistence_start_timestamp": result.high_persistence_start_timestamp,
        "high_persistence_minutes": result.high_persistence_minutes,
        "announced_carbs_g": result.announced_carbs_g,
        "latest_parameter_estimation_timestamp": result.latest_parameter_estimation_timestamp,
        "previous_evaluation_timestamp": result.previous_evaluation_timestamp,
        "previous_delivery_timestamp": result.previous_delivery_timestamp,
        "pending_event_id": result.pending_event_id,
        "already_emitted": result.already_emitted,
        "refresh_count_before_detection": refresh_count_before,
        "refresh_count_after_detection": refresh_count_after,
    }


def _event_row(definition, event):
    return {
        "event_id": event.event_id, "episode_id": event.episode_id,
        "dataset": definition.dataset, "patient_id": event.patient_id,
        "split": definition.split, "arm": event.arm_name,
        "timestamp": event.timestamp, "event_type": event.event_type,
        "trigger_reasons": "|".join(event.trigger_reasons),
        "meal_identity": event.meal_identity,
        "announced_carbs_g": event.announced_carbs_g,
        "glucose_mg_dl": event.glucose_mg_dl,
        "high_persistence_minutes": event.high_persistence_minutes,
        "parameter_estimation_timestamp": event.parameter_estimation_timestamp,
    }


def _outcome_row(definition, arm, outcome):
    return {
        "event_id": outcome.event_id, "episode_id": definition.episode_id,
        "dataset": definition.dataset, "patient_id": definition.patient_id,
        "split": definition.split, "arm": arm.arm_name,
        "acknowledgement_timestamp": outcome.acknowledgement_timestamp,
        "status": outcome.status, "outcome": outcome.outcome,
        "selected_dose_u": outcome.selected_dose_u,
        "retry_policy": outcome.retry_policy,
        "delivery_created_by_outcome": False,
    }


def run_event_diagnostic(
    dataset_path: str | Path,
    checkpoint_path: str | Path,
    output_directory: str | Path,
    *,
    trigger_configuration_path: str | Path = DEFAULT_TRIGGER_CONFIGURATION,
    episodes_per_patient: int = 1,
    refresh_minutes: int = 120,
    weight_kg: float = 70.0,
    substeps: int = 5,
) -> dict:
    started = time.perf_counter()
    dataset_path, checkpoint_path, out = Path(dataset_path), Path(checkpoint_path), Path(output_directory)
    out.mkdir(parents=True, exist_ok=True)
    trigger_configuration, trigger_hash = load_trigger_configuration(trigger_configuration_path)
    refresh_configuration = RefreshConfiguration(refresh_minutes)
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
    episode_rows, decisions, events, outcomes, failures = [], [], [], [], []
    paired_checks = paired_failures = 0
    duplicate_checks = duplicate_failures = 0
    no_extra_refresh_checks = no_extra_refresh_failures = 0
    completed_arms = attempted_arms = 0
    lifecycle_failures = 0
    schedule_checks = []
    for definition in selected:
        episode = initialize_episode(
            groups[(definition.dataset, definition.patient_id)], definition, frozen,
            weight_kg=weight_kg, substeps=substeps,
        )
        episode_row = {
            "episode_id": definition.episode_id, "dataset": definition.dataset,
            "patient_id": definition.patient_id, "split": definition.split,
            "start_timestamp": definition.start_timestamp,
            "end_timestamp": definition.end_timestamp,
            "selection_rule": "first_eligible_per_patient" if episodes_per_patient == 1
            else "all_eligible" if episodes_per_patient == 0
            else f"first_{episodes_per_patient}_eligible_per_patient",
            "initialization_status": episode.initialization_status,
        }
        episode_rows.append(episode_row)
        if episode.initialization_status != "initialized":
            failures.append({**episode_row, "arm": "paired", "phase": "initialization",
                             "timestamp": definition.start_timestamp,
                             "reason": episode.failure.reason if episode.failure else "unknown"})
            continue
        arms = (episode.baseline_arm, episode.optimized_arm)
        for arm in arms:
            arm.detector_state = create_detector_state(arm, definition)
        attempted_arms += 2
        for _ in range(288):
            if not all(arm.status == "active" for arm in arms):
                break
            for arm in arms:
                current_glucose_mg_dl(arm, weight_kg=weight_kg)
            boundary_events = (
                episode.environment.reveal(episode.baseline_arm),
                episode.environment.reveal(episode.optimized_arm),
            )
            results = []
            for arm, current_events in zip(arms, boundary_events):
                try:
                    refresh_parameters_if_due(
                        arm, frozen, current_events, refresh_configuration
                    )
                    refresh_before = len(arm.refresh_log)
                    result = detect_evaluation_event(
                        arm, current_events, trigger_configuration,
                        arm.detector_state, weight_kg=weight_kg,
                    )
                    refresh_after = len(arm.refresh_log)
                    no_extra_refresh_checks += 1
                    no_extra_refresh_failures += int(refresh_before != refresh_after)
                    decisions.append(_decision_row(
                        definition, arm, result, refresh_before, refresh_after
                    ))
                    results.append(result)
                    if result.event is not None:
                        events.append(_event_row(definition, result.event))
                        repeated = detect_evaluation_event(
                            arm, current_events, trigger_configuration,
                            arm.detector_state, weight_kg=weight_kg,
                        )
                        duplicate_checks += 1
                        duplicate_failures += int(
                            not repeated.already_emitted
                            or repeated.event is None
                            or repeated.event.event_id != result.event.event_id
                            or len(arm.detector_state.events) != len(arm.detector_state.outcomes) + 1
                        )
                        outcome = acknowledge_evaluation(
                            arm.detector_state, result.event.event_id,
                            status="completed", outcome="diagnostic_only_no_optimization",
                            acknowledgement_timestamp=arm.current_timestamp,
                        )
                        outcomes.append(_outcome_row(definition, arm, outcome))
                    recorded_action = boundary_events[0].recorded_bolus_u
                    completion = complete_interval(
                        arm, current_events, recorded_action,
                        weight_kg=weight_kg, substeps=substeps,
                    )
                    if not completion.success:
                        failures.append({**episode_row, "arm": arm.arm_name,
                                         "phase": arm.status, "timestamp": arm.current_timestamp,
                                         "reason": arm.failure_reason})
                except Exception as error:
                    arm.status = "failed_event_diagnostic"
                    arm.failure_reason = f"{type(error).__name__}:{error}"
                    failures.append({**episode_row, "arm": arm.arm_name,
                                     "phase": arm.status, "timestamp": arm.current_timestamp,
                                     "reason": arm.failure_reason})
                    lifecycle_failures += 1
            if len(results) == 2:
                paired_checks += 1
                paired_failures += int(not (
                    results[0].evaluation_eligible == results[1].evaluation_eligible
                    and results[0].trigger_reasons == results[1].trigger_reasons
                    and results[0].suppression_reasons == results[1].suppression_reasons
                    and (results[0].event.event_type if results[0].event else None)
                    == (results[1].event.event_type if results[1].event else None)
                ))
        for arm in arms:
            completed = arm.status == "active" and arm.current_timestamp == definition.end_timestamp
            completed_arms += int(completed)
            if arm.detector_state.pending_event_id is not None:
                lifecycle_failures += 1
                failures.append({**episode_row, "arm": arm.arm_name,
                                 "phase": "pending_evaluation", "timestamp": arm.current_timestamp,
                                 "reason": arm.detector_state.pending_event_id})
            schedule_checks.append(verify_arm_refresh_schedule(
                arm, refresh_configuration, definition.end_timestamp
            ))

    episode_frame = pd.DataFrame(episode_rows)
    decision_frame = pd.DataFrame(decisions)
    event_frame = pd.DataFrame(events)
    outcome_frame = pd.DataFrame(outcomes)
    failure_columns = [
        "episode_id", "dataset", "patient_id", "split", "start_timestamp",
        "end_timestamp", "selection_rule", "initialization_status", "arm",
        "phase", "timestamp", "reason",
    ]
    failure_frame = pd.DataFrame(failures, columns=failure_columns)
    episode_frame.to_csv(out / "evaluated_episodes.csv", index=False)
    decision_frame.to_parquet(out / "boundary_decisions.parquet", index=False)
    event_frame.to_parquet(out / "evaluation_events.parquet", index=False)
    outcome_frame.to_parquet(out / "evaluation_outcomes.parquet", index=False)
    failure_frame.to_csv(out / "failures.csv", index=False)

    dataset_hash = sha256(dataset_path)
    checkpoint_data_hash = frozen.checkpoint["data_sha256"]
    source_hashes = {path: sha256(path) for path in RELEVANT_SOURCE_FILES}
    configuration_record = {
        "step": 7, "scope": "observation_only_identical_action_event_detection",
        "dataset": str(dataset_path.resolve()), "dataset_sha256": dataset_hash,
        "checkpoint": str(checkpoint_path.resolve()),
        "checkpoint_sha256": frozen.checkpoint_sha256,
        "checkpoint_dataset_sha256": checkpoint_data_hash,
        "dataset_hash_discrepancy": {"status": "unresolved",
            "current_dataset_matches_checkpoint_record": dataset_hash == checkpoint_data_hash},
        "trigger_configuration_path": str(Path(trigger_configuration_path).resolve()),
        "trigger_configuration_sha256": trigger_hash,
        "trigger_configuration": trigger_configuration.__dict__,
        "experimental_not_clinical": True,
        "splits": list(ALLOWED_SPLITS), "testing_patients_excluded": True,
        "episodes_per_patient": episodes_per_patient,
        "selected_episode_ids": episode_frame["episode_id"].tolist(),
        "refresh_minutes": refresh_minutes, "weight_kg": weight_kg,
        "substeps": substeps, "recorded_future_cgm_used": False,
        "diagnostic_action_source": "externally supplied recorded bolus, identical in both arms",
        "detected_events_caused_actions": False,
        "aggregated_meal_limitation": (
            "A positive five-minute announcement bucket is one event; multiple meals within "
            "one bucket cannot be separated because explicit meal IDs are unavailable."
        ),
        "source_hashes": source_hashes,
        "expected_preserved_source_hashes": EXPECTED_SOURCE_HASHES,
        "loader_audit": loader_audit,
        "software": {"python": platform.python_version(), "platform": platform.platform(),
            **{name: importlib.metadata.version(name) for name in ("numpy", "pandas", "pyarrow", "torch")}},
    }
    (out / "configuration.json").write_text(
        json.dumps(configuration_record, indent=2, default=str) + "\n"
    )
    schedule_pass = bool(
        len(schedule_checks) == attempted_arms
        and all(item["ordered_exact_match"] for item in schedule_checks)
    )
    event_counts = (
        event_frame.groupby(["event_type", "arm"]).size().rename("count").reset_index().to_dict("records")
        if len(event_frame) else []
    )
    patient_counts = (
        event_frame.groupby(["patient_id", "arm", "event_type"]).size().rename("count").reset_index().to_dict("records")
        if len(event_frame) else []
    )
    suppression_counts = {}
    for values in decision_frame.get("suppression_reasons", pd.Series(dtype=str)).fillna(""):
        for reason in filter(None, values.split("|")):
            suppression_counts[reason] = suppression_counts.get(reason, 0) + 1
    preservation_pass = bool(
        frozen.checkpoint_sha256 == FROZEN_CHECKPOINT_SHA256
        and all(source_hashes[path] == expected for path, expected in EXPECTED_SOURCE_HASHES.items())
        and not (episode_frame["split"] == "testing").any()
    )
    implementation_pass = bool(
        preservation_pass and schedule_pass and paired_failures == 0
        and duplicate_failures == 0 and lifecycle_failures == 0
        and no_extra_refresh_failures == 0
        and len(event_frame) == len(outcome_frame)
    )
    completion_pass = bool(completed_arms == attempted_arms and not len(failure_frame))
    summary = {
        "scope": configuration_record["scope"],
        "episodes_attempted": len(selected), "arms_attempted": attempted_arms,
        "arms_completed_288_intervals": completed_arms,
        "arms_failed": attempted_arms - completed_arms,
        "boundaries_processed": len(decision_frame),
        "evaluation_events": len(event_frame), "evaluation_outcomes": len(outcome_frame),
        "event_counts_by_type_and_arm": event_counts,
        "event_counts_by_patient_arm_type": patient_counts,
        "suppression_reason_counts": suppression_counts,
        "duplicate_protection_checks": duplicate_checks,
        "duplicate_protection_failures": duplicate_failures,
        "lifecycle_failures": lifecycle_failures,
        "paired_trigger_checks": paired_checks,
        "paired_trigger_failures": paired_failures,
        "no_extra_gru_refresh_checks": no_extra_refresh_checks,
        "no_extra_gru_refresh_failures": no_extra_refresh_failures,
        "strict_step6_refresh_schedule_pass": schedule_pass,
        "preservation_checks_pass": preservation_pass,
        "implementation_verification_pass": implementation_pass,
        "simulation_completion_pass": completion_pass,
        "overall_pass": bool(implementation_pass and completion_pass),
        "failure_reason_counts": failure_frame["reason"].value_counts().to_dict() if len(failure_frame) else {},
        "runtime_seconds": time.perf_counter() - started,
        "dataset_hash_discrepancy": "unresolved",
        "interpretation": (
            "Events requested diagnostic evaluation only. Recorded boluses were supplied "
            "externally and were not attributed to detected triggers."
        ),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    (out / "summary.md").write_text("\n".join([
        "# Step 7 event-detection verification", "",
        f"Implementation verification: **{'PASS' if implementation_pass else 'FAIL'}**",
        f"Simulation completion: **{'PASS' if completion_pass else 'FAIL'}**",
        f"Overall result: **{'PASS' if summary['overall_pass'] else 'FAIL'}**", "",
        f"Episodes attempted: {len(selected)}",
        f"Arms completed: {completed_arms}/{attempted_arms}",
        f"Evaluation events: {len(event_frame)}",
        f"Paired trigger failures: {paired_failures}",
        f"Lifecycle failures: {lifecycle_failures}", "",
        summary["interpretation"], "",
        "Trigger thresholds are experimental simulation settings, not validated clinical rules.",
        "The checkpoint/dataset hash discrepancy remains unresolved.", "",
    ]))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--checkpoint", default="baseline/model.pt")
    parser.add_argument("--out", default="results/bolus_optimization_migrated_final/step7_event_detection")
    parser.add_argument("--trigger-configuration", default=str(DEFAULT_TRIGGER_CONFIGURATION))
    parser.add_argument("--episodes-per-patient", type=int, default=1)
    parser.add_argument("--refresh-minutes", type=int, default=120)
    parser.add_argument("--weight-kg", type=float, default=70.0)
    parser.add_argument("--substeps", type=int, default=5)
    args = parser.parse_args()
    if args.episodes_per_patient < 0 or args.weight_kg <= 0 or args.substeps <= 0:
        parser.error("episode count must be nonnegative; weight and substeps must be positive")
    summary = run_event_diagnostic(
        args.dataset, args.checkpoint, args.out,
        trigger_configuration_path=args.trigger_configuration,
        episodes_per_patient=args.episodes_per_patient,
        refresh_minutes=args.refresh_minutes, weight_kg=args.weight_kg,
        substeps=args.substeps,
    )
    print(Path(args.out) / "summary.json")
    if not summary["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
