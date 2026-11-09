"""Step 6 identical-action verification for evolving histories and refreshes."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import numbers
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from final_model_adapter import sha256

from .checkpoint import load_frozen_gru
from .configuration import FROZEN_CHECKPOINT_SHA256, MODEL_FEATURES
from .data import read_optimization_data
from .episodes import (
    ALLOWED_SPLITS, EXPECTED_SOURCE_HASHES, build_episode_definitions,
    initialize_episode,
)
from .history import complete_interval, current_glucose_mg_dl
from .parameter_updates import RefreshConfiguration, refresh_parameters_if_due
from .physiology import PARAMETER_NAMES, STATE_NAMES


RELEVANT_SOURCE_FILES = (
    "final_model_adapter.py", "optimize.py", "test.py", "bolus_optimization/configuration.py",
    "bolus_optimization/checkpoint.py", "bolus_optimization/data.py",
    "bolus_optimization/physiology.py", "bolus_optimization/episodes.py",
    "bolus_optimization/history.py", "bolus_optimization/parameter_updates.py",
    "bolus_optimization/verify_history_updates.py",
)


def select_diagnostic_episodes(definitions, episodes_per_patient: int = 1):
    if episodes_per_patient < 0:
        raise ValueError("episodes_per_patient must be nonnegative")
    selected = []
    counts = {}
    for item in definitions:
        if not item.eligible:
            continue
        key = (item.dataset, item.patient_id)
        used = counts.get(key, 0)
        if episodes_per_patient == 0 or used < episodes_per_patient:
            selected.append(item)
            counts[key] = used + 1
    return selected


def _trajectory_row(definition, arm, interval_index):
    row = {
        "episode_id": definition.episode_id, "dataset": definition.dataset,
        "patient_id": definition.patient_id, "split": definition.split,
        "arm": arm.arm_name, "boundary_timestamp": arm.current_timestamp,
        "completed_episode_intervals": interval_index,
        "glucose_mg_dl": arm.history.current_glucose_mg_dl,
        "observation_source": arm.history.current_source,
        "parameter_estimation_timestamp": arm.parameter_estimation_timestamp,
        "arm_status": arm.status,
    }
    row.update({name: float(value) for name, value in zip(STATE_NAMES, arm.physiological_state)})
    return row


def _flatten_refresh(definition, arm, entry):
    row = {
        "episode_id": definition.episode_id, "dataset": definition.dataset,
        "patient_id": definition.patient_id, "split": definition.split,
        "arm": arm.arm_name,
        **{key: value for key, value in entry.items()
           if key not in {"old_parameters", "new_parameters", "absolute_changes", "relative_changes"}},
    }
    for prefix, key in (
        ("old", "old_parameters"), ("new", "new_parameters"),
        ("absolute_change", "absolute_changes"),
        ("relative_change", "relative_changes"),
    ):
        row.update({f"{prefix}_{name}": entry[key][name] for name in PARAMETER_NAMES})
    return row


def verify_arm_refresh_schedule(
    arm,
    refresh_configuration: RefreshConfiguration,
    episode_end_timestamp: pd.Timestamp,
) -> dict:
    """Require an exact full schedule or exact prefix through arm stopping time."""

    end = pd.Timestamp(episode_end_timestamp)
    start = pd.Timestamp(arm.episode_start_timestamp)
    stop = pd.Timestamp(arm.current_timestamp)
    elapsed_seconds = (stop - start).total_seconds()
    grid_aligned = bool(
        elapsed_seconds >= 0
        and elapsed_seconds % (5 * 60) == 0
        and stop <= end
    )
    elapsed_minutes = int(elapsed_seconds // 60) if elapsed_seconds >= 0 else -1
    completed = bool(arm.status == "active" and stop == end)
    configured = tuple(refresh_configuration.scheduled_offsets)
    expected = configured if completed else tuple(
        offset for offset in configured if offset <= elapsed_minutes
    )
    observed_values = []
    invalid_offset_entries = []
    invalid_timestamp_entries = []
    for index, entry in enumerate(arm.refresh_log):
        raw_offset = entry.get("scheduled_offset_minutes")
        offset_valid = bool(
            not isinstance(raw_offset, (bool, np.bool_))
            and isinstance(raw_offset, numbers.Real)
            and np.isfinite(raw_offset)
            and float(raw_offset).is_integer()
        )
        if not offset_valid:
            invalid_offset_entries.append({
                "entry_index": index,
                "value": repr(raw_offset),
                "reason": "offset_must_be_a_finite_integer_value",
            })
            continue
        offset = int(raw_offset)
        observed_values.append(offset)
        raw_timestamp = entry.get("refresh_timestamp")
        if raw_timestamp is None:
            invalid_timestamp_entries.append({
                "entry_index": index, "offset_minutes": offset,
                "value": repr(raw_timestamp), "reason": "missing_refresh_timestamp",
            })
            continue
        try:
            timestamp = pd.Timestamp(raw_timestamp)
            expected_timestamp = start + pd.Timedelta(minutes=offset)
            timestamp_valid = bool(not pd.isna(timestamp) and timestamp == expected_timestamp)
        except (TypeError, ValueError, OverflowError):
            timestamp_valid = False
            expected_timestamp = start + pd.Timedelta(minutes=offset)
        if not timestamp_valid:
            invalid_timestamp_entries.append({
                "entry_index": index, "offset_minutes": offset,
                "value": repr(raw_timestamp),
                "expected_timestamp": expected_timestamp,
                "reason": "refresh_timestamp_does_not_equal_episode_start_plus_offset",
            })
    observed = tuple(observed_values)
    offsets_valid = not invalid_offset_entries
    timestamps_valid = not invalid_timestamp_entries
    no_duplicates = len(observed) == len(set(observed))
    exact_match = bool(
        grid_aligned and offsets_valid and timestamps_valid
        and no_duplicates and observed == expected
    )
    return {
        "scope": "completed_full_schedule" if completed else "stopped_schedule_prefix",
        "completed_arm": completed,
        "stopping_timestamp": stop,
        "stopping_offset_minutes": elapsed_minutes,
        "expected_offsets_minutes": list(expected),
        "observed_offsets_minutes": list(observed),
        "ordered_exact_match": exact_match,
        "missing_offsets_minutes": [value for value in expected if value not in observed],
        "unexpected_offsets_minutes": [value for value in observed if value not in expected],
        "duplicate_offsets_present": not no_duplicates,
        "offset_values_valid": offsets_valid,
        "refresh_timestamps_valid": timestamps_valid,
        "invalid_offset_entries": invalid_offset_entries,
        "invalid_timestamp_entries": invalid_timestamp_entries,
        "timestamp_grid_aligned": grid_aligned,
    }


def run_diagnostic(
    dataset_path: str | Path,
    checkpoint_path: str | Path,
    output_directory: str | Path,
    *,
    episodes_per_patient: int = 1,
    refresh_minutes: int = 120,
    weight_kg: float = 70.0,
    substeps: int = 5,
) -> dict:
    started = time.perf_counter()
    dataset_path, checkpoint_path, out = Path(dataset_path), Path(checkpoint_path), Path(output_directory)
    out.mkdir(parents=True, exist_ok=True)
    data, patient_splits, loader_audit = read_optimization_data(dataset_path)
    frozen = load_frozen_gru(checkpoint_path, expected_sha256=FROZEN_CHECKPOINT_SHA256)
    if patient_splits != frozen.checkpoint["patient_splits"]:
        raise ValueError("Patient splits differ from the frozen checkpoint")
    configuration = RefreshConfiguration(refresh_minutes)
    definitions = build_episode_definitions(data)
    selected = select_diagnostic_episodes(definitions, episodes_per_patient)
    groups = {
        (str(dataset), str(patient)): group.sort_values("timestamp").reset_index(drop=True)
        for (dataset, patient), group in data[data["split"].isin(ALLOWED_SPLITS)].groupby(
            ["dataset", "patient_id"], sort=False
        )
    }

    episode_rows, trajectory_rows, refresh_rows, failure_rows = [], [], [], []
    identity_checks = 0
    identity_failures = 0
    history_checks = 0
    information_isolation_checks = 0
    information_isolation_failures = 0
    completed_arms = 0
    attempted_arms = 0
    total_roundoff_corrections = 0
    schedule_checks = []
    for definition in selected:
        episode = initialize_episode(
            groups[(definition.dataset, definition.patient_id)], definition,
            frozen, weight_kg=weight_kg, substeps=substeps,
        )
        episode_row = {
            "episode_id": definition.episode_id, "dataset": definition.dataset,
            "patient_id": definition.patient_id, "split": definition.split,
            "start_timestamp": definition.start_timestamp,
            "end_timestamp": definition.end_timestamp,
            "selection_rule": (
                "all_eligible" if episodes_per_patient == 0
                else f"first_{episodes_per_patient}_eligible_per_patient"
            ),
            "initialization_status": episode.initialization_status,
        }
        episode_rows.append(episode_row)
        if episode.initialization_status != "initialized":
            failure_rows.append({
                **episode_row, "arm": "paired", "phase": "initialization",
                "timestamp": definition.start_timestamp,
                "reason": episode.failure.reason if episode.failure else "unknown",
            })
            continue
        arms = (episode.baseline_arm, episode.optimized_arm)
        attempted_arms += 2
        for arm in arms:
            trajectory_rows.append(_trajectory_row(definition, arm, 0))
        for interval_index in range(288):
            active = [arm for arm in arms if arm.status == "active"]
            if len(active) != 2:
                for arm in active:
                    arm.status = "stopped_paired_failure"
                    arm.failure_reason = "paired_arm_failed"
                    failure_rows.append({
                        "episode_id": definition.episode_id, "dataset": definition.dataset,
                        "patient_id": definition.patient_id, "split": definition.split,
                        "start_timestamp": definition.start_timestamp,
                        "end_timestamp": definition.end_timestamp,
                        "selection_rule": episode_row["selection_rule"],
                        "initialization_status": episode.initialization_status,
                        "arm": arm.arm_name, "phase": arm.status,
                        "timestamp": arm.current_timestamp, "reason": arm.failure_reason,
                    })
                break
            for arm in arms:
                current_glucose_mg_dl(arm, weight_kg=weight_kg)
            baseline_events = episode.environment.reveal(episode.baseline_arm)
            optimized_events = episode.environment.reveal(episode.optimized_arm)
            information_isolation_checks += 1
            information_isolation_failures += int(not (
                optimized_events.recorded_bolus_u is None
                and episode.baseline_arm.history.gru_input(baseline_events)[-1, 2].item() == 0.0
                and episode.optimized_arm.history.gru_input(optimized_events)[-1, 2].item() == 0.0
            ))
            externally_supplied_recorded_bolus = baseline_events.recorded_bolus_u
            for arm, events in zip(arms, (baseline_events, optimized_events)):
                if arm.status != "active":
                    continue
                try:
                    refresh_parameters_if_due(arm, frozen, events, configuration)
                except Exception as error:
                    if arm.status == "active":
                        arm.status, arm.failure_reason = "failed_schedule", str(error)
                if arm.status == "active":
                    completion = complete_interval(
                        arm, events, externally_supplied_recorded_bolus,
                        weight_kg=weight_kg, substeps=substeps,
                    )
                    total_roundoff_corrections += completion.roundoff_corrections
                trajectory_rows.append(_trajectory_row(definition, arm, interval_index + 1))
                if arm.status != "active":
                    failure_rows.append({
                        "episode_id": definition.episode_id, "dataset": definition.dataset,
                        "patient_id": definition.patient_id, "split": definition.split,
                        "start_timestamp": definition.start_timestamp,
                        "end_timestamp": definition.end_timestamp,
                        "selection_rule": episode_row["selection_rule"],
                        "initialization_status": episode.initialization_status,
                        "arm": arm.arm_name, "phase": arm.status,
                        "timestamp": arm.current_timestamp, "reason": arm.failure_reason,
                    })
            if all(arm.status == "active" for arm in arms):
                identity_checks += 1
                equal = (
                    torch.equal(arms[0].physiological_state, arms[1].physiological_state)
                    and torch.equal(arms[0].parameters, arms[1].parameters)
                    and torch.equal(
                        arms[0].history.completed_bolus_u,
                        arms[1].history.completed_bolus_u,
                    )
                    and arms[0].current_timestamp == arms[1].current_timestamp
                )
                identity_failures += int(not equal)
                history_checks += int(
                    len(arms[0].history.inference_timestamps()) == 289
                    and len(set(arms[0].history.inference_timestamps())) == 289
                    and len(arms[1].history.inference_timestamps()) == 289
                )
        for arm in arms:
            refresh_rows.extend(_flatten_refresh(definition, arm, row) for row in arm.refresh_log)
            completed_arms += int(
                arm.status == "active" and arm.current_timestamp == definition.end_timestamp
            )
            schedule_checks.append({
                "episode_id": definition.episode_id,
                "patient_id": definition.patient_id,
                "split": definition.split,
                "arm": arm.arm_name,
                **verify_arm_refresh_schedule(arm, configuration, definition.end_timestamp),
            })

    episode_frame = pd.DataFrame(episode_rows)
    trajectory_frame = pd.DataFrame(trajectory_rows)
    refresh_frame = pd.DataFrame(refresh_rows)
    failure_columns = [
        "episode_id", "dataset", "patient_id", "split", "start_timestamp",
        "end_timestamp", "selection_rule", "initialization_status", "arm",
        "phase", "timestamp", "reason",
    ]
    failure_frame = pd.DataFrame(failure_rows, columns=failure_columns)
    episode_frame.to_csv(out / "evaluated_episodes.csv", index=False)
    refresh_frame.to_parquet(out / "parameter_refresh_log.parquet", index=False)
    trajectory_frame.to_parquet(out / "trajectories.parquet", index=False)
    failure_frame.to_csv(out / "failures.csv", index=False)

    source_hashes = {path: sha256(path) for path in RELEVANT_SOURCE_FILES}
    dataset_hash = sha256(dataset_path)
    checkpoint_data_hash = frozen.checkpoint["data_sha256"]
    config_record = {
        "step": 6,
        "diagnostic_label": "identical-action verification",
        "dataset": str(dataset_path.resolve()), "dataset_sha256": dataset_hash,
        "checkpoint": str(checkpoint_path.resolve()),
        "checkpoint_sha256": frozen.checkpoint_sha256,
        "checkpoint_dataset_sha256": checkpoint_data_hash,
        "dataset_hash_discrepancy": {
            "status": "unresolved",
            "current_dataset_matches_checkpoint_record": dataset_hash == checkpoint_data_hash,
        },
        "source_hashes": source_hashes,
        "expected_preserved_source_hashes": EXPECTED_SOURCE_HASHES,
        "splits": list(ALLOWED_SPLITS), "testing_patients_excluded": True,
        "episodes_per_patient": episodes_per_patient,
        "run_scope": "all_eligible_episodes" if episodes_per_patient == 0 else "deterministic_smoke_set",
        "selected_episode_ids": episode_frame["episode_id"].tolist(),
        "parameter_refresh_minutes": refresh_minutes,
        "scheduled_refresh_offsets_minutes": list(configuration.scheduled_offsets),
        "terminal_boundary_refresh": False,
        "weight_kg": weight_kg, "substeps": substeps,
        "model_feature_order": list(MODEL_FEATURES),
        "current_boundary_bolus": 0.0,
        "action_provider": "Recorded bolus supplied externally and identically to both arms.",
        "recorded_future_cgm_used": False,
        "feedback_limitation": (
            "Refreshes increasingly use simulated glucose/action histories, while the checkpoint "
            "was trained on recorded histories; accuracy of this feedback behavior is unestablished."
        ),
        "loader_audit": loader_audit,
        "software": {
            "python": platform.python_version(), "platform": platform.platform(),
            **{name: importlib.metadata.version(name) for name in ("numpy", "pandas", "pyarrow", "torch")},
        },
    }
    (out / "configuration.json").write_text(json.dumps(config_record, indent=2, default=str) + "\n")
    expected_refreshes_per_completed_arm = len(configuration.scheduled_offsets)
    refresh_validation_pass = bool(
        (len(refresh_frame) == 0 or refresh_frame["parameter_validation_passed"].all())
        and (len(refresh_frame) == 0 or refresh_frame["state_preserved_exactly"].all())
        and (len(refresh_frame) == 0 or refresh_frame["history_preserved_exactly"].all())
        and (len(refresh_frame) == 0 or refresh_frame["scheduled_offset_minutes"].isin(
            configuration.scheduled_offsets
        ).all())
    )
    schedule_verification_pass = bool(
        len(schedule_checks) == attempted_arms
        and all(item["ordered_exact_match"] for item in schedule_checks)
    )
    completed_schedule_checks = [item for item in schedule_checks if item["completed_arm"]]
    stopped_schedule_checks = [item for item in schedule_checks if not item["completed_arm"]]
    schedule_mismatches = [item for item in schedule_checks if not item["ordered_exact_match"]]
    implementation_pass = bool(
        frozen.checkpoint_sha256 == FROZEN_CHECKPOINT_SHA256
        and all(source_hashes[path] == expected for path, expected in EXPECTED_SOURCE_HASHES.items())
        and not (episode_frame["split"] == "testing").any()
        and identity_failures == 0
        and history_checks == identity_checks
        and information_isolation_failures == 0
        and refresh_validation_pass
        and schedule_verification_pass
    )
    completion_pass = bool(completed_arms == attempted_arms and not len(failure_frame))
    summary = {
        "diagnostic_label": "identical-action verification",
        "run_scope": config_record["run_scope"],
        "episodes_attempted": len(selected),
        "episodes_completed_288_intervals": completed_arms // 2,
        "episodes_failed_or_incomplete": len(selected) - completed_arms // 2,
        "arms_attempted": attempted_arms,
        "arms_completed_288_intervals": completed_arms,
        "arms_failed": attempted_arms - completed_arms,
        "expected_refreshes_per_completed_arm": expected_refreshes_per_completed_arm,
        "observed_refreshes": len(refresh_frame),
        "expected_refreshes_for_completed_arms": completed_arms * expected_refreshes_per_completed_arm,
        "refresh_validation_and_preservation_pass": refresh_validation_pass,
        "refresh_schedule_verification_pass": schedule_verification_pass,
        "completed_arm_full_schedule_checks": {
            "passed": sum(item["ordered_exact_match"] for item in completed_schedule_checks),
            "required": len(completed_schedule_checks),
        },
        "failed_or_stopped_arm_prefix_schedule_checks": {
            "passed": sum(item["ordered_exact_match"] for item in stopped_schedule_checks),
            "required": len(stopped_schedule_checks),
        },
        "refresh_schedule_mismatches": schedule_mismatches,
        "identical_action_boundary_checks": identity_checks,
        "identity_check_failures": identity_failures,
        "history_alignment_checks_passed": history_checks,
        "information_isolation_checks_passed": information_isolation_checks,
        "information_isolation_check_failures": information_isolation_failures,
        "failure_reason_counts": failure_frame["reason"].value_counts().to_dict() if len(failure_frame) else {},
        "roundoff_corrections": total_roundoff_corrections,
        "runtime_seconds": time.perf_counter() - started,
        "implementation_verification_pass": implementation_pass,
        "simulation_completion_pass": completion_pass,
        "overall_pass": bool(implementation_pass and completion_pass),
        "dataset_hash_discrepancy": "unresolved",
        "interpretation": (
            "This verifies machinery under identical recorded actions; it is not an "
            "optimized-versus-baseline effectiveness evaluation."
        ),
        "feedback_limitation": config_record["feedback_limitation"],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    (out / "summary.md").write_text("\n".join([
        "# Step 6 history and parameter-refresh verification", "",
        f"Implementation verification: **{'PASS' if implementation_pass else 'FAIL'}**",
        f"Simulation completion: **{'PASS' if completion_pass else 'FAIL'}**",
        f"Overall result: **{'PASS' if summary['overall_pass'] else 'FAIL'}**", "",
        f"Episodes attempted: {len(selected)}",
        f"Arms completed: {completed_arms}/{attempted_arms}",
        f"Observed refreshes: {len(refresh_frame)}",
        f"Exact per-arm schedule verification: {'PASS' if schedule_verification_pass else 'FAIL'}",
        f"Identity failures: {identity_failures}", "",
        summary["interpretation"], "", summary["feedback_limitation"], "",
        "The checkpoint/dataset hash discrepancy remains unresolved.", "",
    ]))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--checkpoint", default="baseline/model.pt")
    parser.add_argument("--out", default="results/bolus_optimization_migrated_final/step6_history_updates")
    parser.add_argument("--episodes-per-patient", type=int, default=1,
                        help="1 is the deterministic smoke set; 0 selects all eligible episodes")
    parser.add_argument("--refresh-minutes", type=int, default=120)
    parser.add_argument("--weight-kg", type=float, default=70.0)
    parser.add_argument("--substeps", type=int, default=5)
    args = parser.parse_args()
    if args.episodes_per_patient < 0 or args.weight_kg <= 0 or args.substeps <= 0:
        parser.error("episode count must be nonnegative; weight and substeps must be positive")
    summary = run_diagnostic(
        args.dataset, args.checkpoint, args.out,
        episodes_per_patient=args.episodes_per_patient,
        refresh_minutes=args.refresh_minutes, weight_kg=args.weight_kg,
        substeps=args.substeps,
    )
    print(Path(args.out) / "summary.json")
    if not summary["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
