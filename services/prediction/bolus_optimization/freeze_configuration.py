"""Step 13 bounded development/validation selection and immutable freeze bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import torch

from final_model_adapter import LOWER, UPPER, sha256, verify_dataset

from .candidate_inputs import load_consumption_configuration
from .candidate_search import BolusSearchConfiguration
from .checkpoint import load_frozen_gru
from .configuration import FROZEN_CHECKPOINT_SHA256, MODEL_FEATURES
from .data import read_optimization_data
from .episodes import build_episode_definitions, initialize_episode
from .events import TriggerConfiguration
from .outcomes import (
    acceptance_and_rank_record, arm_outcomes_from_run,
    deterministic_policy_order, paired_outcomes, patient_aggregates,
    patient_macro, verify_manifest_hashes, initialization_failure_arm_outcomes,
)
from .parameter_updates import RefreshConfiguration
from .run_paired_episodes import run_paired_episode
from .scoring import load_scoring_configuration
from .verify_candidate_search import _versions


DEFAULT_PROTOCOL = Path(
    "results/bolus_optimization_migrated_final/step13_configuration_freeze/selection_protocol.json"
)
ROOT_SOURCE_FILES = (
    "final_model_adapter.py", "optimize.py", "test.py", "environment.json",
)


def runtime_dependency_files(root: str | Path = ".") -> tuple[str, ...]:
    """Return every local file needed to import and configure the frozen runner."""

    root = Path(root)
    package = root / "bolus_optimization"
    package_files = sorted(
        path.relative_to(root).as_posix()
        for pattern in ("*.py", "*.json")
        for path in package.glob(pattern)
        if path.is_file()
    )
    files = [name for name in ROOT_SOURCE_FILES if (root / name).is_file()]
    files.extend(package_files)
    return tuple(dict.fromkeys(files))


def _configurations(protocol):
    _, base_scoring_hash = load_scoring_configuration()
    base_scoring, _ = load_scoring_configuration()
    result = {}
    for item in protocol["predeclared_configurations"]:
        trigger = item["trigger"]
        search = item["search"]
        result[item["configuration_id"]] = {
            "protocol_record": item,
            "trigger": TriggerConfiguration(
                f"step13-{item['configuration_id']}",
                trigger["threshold_mg_dl"], trigger["persistence_minutes"],
                trigger["reassessment_minutes"],
                "Predeclared Step 13 experimental research trigger.",
            ),
            "search": BolusSearchConfiguration(
                f"step13-{item['configuration_id']}",
                search["maximum_bolus_u"], search["increment_u"],
                search["maximum_candidate_count"], search["candidate_batch_size"],
                "Predeclared Step 13 experimental research dose grid; not a safe limit.",
            ),
            "scoring": replace(base_scoring, **item["score_overrides"]),
            "reference_scoring_configuration_sha256": base_scoring_hash,
        }
    return result


def _definition_inventory(definitions, selected_ids):
    return pd.DataFrame([{
        "episode_id": item.episode_id, "dataset": item.dataset,
        "patient_id": item.patient_id, "split": item.split,
        "start_timestamp": item.start_timestamp, "end_timestamp": item.end_timestamp,
        "eligible": item.eligible,
        "selected": item.episode_id in selected_ids,
        "status": (
            "selected" if item.episode_id in selected_ids
            else "excluded_incomplete_final_episode" if not item.eligible
            else "not_selected_by_predeclared_stage_rule"
        ),
        "omission_reason": item.omission_reason,
    } for item in definitions])


def _save_results(directory, inventory, arm_frame, pair_frame, patient_frame, record):
    directory.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(directory / "episode_inventory.csv", index=False)
    arm_frame.to_csv(directory / "arm_outcomes.csv", index=False)
    pair_frame.to_csv(directory / "paired_episode_outcomes.csv", index=False)
    patient_frame.to_csv(directory / "patient_aggregates.csv", index=False)
    (directory / "aggregate.json").write_text(
        json.dumps(record, indent=2, default=str) + "\n"
    )


def _unique_failure_rows(rows, definitions, incomplete_pairs):
    """Normalize failures and count one copy of each episode/arm failure."""

    by_id = {item.episode_id: item for item in definitions}
    normalized = []
    for raw in rows:
        item = by_id[raw["episode_id"]]
        normalized.append({
            "episode_id": item.episode_id,
            "dataset": item.dataset,
            "patient_id": item.patient_id,
            "split": item.split,
            "arm": raw.get("arm", "pair"),
            "stopping_boundary": raw.get("stopping_boundary", item.start_timestamp),
            "failure_reason": str(raw.get("failure_reason", "unspecified_failure")),
        })
    represented = {row["episode_id"] for row in normalized}
    for episode_id in sorted(incomplete_pairs - represented):
        item = by_id[episode_id]
        normalized.append({
            "episode_id": episode_id, "dataset": item.dataset,
            "patient_id": item.patient_id, "split": item.split, "arm": "pair",
            "stopping_boundary": item.start_timestamp,
            "failure_reason": "incomplete_pair_without_detailed_failure",
        })
    unique = {}
    for row in normalized:
        key = (
            row["episode_id"], row["arm"], str(row["stopping_boundary"]),
            row["failure_reason"],
        )
        unique.setdefault(key, row)
    return list(unique.values())


def summarize_configuration_attempts(
    configuration_id, definitions, arm_frame, failure_rows, criteria,
):
    """Aggregate every requested episode, including pre-arm failures."""

    pair_frame = paired_outcomes(arm_frame)
    patient_frame = patient_aggregates(pair_frame)
    macro = patient_macro(patient_frame)
    if macro["attempted_episode_count"] != len(definitions):
        raise RuntimeError("Every requested episode must be retained as attempted")
    optimized = arm_frame[arm_frame["arm"] == "optimized_bolus"]
    recommendation_count = int(optimized["recommendation_count"].sum())
    no_feasible_count = int(optimized["no_feasible_count"].sum())
    upper_count = int(optimized["upper_grid_selection_count"].sum())
    incomplete_pairs = set(pair_frame.loc[~pair_frame["complete_pair"], "episode_id"])
    unique_failures = _unique_failure_rows(failure_rows, definitions, incomplete_pairs)
    record = acceptance_and_rank_record(
        configuration_id, macro, patient_frame,
        failure_count=len(unique_failures),
        recommendation_count=recommendation_count,
        no_feasible_count=no_feasible_count,
        upper_grid_count=upper_count, criteria=criteria,
    )
    record.update({
        "requested_episode_count": len(definitions),
        "failed_episode_count": len(incomplete_pairs),
        "unique_failure_record_count": len(unique_failures),
    })
    return pair_frame, patient_frame, record, unique_failures


def _run_configuration(
    configuration_id,
    configuration,
    definitions,
    all_stage_definitions,
    groups,
    frozen,
    consumption,
    refresh,
    criteria,
    output_directory,
    *,
    weight_kg,
    substeps,
):
    started = time.perf_counter()
    arm_frames, failure_rows = [], []
    for definition in definitions:
        episode = initialize_episode(
            groups[(definition.dataset, definition.patient_id)], definition, frozen,
            weight_kg=weight_kg, substeps=substeps,
        )
        if episode.initialization_status != "initialized":
            arm_frames.append(initialization_failure_arm_outcomes(
                definition, str(episode.failure)
            ))
            failure_rows.append({
                "episode_id": definition.episode_id,
                "arm": "pair",
                "stopping_boundary": definition.start_timestamp,
                "failure_reason": str(episode.failure),
            })
            continue
        run = run_paired_episode(
            episode, frozen, configuration["trigger"], consumption,
            configuration["search"], configuration["scoring"], refresh,
            weight_kg=weight_kg, substeps=substeps,
        )
        arm = arm_outcomes_from_run(run)
        # Retain refresh-transition magnitude for deterministic plot routing.
        for simulated_arm in (episode.baseline_arm, episode.optimized_arm):
            changes = [
                max(value for value in entry["relative_changes"].values() if value is not None)
                for entry in simulated_arm.refresh_log
                if entry["status"] == "refreshed"
            ]
            mask = arm["arm"] == simulated_arm.arm_name
            arm.loc[mask, "maximum_relative_parameter_change"] = max(changes, default=0.0)
        arm_frames.append(arm)
        failure_rows.extend(run.failure_rows)
    arm_frame = pd.concat(arm_frames, ignore_index=True) if arm_frames else pd.DataFrame()
    pair_frame, patient_frame, record, failure_rows = summarize_configuration_attempts(
        configuration_id, definitions, arm_frame, failure_rows, criteria,
    )
    record.update({
        "runtime_seconds": time.perf_counter() - started,
        "configuration": {
            "trigger": asdict(configuration["trigger"]),
            "search": asdict(configuration["search"]),
            "scoring": asdict(configuration["scoring"]),
        },
        "outcome_label": "discrete Hovorka-simulated outcomes",
        "difference_direction": "optimized minus baseline",
    })
    inventory = _definition_inventory(
        all_stage_definitions, {item.episode_id for item in definitions}
    )
    _save_results(
        output_directory, inventory, arm_frame, pair_frame, patient_frame, record
    )
    pd.DataFrame(failure_rows, columns=(
        "episode_id", "dataset", "patient_id", "split", "arm",
        "stopping_boundary", "failure_reason",
    )).to_csv(output_directory / "failures.csv", index=False)
    return record, arm_frame, pair_frame, patient_frame


def _first_per_patient(definitions):
    selected, seen = [], set()
    for item in definitions:
        if not item.eligible:
            continue
        key = (item.dataset, item.patient_id)
        if key not in seen:
            selected.append(item); seen.add(key)
    return selected


def _git_state(root):
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"], cwd=root,
            capture_output=True, text=True, check=False,
        )
        if inside.returncode != 0:
            return {"available": False, "reason": "not_a_git_worktree"}
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True)
        return {"available": True, "commit": commit, "working_tree_status": status}
    except Exception as error:
        return {"available": False, "reason": f"git_query_failed:{type(error).__name__}:{error}"}


def _plot_episode(run, definition, output_path, title):
    trajectories = pd.DataFrame(run.trajectory_rows)
    inputs = pd.DataFrame(run.input_rows)
    events = pd.DataFrame(run.event_rows)
    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)
    for arm, color in (("recorded_bolus_baseline", "#555555"), ("optimized_bolus", "#1565c0")):
        frame = trajectories[trajectories.arm == arm]
        axes[0].plot(frame.boundary_timestamp, frame.glucose_mg_dl, label=arm, color=color)
    axes[0].axhspan(70, 180, color="#66bb6a", alpha=.12)
    axes[0].axhline(54, color="#c62828", linestyle="--", linewidth=.8)
    axes[0].set_ylabel("Glucose mg/dL"); axes[0].legend(loc="upper right")
    for arm, color, offset in (("recorded_bolus_baseline", "#555555", -.8), ("optimized_bolus", "#1565c0", .8)):
        frame = inputs[inputs.arm == arm]
        axes[1].vlines(frame.interval_start_timestamp, offset, frame.delivered_bolus_u + offset,
                       color=color, alpha=.75, label=arm)
    axes[1].set_ylabel("Bolus U"); axes[1].legend(loc="upper right")
    shared = inputs[inputs.arm == "recorded_bolus_baseline"]
    axes[2].step(shared.interval_start_timestamp, shared.basal_rate_u_per_hour,
                 where="post", label="basal U/hour", color="#6a1b9a")
    axes[2].vlines(shared.interval_start_timestamp, 0, shared.announced_carbs_g,
                   color="#ef6c00", alpha=.65, label="announced g")
    axes[2].vlines(shared.interval_start_timestamp, 0, -shared.consumed_carbs_g,
                   color="#00897b", alpha=.65, label="consumed g")
    axes[2].set_ylabel("Inputs"); axes[2].legend(loc="upper right", ncol=3)
    optimized_events = events[(events.arm == "optimized_bolus") & events.evaluation_eligible]
    axes[3].scatter(optimized_events.decision_timestamp, optimized_events.glucose_mg_dl,
                    marker="x", color="#d32f2f", label="decisions")
    for arm, color in ((run.episode.baseline_arm, "#555555"), (run.episode.optimized_arm, "#1565c0")):
        timestamps = [entry["refresh_timestamp"] for entry in arm.refresh_log]
        changes = [max(entry["relative_changes"].values()) for entry in arm.refresh_log]
        axes[3].plot(timestamps, changes, marker="o", color=color, label=f"{arm.arm_name} max relative parameter change")
    axes[3].set_ylabel("Events / parameter Δ"); axes[3].legend(loc="upper right")
    axes[3].set_xlabel("Boundary timestamp")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(output_path, dpi=140)
    plt.close(fig)


def _diagnostic_episode_ids(pair_frame, arm_frame):
    selected = {}
    complete = pair_frame[pair_frame.complete_pair]
    for category, column, ascending in (
        ("worst_tir", "delta_time_in_range_percent", True),
        ("most_low_exposure", "optimized_below_70_percent", False),
        ("frequent_upper_grid", None, False),
    ):
        if category == "frequent_upper_grid":
            optimized = arm_frame[arm_frame.arm == "optimized_bolus"]
            row = optimized.sort_values(
                ["upper_grid_selection_count", "episode_id"], ascending=[False, True]
            ).iloc[0]
            selected[category] = row.episode_id
        elif len(complete):
            selected[category] = complete.sort_values(
                [column, "episode_id"], ascending=[ascending, True]
            ).iloc[0].episode_id
    optimized = arm_frame[arm_frame.arm == "optimized_bolus"]
    no_feasible = optimized[optimized.no_feasible_count > 0]
    if len(no_feasible):
        selected["no_feasible"] = no_feasible.sort_values("episode_id").iloc[0].episode_id
    failures = optimized[~optimized.complete]
    if len(failures):
        selected["failure"] = failures.sort_values("episode_id").iloc[0].episode_id
    large = optimized.sort_values(
        ["maximum_relative_parameter_change", "episode_id"], ascending=[False, True]
    )
    if len(large):
        selected["large_parameter_change"] = large.iloc[0].episode_id
    return selected


def _source_snapshot(root, out):
    target = out / "source_snapshot"
    target.mkdir(parents=True, exist_ok=True)
    snapshot_files = runtime_dependency_files(root)
    for relative in snapshot_files:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, destination)
    shutil.copy2(root / "README.md", target / "README.md")
    snapshot_files = (*snapshot_files, "README.md")
    hashes = {
        relative: sha256(target / relative) for relative in sorted(snapshot_files)
    }
    index_path = out / "source_snapshot_hashes.json"
    index_path.write_text(json.dumps({
        "snapshot_root": str(target),
        "file_count": len(hashes),
        "files": hashes,
    }, indent=2, sort_keys=True) + "\n")
    return target, hashes, index_path


def run_selection_and_freeze(
    dataset_path,
    checkpoint_path,
    output_directory,
    *,
    protocol_path=DEFAULT_PROTOCOL,
    weight_kg=70.0,
    substeps=5,
):
    root = Path.cwd()
    out = Path(output_directory)
    manifest_path = out / "freeze_manifest.json"
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Freeze output must be a new empty directory")
    out.mkdir(parents=True, exist_ok=True)
    source_protocol_path = Path(protocol_path)
    frozen_protocol_path = out / "selection_protocol.json"
    shutil.copy2(source_protocol_path, frozen_protocol_path)
    protocol_path = frozen_protocol_path
    protocol = json.loads(protocol_path.read_text())
    configurations = _configurations(protocol)
    consumption, consumption_hash = load_consumption_configuration()
    refresh = RefreshConfiguration(protocol["fixed_design"]["parameter_refresh_minutes"])
    data, patient_splits, loader_audit = read_optimization_data(dataset_path)
    frozen = load_frozen_gru(checkpoint_path, expected_sha256=FROZEN_CHECKPOINT_SHA256)
    verify_dataset(dataset_path, frozen.checkpoint)
    if patient_splits != frozen.checkpoint["patient_splits"]:
        raise ValueError("Patient splits differ from frozen checkpoint")
    definitions = build_episode_definitions(data)
    if any(item.split == "testing" for item in definitions):
        raise RuntimeError("Testing definitions must not enter Step 13")
    groups = {
        (str(dataset), str(patient)): group.sort_values("timestamp").reset_index(drop=True)
        for (dataset, patient), group in data[data.split.isin(("development", "validation"))].groupby(
            ["dataset", "patient_id"], sort=False
        )
    }
    development_all = [item for item in definitions if item.split == "development"]
    validation_all = [item for item in definitions if item.split == "validation"]
    development = _first_per_patient(development_all)
    validation_screen = _first_per_patient(validation_all)
    validation_complete = [item for item in validation_all if item.eligible]
    registry = []

    development_records = []
    for configuration_id, configuration in configurations.items():
        record, _, _, _ = _run_configuration(
            configuration_id, configuration, development, development_all,
            groups, frozen, consumption, refresh, protocol["acceptance_criteria"],
            out / "development_results" / configuration_id,
            weight_kg=weight_kg, substeps=substeps,
        )
        development_records.append(record)
        registry.append({
            "stage": "development_screen", "configuration_id": configuration_id,
            "patient_count": 17, "episode_count": len(development),
            "runtime_seconds": record["runtime_seconds"],
            "acceptable": record["acceptable"], "result": "completed",
        })
    comparison_tolerances = protocol["ranking"]["comparison_tolerances"]
    development_ranked = deterministic_policy_order(
        development_records, comparison_tolerances
    )
    shortlist = [item["configuration_id"] for item in development_ranked[:2]]
    measured_seconds = sum(item["runtime_seconds"] for item in development_records) / sum(
        item["attempted_episode_count"] for item in development_records
    )
    estimate = {
        "measured_development_seconds_per_episode_configuration": measured_seconds,
        "validation_shortlist_episode_configuration_runs": len(shortlist) * len(validation_screen),
        "estimated_validation_shortlist_runtime_seconds": measured_seconds * len(shortlist) * len(validation_screen),
        "selected_all_validation_episode_runs": len(validation_complete),
        "estimated_selected_all_validation_runtime_seconds": measured_seconds * len(validation_complete),
        "estimate_created_before_validation_comparisons": True,
    }
    (out / "runtime_estimate.json").write_text(json.dumps(estimate, indent=2) + "\n")

    validation_records = []
    for configuration_id in shortlist:
        record, _, _, _ = _run_configuration(
            configuration_id, configurations[configuration_id], validation_screen,
            validation_all, groups, frozen, consumption, refresh,
            protocol["acceptance_criteria"],
            out / "validation_results" / "shortlist" / configuration_id,
            weight_kg=weight_kg, substeps=substeps,
        )
        validation_records.append(record)
        registry.append({
            "stage": "validation_shortlist", "configuration_id": configuration_id,
            "patient_count": 6, "episode_count": len(validation_screen),
            "runtime_seconds": record["runtime_seconds"],
            "acceptable": record["acceptable"], "result": "completed",
        })
    validation_ranked = deterministic_policy_order(
        validation_records, comparison_tolerances
    )
    selected_id = validation_ranked[0]["configuration_id"] if validation_ranked else None
    confirmation_record = None
    confirmation_arm = confirmation_pairs = confirmation_patients = None
    if selected_id is not None:
        confirmation_record, confirmation_arm, confirmation_pairs, confirmation_patients = _run_configuration(
            selected_id, configurations[selected_id], validation_complete,
            validation_all, groups, frozen, consumption, refresh,
            protocol["acceptance_criteria"],
            out / "validation_results" / "all_eligible" / selected_id,
            weight_kg=weight_kg, substeps=substeps,
        )
        registry.append({
            "stage": "validation_all_eligible", "configuration_id": selected_id,
            "patient_count": 6, "episode_count": len(validation_complete),
            "runtime_seconds": confirmation_record["runtime_seconds"],
            "acceptable": confirmation_record["acceptable"], "result": "completed",
        })
    pd.DataFrame(registry).to_csv(out / "experiment_registry.csv", index=False)

    split_manifest = {
        "description": protocol["evaluation_description"],
        "testing_disclosure": protocol["testing_split_disclosure"],
        "patient_splits": patient_splits,
    }
    split_path = out / "patient_split_manifest.json"
    split_path.write_text(json.dumps(split_manifest, indent=2, sort_keys=True) + "\n")
    final_ready = bool(confirmation_record and confirmation_record["acceptable"])
    validation_tir_change = (
        confirmation_record["patient_macro_delta_time_in_range_percent"]
        if confirmation_record else None
    )
    readiness_meaning = (
        "READY means ready for frozen experimental evaluation; it does not mean "
        "the optimizer improved glucose control."
        + (
            f" Validation patient-macro time in range changed by "
            f"{validation_tir_change:.6f} percentage points."
            if validation_tir_change is not None else ""
        )
    )
    selected_payload = {
        "selection_status": "selected_and_validation_confirmed" if final_ready else (
            "selected_but_all_validation_not_acceptable" if selected_id else
            "no acceptable configuration under the current protocol"
        ),
        "configuration_id": selected_id,
        "configuration": (
            {
                "trigger": asdict(configurations[selected_id]["trigger"]),
                "search": asdict(configurations[selected_id]["search"]),
                "scoring": asdict(configurations[selected_id]["scoring"]),
                "consumption_configuration_path": "bolus_optimization/consumption_configuration_v1.json",
                "consumption_configuration_sha256": consumption_hash,
                "refresh": asdict(refresh),
            } if selected_id else None
        ),
        "final_testing_ready": final_ready,
        "readiness_meaning": readiness_meaning,
        "evaluation_description": protocol["evaluation_description"],
        "testing_disclosure": protocol["testing_split_disclosure"],
    }
    selected_path = out / "selected_configuration.json"
    selected_path.write_text(json.dumps(selected_payload, indent=2, default=str) + "\n")

    # Re-run only deterministically routed validation episodes for full diagnostic plots.
    plot_inventory = {}
    if selected_id is not None and confirmation_pairs is not None:
        routed = _diagnostic_episode_ids(confirmation_pairs, confirmation_arm)
        # Representative episode: first eligible episode for the lexicographically first patient.
        routed["representative"] = validation_screen[0].episode_id
        by_id = {item.episode_id: item for item in validation_complete}
        plot_dir = out / "diagnostic_plots"; plot_dir.mkdir(parents=True, exist_ok=True)
        for category, episode_id in routed.items():
            definition = by_id[episode_id]
            episode = initialize_episode(
                groups[(definition.dataset, definition.patient_id)], definition, frozen,
                weight_kg=weight_kg, substeps=substeps,
            )
            run = run_paired_episode(
                episode, frozen, configurations[selected_id]["trigger"], consumption,
                configurations[selected_id]["search"], configurations[selected_id]["scoring"],
                refresh, weight_kg=weight_kg, substeps=substeps,
            )
            filename = f"{category}__{episode_id}.png"
            _plot_episode(run, definition, plot_dir / filename, f"{category}: {episode_id}")
            plot_inventory[category] = {"episode_id": episode_id, "file": filename}
    (out / "diagnostic_plots").mkdir(parents=True, exist_ok=True)
    (out / "diagnostic_plots" / "inventory.json").write_text(
        json.dumps(plot_inventory, indent=2) + "\n"
    )

    source_snapshot, snapshot_hashes, snapshot_index_path = _source_snapshot(root, out)
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    freeze_seed = json.dumps({
        "selected": selected_payload, "protocol_sha256": sha256(protocol_path),
        "dataset_sha256": sha256(dataset_path), "checkpoint_sha256": sha256(checkpoint_path),
        "timestamp": timestamp,
    }, sort_keys=True)
    freeze_id = "step13-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + hashlib.sha256(freeze_seed.encode()).hexdigest()[:12]
    required = {
        str(Path(dataset_path).resolve()): sha256(dataset_path),
        str(Path(checkpoint_path).resolve()): sha256(checkpoint_path),
        str(Path(protocol_path)): sha256(protocol_path),
        str(selected_path): sha256(selected_path),
        str(split_path): sha256(split_path),
    }
    runtime_files = runtime_dependency_files(root)
    required.update({path: sha256(path) for path in runtime_files})
    required.update({
        str(source_snapshot / relative): digest
        for relative, digest in snapshot_hashes.items()
    })
    required[str(snapshot_index_path)] = sha256(snapshot_index_path)
    manifest = {
        "freeze_identifier": freeze_id, "frozen_at_utc": timestamp,
        "immutable": True, "final_testing_ready": final_ready,
        "readiness_meaning": readiness_meaning,
        "evaluation_description": protocol["evaluation_description"],
        "testing_disclosure": protocol["testing_split_disclosure"],
        "dataset": {"path": str(Path(dataset_path).resolve()), "sha256": sha256(dataset_path)},
        "checkpoint": {
            "path": str(Path(checkpoint_path).resolve()), "sha256": frozen.checkpoint_sha256,
            "recorded_dataset_sha256": frozen.checkpoint.get("data_sha256"),
        },
        "dataset_checkpoint_hash_discrepancy": "none",
        "patient_split_manifest": {"path": str(split_path), "sha256": sha256(split_path)},
        "episode_selection_and_exclusion_rules": protocol["episode_selection"],
        "selected_configuration": selected_payload,
        "feature_scaling_and_preprocessing": {
            "feature_order": list(MODEL_FEATURES),
            "scaling_source": "frozen checkpoint state_dict mean and scale",
            "retrained_or_refit": False,
            "source_minute_count_loader_audit": loader_audit,
        },
        "solver": {
            "weight_kg": weight_kg, "substeps": substeps,
            "dtype": "torch.float32", "parameter_lower_bounds": LOWER,
            "parameter_upper_bounds": UPPER,
        },
        "software_versions": _versions(), "python_platform": platform.platform(),
        "seeds": {"torch": 0, "numpy": 0},
        "deterministic_runtime_settings": {
            "device": "cpu", "gru_mode": "eval", "gradients": "disabled",
            "candidate_batch_size": selected_payload.get("configuration", {}).get("search", {}).get("candidate_batch_size") if selected_id else None,
        },
        "git": _git_state(root),
        "source_snapshot": str(source_snapshot),
        "source_snapshot_hash_index": str(snapshot_index_path),
        "source_snapshot_hashes": snapshot_hashes,
        "required_hashes": required,
        "change_control": "Any code or configuration change requires a new freeze identifier and renewed validation.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    verify_manifest_hashes(manifest_path, root=root)

    report_lines = [
        "# Step 13 configuration selection and freeze", "",
        f"Freeze identifier: `{freeze_id}`",
        f"Frozen experimental-evaluation readiness: **{'READY' if final_ready else 'NOT READY'}**", "",
        "READY means ready for frozen experimental evaluation; it does not mean the optimizer improved glucose control.", "",
        protocol["evaluation_description"], "",
        protocol["testing_split_disclosure"], "",
        f"Development configurations/episodes: {len(configurations)} / {len(development)} per configuration",
        f"Validation shortlist configurations/episodes: {len(shortlist)} / {len(validation_screen)} per configuration",
        f"All-validation confirmation episodes: {len(validation_complete)}",
        f"Selected configuration: `{selected_id}`", "",
    ]
    if confirmation_record:
        report_lines.extend([
            "## All-validation confirmation", "",
            f"Acceptable: **{confirmation_record['acceptable']}**",
            f"Complete pairs: {confirmation_record['complete_pair_count']}/{confirmation_record['attempted_episode_count']}",
            f"Patient-macro Δ time in range: {confirmation_record['patient_macro_delta_time_in_range_percent']:.6f} percentage points",
            f"Patient-macro Δ below 70: {confirmation_record['patient_macro_delta_below_70_percent']:.6f} percentage points",
            f"Patient-macro Δ below 54: {confirmation_record['patient_macro_delta_below_54_percent']:.6f} percentage points",
            f"Patient-macro Δ above 180: {confirmation_record['patient_macro_delta_above_180_percent']:.6f} percentage points",
            f"Patient-macro Δ above 250: {confirmation_record['patient_macro_delta_above_250_percent']:.6f} percentage points",
            f"No-feasible outcomes: {confirmation_record['no_feasible_count']}/{confirmation_record['recommendation_count']}",
            f"Upper-grid selections: {confirmation_record['upper_grid_count']}/{confirmation_record['recommendation_count']}",
            f"Simulation/implementation failures: {confirmation_record['failure_count']}", "",
        ])
    report_lines.extend([
        "## Interpretation and limitations", "",
        "All differences are optimized minus baseline and all glucose outcomes are discrete Hovorka-simulated comparisons using 288 post-advance samples for complete episodes.",
        "Raw candidate objective values were not used as the sole cross-policy outcome.",
        "A lower delivered-insulin total alone is not treated as improvement.",
        "Dose ceilings and acceptance gates are explicit experimental research settings, not clinically validated safety guarantees.",
        readiness_meaning,
        "The dataset SHA-256 matches the final checkpoint provenance.",
        "No testing-patient optimizer outcomes were accessed in Step 13.", "",
    ])
    (out / "selection_report.md").write_text("\n".join(report_lines))
    (out / "commands.txt").write_text(
        f"python -m bolus_optimization.freeze_configuration {dataset_path} "
        f"--checkpoint {checkpoint_path} --protocol {source_protocol_path} --out {out}\n"
        f"python -m bolus_optimization.freeze_configuration --verify-manifest {manifest_path}\n"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", nargs="?")
    parser.add_argument("--checkpoint", default="baseline/model.pt")
    parser.add_argument("--out", default="results/bolus_optimization_migrated_final/step13_configuration_freeze")
    parser.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    parser.add_argument("--verify-manifest")
    args = parser.parse_args()
    if args.verify_manifest:
        verify_manifest_hashes(args.verify_manifest)
        print("freeze manifest verification: PASS")
        return
    if not args.dataset:
        parser.error("dataset is required unless --verify-manifest is used")
    manifest = run_selection_and_freeze(
        args.dataset, args.checkpoint, args.out, protocol_path=args.protocol
    )
    print(Path(args.out) / "freeze_manifest.json")
    if not manifest["final_testing_ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
