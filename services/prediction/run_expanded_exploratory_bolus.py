#!/usr/bin/env python3
"""Run the opt-in expanded exploratory paired bolus experiment.

Strict dataset identity verification remains the default.  The only supported
override is the explicitly authorized, exact expected/actual SHA-256 pair
recorded below; every other checkpoint, schema, split, simulator, source, and
pairing check remains active.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch


AUTHORIZED_EXPECTED_DATASET_SHA256 = (
    "95b201c80404e692bffb3e7b7084ae2b868f849df70bbf9712f7402e747b3d1d"
)
AUTHORIZED_ACTUAL_DATASET_SHA256 = (
    "21e9fd901fb60d9cca01dd6561d82cc9927ff0b03882ef42cac55868790f4017"
)
RUN_LABEL = "EXPLORATORY_WITH_DATASET_HASH_MISMATCH"
ARMS = ("recorded_bolus_baseline", "optimized_bolus")
METRICS = (
    "time_in_range_pct", "below_70_pct", "below_54_pct",
    "above_180_pct", "above_250_pct", "mean_glucose_mg_dl",
    "total_bolus_u",
)


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True
    ).strip()


def json_dump(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


class PartitionWriter:
    def __init__(self, root: Path):
        self.root = root
        self.buffers: dict[str, list[dict]] = defaultdict(list)
        self.parts: Counter[str] = Counter()

    def add(self, name: str, rows: list[dict]) -> None:
        self.buffers[name].extend(rows)

    def flush(self) -> None:
        for name, rows in list(self.buffers.items()):
            if not rows:
                continue
            directory = self.root / name
            directory.mkdir(parents=True, exist_ok=True)
            part = self.parts[name]
            pd.DataFrame(rows).to_parquet(
                directory / f"part-{part:05d}.parquet", index=False
            )
            self.parts[name] += 1
            self.buffers[name] = []


def metric_row(episode_id: str, dataset: str, patient_id: str, split: str,
               arm: str, glucose: np.ndarray, bolus_u: float) -> dict:
    if glucose.shape != (288,) or not np.isfinite(glucose).all():
        raise ValueError(
            f"{episode_id}/{arm}: expected 288 finite committed glucose values, "
            f"got {glucose.shape}"
        )
    return {
        "episode_id": episode_id,
        "dataset": dataset,
        "patient_id": patient_id,
        "patient_key": f"{dataset}::{patient_id}",
        "split": split,
        "arm": arm,
        "time_in_range_pct": float(np.mean((glucose >= 70) & (glucose <= 180)) * 100),
        "below_70_pct": float(np.mean(glucose < 70) * 100),
        "below_54_pct": float(np.mean(glucose < 54) * 100),
        "above_180_pct": float(np.mean(glucose > 180) * 100),
        "above_250_pct": float(np.mean(glucose > 250) * 100),
        "mean_glucose_mg_dl": float(np.mean(glucose)),
        "total_bolus_u": float(bolus_u),
        "glucose_sample_count": 288,
    }


def run_set(
    definitions,
    groups,
    frozen,
    policy,
    search,
    scoring,
    search_hash: str,
    output: Path,
    *,
    weight_kg: float,
    substeps: int,
    flush_every: int,
):
    from bolus_optimization.episodes import initialize_episode, mutable_storage_is_independent
    from bolus_optimization.run_paired_episodes import run_paired_episode
    from bolus_optimization.verify_history_updates import (
        _flatten_refresh, verify_arm_refresh_schedule,
    )

    output.mkdir(parents=True, exist_ok=True)
    writer = PartitionWriter(output)
    metrics: list[dict] = []
    checks: list[dict] = []
    failures: list[dict] = []
    started = time.perf_counter()
    upper_boundary = recommendations = 0
    candidate_inventory_checks = 0
    weighted_insulin_nonzero = 0
    order_failures = 0
    event_counts: Counter[str] = Counter()

    for index, definition in enumerate(definitions, 1):
        key = (definition.dataset, definition.patient_id)
        try:
            episode = initialize_episode(
                groups[key], definition, frozen,
                weight_kg=weight_kg, substeps=substeps,
            )
            if episode.initialization_status != "initialized":
                failures.append({
                    "episode_id": definition.episode_id,
                    "stage": "initialization",
                    "arm": "pair",
                    "reason": str(episode.failure),
                })
                checks.append({
                    "episode_id": definition.episode_id,
                    "dataset": definition.dataset,
                    "patient_id": definition.patient_id,
                    "split": definition.split,
                    "both_complete": False,
                    "failure_stage": "initialization",
                })
                continue

            initialized_equal = all(torch.equal(
                getattr(episode.baseline_arm, name),
                getattr(episode.optimized_arm, name),
            ) for name in ("physiological_state", "parameters"))
            storage_independent = mutable_storage_is_independent(episode)
            run = run_paired_episode(
                episode, frozen, policy.trigger, policy.consumption,
                search, scoring, policy.refresh,
                weight_kg=weight_kg, substeps=substeps,
                search_configuration_hash=search_hash,
            )

            episode_status = {row["arm"]: row for row in run.episode_rows}
            both_complete = all(
                episode_status.get(arm, {}).get("status") == "completed"
                and int(episode_status.get(arm, {}).get("completed_intervals", -1)) == 288
                for arm in ARMS
            )
            inputs = pd.DataFrame(run.input_rows)
            shared_equal = False
            if len(inputs):
                left = inputs[inputs.arm == ARMS[0]].sort_values("interval_index")
                right = inputs[inputs.arm == ARMS[1]].sort_values("interval_index")
                shared = [
                    "interval_start_timestamp", "basal_rate_u_per_hour",
                    "consumed_carbs_g", "announced_carbs_g",
                ]
                shared_equal = (
                    len(left) == len(right) == 288
                    and left[shared].reset_index(drop=True).equals(
                        right[shared].reset_index(drop=True)
                    )
                )
            schedules = [
                verify_arm_refresh_schedule(
                    arm, policy.refresh, definition.end_timestamp
                ) for arm in (episode.baseline_arm, episode.optimized_arm)
            ]
            schedule_pass = all(item["ordered_exact_match"] for item in schedules)
            refresh_equal = tuple(
                x["scheduled_offset_minutes"] for x in episode.baseline_arm.refresh_log
            ) == tuple(
                x["scheduled_offset_minutes"] for x in episode.optimized_arm.refresh_log
            )
            order_pass = all(row["boundary_order_pass"] for row in run.order_rows)
            order_failures += sum(not row["boundary_order_pass"] for row in run.order_rows)
            pair_pass = all((
                initialized_equal, storage_independent, shared_equal,
                schedule_pass, refresh_equal, order_pass, both_complete,
            ))
            checks.append({
                "episode_id": definition.episode_id,
                "dataset": definition.dataset,
                "patient_id": definition.patient_id,
                "split": definition.split,
                "initialization_equal": initialized_equal,
                "mutable_storage_independent": storage_independent,
                "shared_exogenous_inputs_equal": shared_equal,
                "shared_refresh_offsets_equal": refresh_equal,
                "strict_refresh_schedule_pass": schedule_pass,
                "boundary_order_pass": order_pass,
                "both_complete": both_complete,
                "pair_verification_pass": pair_pass,
            })

            if run.failure_rows:
                failures.extend({"stage": "episode", **row} for row in run.failure_rows)
            if pair_pass:
                trajectory = pd.DataFrame(run.trajectory_rows)
                for arm in ARMS:
                    committed = trajectory[
                        (trajectory.arm == arm)
                        & (trajectory.completed_episode_intervals > 0)
                    ].sort_values("completed_episode_intervals")
                    arm_inputs = inputs[inputs.arm == arm]
                    metrics.append(metric_row(
                        definition.episode_id, definition.dataset,
                        definition.patient_id, definition.split, arm,
                        committed.glucose_mg_dl.to_numpy(dtype=float),
                        float(arm_inputs.delivered_bolus_u.sum()),
                    ))

            for row in run.recommendation_rows:
                recommendations += 1
                upper_boundary += int(bool(row["selected_at_upper_grid_boundary"]))
            for row in run.score_rows:
                candidate_inventory_checks += 1
                weighted = row.get("weighted_insulin")
                if weighted is not None and not pd.isna(weighted) and float(weighted) != 0.0:
                    weighted_insulin_nonzero += 1
            for row in run.event_rows:
                if row["event_type"] is not None:
                    event_counts[f"{row['arm']}:{row['event_type']}"] += 1

            writer.add("raw_glucose_trajectories", run.trajectory_rows)
            writer.add("applied_interval_inputs", run.input_rows)
            writer.add("decision_log", run.recommendation_rows)
            writer.add("actual_bolus_deliveries", run.delivery_rows)
            writer.add("candidate_scores", run.score_rows)
            writer.add("candidate_rejections", run.rejection_rows)
            writer.add(
                "event_log",
                [row for row in run.event_rows if row["event_type"] is not None],
            )
            refresh_rows = []
            for arm in (episode.baseline_arm, episode.optimized_arm):
                refresh_rows.extend(
                    _flatten_refresh(definition, arm, row) for row in arm.refresh_log
                )
            writer.add("parameter_refresh_log", refresh_rows)
        except Exception as error:
            failures.append({
                "episode_id": definition.episode_id,
                "dataset": definition.dataset,
                "patient_id": definition.patient_id,
                "split": definition.split,
                "stage": "runner_exception",
                "arm": "pair",
                "reason": f"{type(error).__name__}:{error}",
            })
            checks.append({
                "episode_id": definition.episode_id,
                "dataset": definition.dataset,
                "patient_id": definition.patient_id,
                "split": definition.split,
                "both_complete": False,
                "pair_verification_pass": False,
                "failure_stage": "runner_exception",
            })

        if index % flush_every == 0:
            writer.flush()
            elapsed = time.perf_counter() - started
            rate = index / elapsed if elapsed else 0.0
            remaining = (len(definitions) - index) / rate if rate else float("inf")
            print(
                f"progress {index}/{len(definitions)} episodes; "
                f"elapsed={elapsed:.1f}s; eta={remaining:.1f}s; failures={len(failures)}",
                flush=True,
            )
    writer.flush()

    metric_frame = pd.DataFrame(metrics)
    check_frame = pd.DataFrame(checks)
    failure_frame = pd.DataFrame(failures)
    metric_frame.to_csv(output / "per_episode_metrics.csv", index=False)
    check_frame.to_csv(output / "pair_verification.csv", index=False)
    failure_frame.to_csv(output / "failures.csv", index=False)
    summary = {
        "episodes_attempted": len(definitions),
        "matched_complete_pairs": int(
            metric_frame.episode_id.nunique() if len(metric_frame) else 0
        ),
        "failures": len(failures),
        "pair_verification_failures": int(
            (~check_frame.get("pair_verification_pass", pd.Series(dtype=bool)).fillna(False)).sum()
        ),
        "recommendations": recommendations,
        "upper_grid_boundary_selections": upper_boundary,
        "upper_grid_boundary_selection_frequency": (
            upper_boundary / recommendations if recommendations else 0.0
        ),
        "candidate_score_rows": candidate_inventory_checks,
        "weighted_insulin_nonzero_rows": weighted_insulin_nonzero,
        "boundary_order_failures": order_failures,
        "event_counts": dict(event_counts),
        "runtime_seconds": time.perf_counter() - started,
        "partition_counts": dict(writer.parts),
    }
    summary["pass"] = bool(
        summary["matched_complete_pairs"] == len(definitions)
        and summary["failures"] == 0
        and summary["pair_verification_failures"] == 0
        and weighted_insulin_nonzero == 0
        and order_failures == 0
    )
    json_dump(output / "run_summary.json", summary)
    return summary, metric_frame, check_frame, failure_frame


def make_table(summary_rows: list[dict]) -> tuple[str, list[dict]]:
    labels = {
        "time_in_range_pct": "Time in range: 70–180 mg/dL",
        "below_70_pct": "Below 70 mg/dL",
        "below_54_pct": "Below 54 mg/dL",
        "above_180_pct": "Above 180 mg/dL",
        "above_250_pct": "Above 250 mg/dL",
        "mean_glucose_mg_dl": "Mean glucose",
        "total_bolus_u": "Mean bolus insulin per episode",
    }
    units = {
        "time_in_range_pct": ("%", "pp"),
        "below_70_pct": ("%", "pp"),
        "below_54_pct": ("%", "pp"),
        "above_180_pct": ("%", "pp"),
        "above_250_pct": ("%", "pp"),
        "mean_glucose_mg_dl": (" mg/dL", " mg/dL"),
        "total_bolus_u": (" U", " U"),
    }
    by_metric = {row["metric_key"]: row for row in summary_rows}
    lines = [
        "| Metric | Recorded-bolus baseline | Optimizer | Change |",
        "|---|---:|---:|---:|",
    ]
    for key in METRICS:
        row = by_metric[key]
        value_unit, change_unit = units[key]
        lines.append(
            f"| {labels[key]} | {row['recorded_bolus_baseline']:.3f}{value_unit} "
            f"| {row['optimizer']:.3f}{value_unit} "
            f"| {row['change']:+.3f} {change_unit.strip()} |"
        )
    return "\n".join(lines), summary_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--checkpoint", default="services/prediction/baseline/model.pt")
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-dataset-hash-mismatch", action="store_true")
    parser.add_argument("--flush-every", type=int, default=25)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    dataset = (repo / args.dataset).resolve() if not Path(args.dataset).is_absolute() else Path(args.dataset).resolve()
    checkpoint = (repo / args.checkpoint).resolve() if not Path(args.checkpoint).is_absolute() else Path(args.checkpoint).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    prediction = repo / "services/prediction"
    sys.path.insert(0, str(prediction))
    os.chdir(prediction)

    from final_model_adapter import sha256, verify_dataset
    from bolus_optimization.candidate_search import (
        BolusSearchConfiguration, generate_bolus_candidates,
    )
    from bolus_optimization.checkpoint import load_frozen_gru
    from bolus_optimization.configuration import FROZEN_CHECKPOINT_SHA256
    from bolus_optimization.data import read_optimization_data
    from bolus_optimization.episodes import (
        ALLOWED_SPLITS, EXPECTED_SOURCE_HASHES, RELEVANT_SOURCE_FILES,
        build_episode_definitions,
    )
    from bolus_optimization.migrated_configuration import load_migrated_configuration
    from bolus_optimization.scoring import (
        ScoringConfiguration, calculate_score_components,
    )

    started_utc = datetime.now(timezone.utc).isoformat()
    branch = git(repo, "branch", "--show-current")
    commit = git(repo, "rev-parse", "HEAD")
    status_at_execution = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if branch != "mariam":
        raise RuntimeError(f"Required branch mariam, found {branch}")

    frozen = load_frozen_gru(checkpoint, expected_sha256=FROZEN_CHECKPOINT_SHA256)
    actual_dataset_hash = sha256(dataset)
    expected_dataset_hash = str(frozen.checkpoint["data_sha256"])
    mismatch = actual_dataset_hash != expected_dataset_hash
    if mismatch:
        if not args.allow_dataset_hash_mismatch:
            verify_dataset(dataset, frozen.checkpoint)
        if (
            expected_dataset_hash != AUTHORIZED_EXPECTED_DATASET_SHA256
            or actual_dataset_hash != AUTHORIZED_ACTUAL_DATASET_SHA256
        ):
            raise ValueError(
                "Dataset mismatch is not the specifically authorized expected/actual pair"
            )
    else:
        verify_dataset(dataset, frozen.checkpoint)

    data, patient_splits, loader_audit = read_optimization_data(dataset)
    if patient_splits != frozen.checkpoint["patient_splits"]:
        raise ValueError("Patient splits differ from the frozen checkpoint")
    if set(data.loc[data.split.isin(ALLOWED_SPLITS), "split"]) - set(ALLOWED_SPLITS):
        raise ValueError("Unexpected split entered development/validation data")

    source_hashes = {path: sha256(path) for path in RELEVANT_SOURCE_FILES}
    preserved = {
        path: source_hashes[path] == expected
        for path, expected in EXPECTED_SOURCE_HASHES.items()
    }
    if not all(preserved.values()):
        raise ValueError(f"Protected source integrity failed: {preserved}")

    policy_path = prediction / "bolus_optimization/migrated_selected_configuration.json"
    spec_path = prediction / "bolus_optimization/expanded_20u_no_insulin_penalty_v1.json"
    policy = load_migrated_configuration(policy_path)
    spec = json.loads(spec_path.read_text())
    search_payload = dataclasses.asdict(policy.search)
    search_payload.update({
        "configuration_version": spec["configuration_version"],
        "maximum_bolus_u": spec["maximum_bolus_u"],
        "bolus_increment_u": spec["bolus_increment_u"],
        "maximum_candidate_count": spec["maximum_candidate_count"],
        "candidate_batch_size": spec["candidate_batch_size"],
        "intended_use": spec["intended_use"],
    })
    scoring_payload = dataclasses.asdict(policy.scoring)
    scoring_payload["insulin_weight"] = spec["insulin_weight"]
    search = BolusSearchConfiguration(**search_payload)
    scoring = ScoringConfiguration(**scoring_payload)
    candidates = generate_bolus_candidates(search)
    doses = [item.bolus_u for item in candidates]
    if doses != [index * 0.5 for index in range(41)]:
        raise ValueError(f"Expanded candidate grid is incorrect: {doses}")
    synthetic = torch.full((48,), 200.0, dtype=torch.float32)
    score_probe = calculate_score_components(synthetic, 20.0, scoring)
    if scoring.insulin_weight != 0.0 or score_probe.weighted_insulin != 0.0:
        raise ValueError("Zero insulin penalty did not reach score calculation")
    search_hash = canonical_hash(search_payload)

    effective = {
        "run_label": RUN_LABEL,
        "migrated_policy_sha256": policy.sha256,
        "expanded_spec_path": str(spec_path),
        "expanded_spec_sha256": sha256(spec_path),
        "trigger": dataclasses.asdict(policy.trigger),
        "consumption": dataclasses.asdict(policy.consumption),
        "refresh": dataclasses.asdict(policy.refresh),
        "search": search_payload,
        "scoring": scoring_payload,
        "simulator": policy.source_payload["simulator"],
        "residual": policy.source_payload["residual"],
        "candidate_doses_u": doses,
        "candidate_count": len(doses),
        "search_configuration_canonical_sha256": search_hash,
        "experimental_search_bound_notice": (
            "20 U is an experimental search bound, not a validated safe-dose limit."
        ),
    }
    json_dump(output / "effective_configuration.json", effective)
    json_dump(output / "candidate_grid_verification.json", {
        "pass": True,
        "candidate_count": len(doses),
        "minimum_u": min(doses),
        "maximum_u": max(doses),
        "increment_u": 0.5,
        "doses_u": doses,
        "insulin_weight": scoring.insulin_weight,
        "score_probe_20u_insulin_component": score_probe.insulin_component,
        "score_probe_20u_weighted_insulin": score_probe.weighted_insulin,
        "raw_hovorka_trajectory_scoring": True,
        "gated_correction_enabled": False,
        "residual_correction_enabled": False,
    })

    all_definitions = build_episode_definitions(data)
    eligible = [item for item in all_definitions if item.eligible]
    if any(item.split == "testing" for item in all_definitions):
        raise ValueError("Testing episode entered eligible inventory")
    groups = {
        (str(ds), str(patient)): group.sort_values("timestamp").reset_index(drop=True)
        for (ds, patient), group in data[data.split.isin(ALLOWED_SPLITS)].groupby(
            ["dataset", "patient_id"], sort=False
        )
    }
    smoke_definitions = []
    seen = set()
    for item in eligible:
        key = (item.dataset, item.patient_id)
        if key not in seen:
            smoke_definitions.append(item)
            seen.add(key)
    print(f"smoke_start episodes={len(smoke_definitions)}", flush=True)
    smoke_summary, _, _, _ = run_set(
        smoke_definitions, groups, frozen, policy, search, scoring, search_hash,
        output / "smoke", weight_kg=70.0, substeps=5,
        flush_every=max(1, args.flush_every),
    )
    if not smoke_summary["pass"]:
        raise RuntimeError(f"Smoke check failed: {smoke_summary}")
    print("smoke_pass", flush=True)

    print(f"full_start episodes={len(eligible)}", flush=True)
    full_summary, episode_metrics, pair_checks, failure_frame = run_set(
        eligible, groups, frozen, policy, search, scoring, search_hash,
        output / "full", weight_kg=70.0, substeps=5,
        flush_every=max(1, args.flush_every),
    )

    matched_ids = set(
        pair_checks.loc[
            pair_checks.get("pair_verification_pass", pd.Series(dtype=bool)).fillna(False),
            "episode_id",
        ]
    )
    episode_metrics = episode_metrics[episode_metrics.episode_id.isin(matched_ids)].copy()
    counts_per_episode = episode_metrics.groupby("episode_id").arm.nunique()
    matched_ids = set(counts_per_episode[counts_per_episode == 2].index)
    episode_metrics = episode_metrics[episode_metrics.episode_id.isin(matched_ids)].copy()
    episode_metrics.to_csv(output / "per_episode_metrics.csv", index=False)

    patient_metrics = (
        episode_metrics.groupby(
            ["dataset", "patient_id", "patient_key", "split", "arm"],
            as_index=False,
        )[list(METRICS)].mean()
    )
    patient_metrics.to_csv(output / "per_patient_metrics.csv", index=False)
    patient_arm_counts = patient_metrics.groupby("arm").patient_key.nunique().to_dict()
    if patient_arm_counts.get(ARMS[0]) != patient_arm_counts.get(ARMS[1]):
        raise ValueError(f"Matched patient counts differ by arm: {patient_arm_counts}")

    arm_means = patient_metrics.groupby("arm")[list(METRICS)].mean()
    summary_rows = []
    for metric in METRICS:
        baseline = float(arm_means.loc[ARMS[0], metric])
        optimizer = float(arm_means.loc[ARMS[1], metric])
        summary_rows.append({
            "metric_key": metric,
            "recorded_bolus_baseline": baseline,
            "optimizer": optimizer,
            "change": optimizer - baseline,
        })
    pd.DataFrame(summary_rows).to_csv(output / "summary.csv", index=False)
    table, _ = make_table(summary_rows)

    definition_rows = []
    checks_by_id = pair_checks.set_index("episode_id").to_dict("index") if len(pair_checks) else {}
    for item in all_definitions:
        check = checks_by_id.get(item.episode_id, {})
        definition_rows.append({
            **dataclasses.asdict(item),
            "inventory_status": (
                "excluded_incomplete_final_episode" if not item.eligible
                else "matched_complete" if item.episode_id in matched_ids
                else "attempted_incomplete_or_failed"
            ),
            "pair_verification_pass": check.get("pair_verification_pass"),
        })
    inventory = pd.DataFrame(definition_rows)
    inventory.to_csv(output / "episode_inventory.csv", index=False)
    excluded = inventory[~inventory.eligible]
    attempted_incomplete = inventory[
        inventory.eligible & ~inventory.episode_id.isin(matched_ids)
    ]
    excluded.to_csv(output / "exclusions.csv", index=False)
    attempted_incomplete.to_csv(output / "incomplete_pairs.csv", index=False)
    failure_frame.to_csv(output / "failures.csv", index=False)

    matched = inventory[inventory.episode_id.isin(matched_ids)]
    split_counts = matched.groupby("split").episode_id.nunique().to_dict()
    patient_count = int(patient_metrics.patient_key.nunique())
    matched_episode_count = len(matched_ids)
    full_completed = bool(
        full_summary["pass"]
        and matched_episode_count == len(eligible)
        and len(attempted_incomplete) == 0
    )
    metrics_payload = {
        "run_label": RUN_LABEL,
        "aggregation": (
            "episode metrics averaged within each patient, then patients weighted equally"
        ),
        "change_direction": "optimizer_minus_recorded_bolus_baseline",
        "full_precision": summary_rows,
        "patient_count": patient_count,
        "matched_episode_count": matched_episode_count,
        "split_counts": split_counts,
        "eligible_episode_count": len(eligible),
        "excluded_episode_count": len(excluded),
        "incomplete_pair_count": len(attempted_incomplete),
        "failure_count": len(failure_frame),
        "full_run_completed": full_completed,
        "upper_grid_boundary_selections": full_summary["upper_grid_boundary_selections"],
        "optimizer_recommendations": full_summary["recommendations"],
        "upper_grid_boundary_selection_frequency": full_summary[
            "upper_grid_boundary_selection_frequency"
        ],
    }
    json_dump(output / "metrics.json", metrics_payload)

    command = shlex.join([sys.executable, *sys.argv])
    (output / "execution_command.txt").write_text(command + "\n")
    provenance = {
        "run_label": RUN_LABEL,
        "started_utc": started_utc,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "repository": str(repo),
        "branch": branch,
        "commit": commit,
        "worktree_status_at_execution": status_at_execution,
        "dataset": str(dataset),
        "dataset_sha256_actual": actual_dataset_hash,
        "dataset_sha256_checkpoint_expected": expected_dataset_hash,
        "dataset_hash_mismatch": mismatch,
        "dataset_hash_mismatch_override_requested": args.allow_dataset_hash_mismatch,
        "dataset_hash_mismatch_override_applied": mismatch and args.allow_dataset_hash_mismatch,
        "dataset_compatibility_status": "unverified_due_to_authorized_hash_mismatch",
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": frozen.checkpoint_sha256,
        "checkpoint_integrity_pass": frozen.checkpoint_sha256 == FROZEN_CHECKPOINT_SHA256,
        "patient_splits_match_checkpoint": True,
        "testing_patients_used": False,
        "protected_source_integrity": preserved,
        "source_hashes": source_hashes,
        "loader_audit": loader_audit,
        "python": sys.version,
        "torch": torch.__version__,
        "pandas": pd.__version__,
    }
    json_dump(output / "provenance.json", provenance)

    interpretation = (
        "Positive changes mean the optimizer produced more of that metric; for below/above-range "
        "metrics, positive changes indicate more time outside the stated threshold."
    )
    results_md = "\n".join([
        f"# {RUN_LABEL}", "",
        "These are exploratory internal Hovorka simulation results. Model compatibility with "
        "the supplied dataset remains unverified because the explicitly authorized dataset-hash "
        "mismatch override was used.", "",
        table, "",
        f"Patients: **{patient_count}**", "",
        f"Matched complete 24-hour episode pairs: **{matched_episode_count}**", "",
        f"Matched episodes by split: `{json.dumps(split_counts, sort_keys=True)}`", "",
        f"Excluded incomplete episodes: **{len(excluded)}**", "",
        f"Incomplete attempted pairs: **{len(attempted_incomplete)}**", "",
        f"Failures: **{len(failure_frame)}**", "",
        f"Full run completed: **{'YES' if full_completed else 'NO'}**", "",
        f"20 U boundary selections: **{full_summary['upper_grid_boundary_selections']} / "
        f"{full_summary['recommendations']} "
        f"({100 * full_summary['upper_grid_boundary_selection_frequency']:.3f}%)**", "",
        interpretation, "",
        f"Expected dataset SHA-256: `{expected_dataset_hash}`", "",
        f"Actual dataset SHA-256: `{actual_dataset_hash}`", "",
        "Override label: `EXPLORATORY_WITH_DATASET_HASH_MISMATCH`", "",
        "The 20 U maximum is an experimental search bound, not a validated safe-dose limit.", "",
    ])
    (output / "RESULTS.md").write_text(results_md)

    status = {
        "run_label": RUN_LABEL,
        "smoke_pass": smoke_summary["pass"],
        "full_run_completed": full_completed,
        "full_summary": full_summary,
    }
    json_dump(output / "status.json", status)
    archive_temp = shutil.make_archive(
        str(output.parent / f"{output.name}_report_and_supporting_outputs"),
        "zip", root_dir=output,
    )
    archive_path = output / Path(archive_temp).name
    shutil.move(archive_temp, archive_path)
    print(json.dumps({
        "output": str(output),
        "zip": str(archive_path),
        "full_run_completed": full_completed,
        "table": table,
    }), flush=True)
    if not full_completed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
