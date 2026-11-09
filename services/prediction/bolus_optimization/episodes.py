"""Independent paired-episode initialization for prospective bolus work.

This module stops at the decision boundary.  It neither selects a bolus nor
advances an episode.  The GRU boundary row contains current CGM, basal and
announced carbohydrate, but a zero bolus because the current action has not
yet been delivered.  Hovorka initialization replays only the preceding 72
completed intervals and therefore returns a state before current consumption
or bolus enters the physiological compartments.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from final_model_adapter import HISTORY, sha256

from .checkpoint import FrozenGRU, load_frozen_gru, predict_parameters
from .configuration import FROZEN_CHECKPOINT_SHA256, MODEL_FEATURES
from .data import read_optimization_data
from .physiology import (
    PARAMETER_NAMES,
    PHYSIOLOGICAL_INPUT_NAMES,
    STATE_NAMES,
    CandidateFailure,
    initialize_state,
    physiological_inputs_from_frame,
)


EPISODE_INTERVALS = 288
INITIALIZATION_INTERVALS = 72
ALLOWED_SPLITS = ("development", "validation")
EXPECTED_SOURCE_HASHES = {
    "final_model_adapter.py": "22522d4f3cb12169b0a57192844c7126293be13aaedc33085ce8e7566732b154",
    "optimize.py": "7b2dfb7850b846ae8c480cccf58b968ea4e54a8953d5b7a66aaaea808dbe9c28",
    "test.py": "6cc4770aa148247f20fa1ebd06cea7eb8c87cc1da9a9554a80cd4dea89f0bd3c",
}
RELEVANT_SOURCE_FILES = (
    "final_model_adapter.py",
    "optimize.py",
    "test.py",
    "bolus_optimization/configuration.py",
    "bolus_optimization/checkpoint.py",
    "bolus_optimization/data.py",
    "bolus_optimization/physiology.py",
    "bolus_optimization/episodes.py",
)


@dataclass(frozen=True)
class EpisodeDefinition:
    episode_id: str
    dataset: str
    patient_id: str
    split: str
    start_timestamp: pd.Timestamp
    end_timestamp: pd.Timestamp
    patient_history_start_row: int
    patient_start_row: int
    patient_end_row_exclusive: int
    available_future_intervals: int
    eligible: bool
    omission_reason: str | None = None


@dataclass(frozen=True)
class IntervalEvents:
    timestamp: pd.Timestamp
    carbs_g: float
    consumed_carbs_g: float
    basal_rate_u_per_hour: float
    recorded_bolus_u: float | None


class EpisodeEnvironment:
    """Reveal only the event at an arm's current simulation timestamp.

    Future CGM is never stored.  Recorded bolus is returned only for the
    baseline arm.  Asking for any timestamp other than the arm's current one
    fails, preventing a controller from peeking at later events.
    """

    __slots__ = ("__events",)

    def __init__(self, frame: pd.DataFrame):
        required = {
            "timestamp", "carbs_g", "consumed_carbs_g",
            "basal_rate_u_per_hour", "bolus_u",
        }
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"Missing environment columns: {sorted(missing)}")
        if len(frame) != EPISODE_INTERVALS:
            raise ValueError(f"Environment must have {EPISODE_INTERVALS} intervals")
        timestamps = pd.to_datetime(frame["timestamp"])
        if not timestamps.diff().dropna().eq(pd.Timedelta(minutes=5)).all():
            raise ValueError("Environment intervals are not contiguous five-minute rows")
        self.__events = {
            pd.Timestamp(row.timestamp): (
                float(row.carbs_g), float(row.consumed_carbs_g),
                float(row.basal_rate_u_per_hour), float(row.bolus_u),
            )
            for row in frame.loc[:, sorted(required)].itertuples(index=False)
        }

    def reveal(self, arm: "ArmState", timestamp: pd.Timestamp | None = None) -> IntervalEvents:
        requested = arm.current_timestamp if timestamp is None else pd.Timestamp(timestamp)
        if requested != arm.current_timestamp:
            raise PermissionError("Only the arm's current interval may be revealed")
        if requested not in self.__events:
            raise KeyError(f"No episode interval at {requested}")
        announced, consumed, basal, recorded = self.__events[requested]
        if arm.arm_name not in {"recorded_bolus_baseline", "optimized_bolus"}:
            raise ValueError(f"Unknown arm: {arm.arm_name}")
        return IntervalEvents(
            requested, announced, consumed, basal,
            recorded if arm.arm_name == "recorded_bolus_baseline" else None,
        )


@dataclass
class ArmState:
    arm_name: str
    physiological_state: torch.Tensor
    parameters: torch.Tensor
    gru_history: torch.Tensor
    glucose_history: torch.Tensor
    applied_input_history: torch.Tensor
    current_timestamp: pd.Timestamp
    event_bookkeeping: dict[str, Any] = field(default_factory=dict)
    history: Any | None = None
    episode_start_timestamp: pd.Timestamp | None = None
    parameter_estimation_timestamp: pd.Timestamp | None = None
    refresh_log: list[dict[str, Any]] = field(default_factory=list)
    status: str = "active"
    failure_reason: str | None = None
    roundoff_corrections: int = 0
    detector_state: Any | None = None
    meal_ledger: Any | None = None


@dataclass
class InitializedEpisode:
    definition: EpisodeDefinition
    initialization_status: str
    failure: CandidateFailure | None
    shared_initial_parameters: torch.Tensor | None
    baseline_arm: ArmState | None
    optimized_arm: ArmState | None
    environment: EpisodeEnvironment | None
    roundoff_corrections: int = 0


@dataclass(frozen=True)
class PreparedEpisode:
    definition: EpisodeDefinition
    gru_history: torch.Tensor
    glucose_history: torch.Tensor
    physiological_input_history: torch.Tensor
    environmental_rows: pd.DataFrame
    historical_rows: pd.DataFrame


def build_episode_definitions(
    data: pd.DataFrame, *, splits: tuple[str, ...] = ALLOWED_SPLITS
) -> list[EpisodeDefinition]:
    """Build deterministic patient-local daily starts and report final remainders."""

    allowed = set(splits)
    if "testing" in allowed or not allowed.issubset(set(ALLOWED_SPLITS)):
        raise ValueError("Step 5 permits development and validation patients only")
    selected = data[data["split"].isin(allowed)]
    definitions: list[EpisodeDefinition] = []
    ordinal = 0
    for (dataset, patient_id), original in selected.groupby(
        ["dataset", "patient_id"], sort=True
    ):
        group = original.sort_values("timestamp").reset_index(drop=True)
        if group["split"].nunique() != 1:
            raise ValueError(f"Patient crosses splits: {(dataset, patient_id)}")
        if not group["timestamp"].diff().dropna().eq(pd.Timedelta(minutes=5)).all():
            raise ValueError(f"Patient has gaps: {(dataset, patient_id)}")
        split = str(group.loc[0, "split"])
        for start in range(EPISODE_INTERVALS, len(group), EPISODE_INTERVALS):
            available = min(EPISODE_INTERVALS, len(group) - start)
            eligible = available == EPISODE_INTERVALS
            start_time = pd.Timestamp(group.loc[start, "timestamp"])
            definition = EpisodeDefinition(
                episode_id=f"episode_{ordinal:06d}",
                dataset=str(dataset), patient_id=str(patient_id), split=split,
                start_timestamp=start_time,
                end_timestamp=start_time + pd.Timedelta(hours=24),
                patient_history_start_row=start - EPISODE_INTERVALS,
                patient_start_row=start,
                patient_end_row_exclusive=start + EPISODE_INTERVALS,
                available_future_intervals=int(available), eligible=eligible,
                omission_reason=None if eligible else "incomplete_final_episode",
            )
            definitions.append(definition)
            ordinal += 1
    return definitions


def prepare_episode(patient_rows: pd.DataFrame, definition: EpisodeDefinition) -> PreparedEpisode:
    """Separate recorded prehistory, current boundary, and pending events."""

    if not definition.eligible:
        raise ValueError("Cannot prepare an ineligible episode")
    rows = patient_rows.sort_values("timestamp").reset_index(drop=True)
    if set(rows["patient_id"].astype(str)) != {definition.patient_id}:
        raise ValueError("patient_rows do not belong exclusively to the episode patient")
    if set(rows["dataset"].astype(str)) != {definition.dataset}:
        raise ValueError("patient_rows do not belong exclusively to the episode dataset")
    start = definition.patient_start_row
    past = rows.iloc[start - HISTORY : start]
    current = rows.iloc[start]
    future = rows.iloc[start : start + EPISODE_INTERVALS]
    if len(past) != HISTORY or len(future) != EPISODE_INTERVALS:
        raise ValueError("Episode lacks complete history or future input intervals")
    expected_start = pd.Timestamp(current["timestamp"])
    if expected_start != definition.start_timestamp:
        raise ValueError("Episode row boundary does not match its start timestamp")
    if not rows["timestamp"].diff().dropna().eq(pd.Timedelta(minutes=5)).all():
        raise ValueError("Episode preparation cannot bridge timeline gaps")

    historical = past.loc[:, MODEL_FEATURES].to_numpy(dtype="float32", copy=True)
    boundary = np.asarray(
        [[current["cgm_mg_dl"], current["basal_rate_u_per_hour"], 0.0, current["carbs_g"]]],
        dtype="float32",
    )
    gru_history = torch.from_numpy(np.concatenate((historical, boundary), axis=0))
    glucose_history = torch.from_numpy(
        rows.iloc[start - INITIALIZATION_INTERVALS : start + 1]["cgm_mg_dl"]
        .to_numpy(dtype="float32", copy=True)
    )
    physiological_history = physiological_inputs_from_frame(
        rows.iloc[start - INITIALIZATION_INTERVALS : start]
    )
    environment = future.loc[:, [
        "timestamp", "carbs_g", "consumed_carbs_g",
        "basal_rate_u_per_hour", "bolus_u",
    ]].copy(deep=True)
    if gru_history.shape != (HISTORY + 1, len(MODEL_FEATURES)):
        raise RuntimeError("GRU episode-history alignment invariant failed")
    history_rows = rows.iloc[start - HISTORY : start].loc[:, [
        "timestamp", "cgm_mg_dl", "basal_rate_u_per_hour", "bolus_u",
        "carbs_g", "consumed_carbs_g",
    ]].copy(deep=True)
    return PreparedEpisode(
        definition, gru_history, glucose_history, physiological_history,
        environment, history_rows,
    )


def _arm(name: str, state: torch.Tensor, parameters: torch.Tensor, prepared: PreparedEpisode):
    from .candidate_inputs import initialize_meal_ledger
    from .history import EvolvingHistory

    current = prepared.environmental_rows.iloc[0]
    history = EvolvingHistory.from_recorded_prehistory(
        prepared.historical_rows,
        current_timestamp=prepared.definition.start_timestamp,
        current_glucose_mg_dl=float(prepared.gru_history[-1, 0]),
    )
    return ArmState(
        arm_name=name,
        physiological_state=state.detach().clone(),
        parameters=parameters.detach().clone(),
        gru_history=prepared.gru_history.detach().clone(),
        glucose_history=prepared.glucose_history.detach().clone(),
        applied_input_history=prepared.physiological_input_history.detach().clone(),
        current_timestamp=prepared.definition.start_timestamp,
        event_bookkeeping={"revealed_timestamps": [], "applied_events": []},
        history=history,
        episode_start_timestamp=prepared.definition.start_timestamp,
        parameter_estimation_timestamp=prepared.definition.start_timestamp,
        meal_ledger=initialize_meal_ledger(
            prepared.historical_rows, prepared.definition.episode_id,
            prepared.definition.patient_id,
        ),
    )


def assemble_initialized_episode(
    prepared: PreparedEpisode,
    parameters: torch.Tensor,
    state: torch.Tensor,
    failure: CandidateFailure | None,
    roundoff_corrections: int,
) -> InitializedEpisode:
    environment = EpisodeEnvironment(prepared.environmental_rows)
    if failure is not None:
        return InitializedEpisode(
            prepared.definition, "failed", failure, parameters.detach().clone(),
            None, None, environment, roundoff_corrections,
        )
    baseline = _arm("recorded_bolus_baseline", state, parameters, prepared)
    optimized = _arm("optimized_bolus", state, parameters, prepared)
    return InitializedEpisode(
        prepared.definition, "initialized", None, parameters.detach().clone(),
        baseline, optimized, environment, roundoff_corrections,
    )


def initialize_episode(
    patient_rows: pd.DataFrame,
    definition: EpisodeDefinition,
    frozen: FrozenGRU,
    *,
    weight_kg: float = 70.0,
    substeps: int = 5,
) -> InitializedEpisode:
    """Run the frozen GRU once and initialize one independent paired episode."""

    prepared = prepare_episode(patient_rows, definition)
    parameters = predict_parameters(frozen, prepared.gru_history.unsqueeze(0))[0]
    result = initialize_state(
        prepared.glucose_history, prepared.physiological_input_history,
        parameters, weight_kg, substeps,
    )
    failure = result.validity.failures[0] if result.validity.failures else None
    return assemble_initialized_episode(
        prepared, parameters, result.state, failure,
        result.validity.roundoff_corrections[0],
    )


def mutable_storage_is_independent(episode: InitializedEpisode) -> bool:
    if episode.baseline_arm is None or episode.optimized_arm is None:
        return False
    first, second = episode.baseline_arm, episode.optimized_arm
    tensors = (
        "physiological_state", "parameters", "gru_history", "glucose_history",
        "applied_input_history",
    )
    return all(getattr(first, name).data_ptr() != getattr(second, name).data_ptr() for name in tensors) \
        and first.event_bookkeeping is not second.event_bookkeeping \
        and first.event_bookkeeping["revealed_timestamps"] is not second.event_bookkeeping["revealed_timestamps"] \
        and first.event_bookkeeping["applied_events"] is not second.event_bookkeeping["applied_events"] \
        and first.meal_ledger is not second.meal_ledger \
        and first.meal_ledger.entries is not second.meal_ledger.entries


def arms_are_numerically_equal(episode: InitializedEpisode) -> bool:
    if episode.baseline_arm is None or episode.optimized_arm is None:
        return False
    first, second = episode.baseline_arm, episode.optimized_arm
    return all(torch.equal(getattr(first, name), getattr(second, name)) for name in (
        "physiological_state", "parameters", "gru_history", "glucose_history",
        "applied_input_history",
    )) and first.current_timestamp == second.current_timestamp


def _manifest_frame(definitions: list[EpisodeDefinition]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "episode_id": item.episode_id, "dataset": item.dataset,
            "patient_id": item.patient_id, "split": item.split,
            "start_timestamp": item.start_timestamp, "end_timestamp": item.end_timestamp,
            "patient_history_start_row": item.patient_history_start_row,
            "patient_start_row": item.patient_start_row,
            "patient_end_row_exclusive": item.patient_end_row_exclusive,
            "available_future_intervals": item.available_future_intervals,
            "eligibility_status": "eligible" if item.eligible else "omitted_incomplete",
            "omission_reason": item.omission_reason or "",
        }
        for item in definitions
    ])


def _versions():
    result = {"python": platform.python_version(), "platform": platform.platform()}
    for name in ("numpy", "pandas", "pyarrow", "torch"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = "unavailable"
    return result


def _summary_markdown(summary: dict) -> str:
    return "\n".join([
        "# Step 5 episode initialization", "",
        f"Overall result: **{'PASS' if summary['overall_pass'] else 'FAIL'}**", "",
        f"Eligible episodes: {summary['counts']['eligible']}",
        f"Initialized paired episodes: {summary['counts']['initialized']}",
        f"Initialization failures: {summary['counts']['failed']}",
        f"Omitted incomplete episodes: {summary['counts']['omitted_incomplete']}",
        f"Roundoff corrections: {summary['roundoff_corrections']}", "",
        "Both arms were checked for numerical equality and independent mutable storage.",
        "The GRU boundary row uses current CGM, basal, announced carbohydrates, and zero bolus.",
        "Hovorka state is before current-interval bolus or consumption.",
        "The checkpoint/dataset hash discrepancy remains unresolved.",
        "No episode was advanced and no bolus was selected or scored.", "",
    ])


def run_initialization(
    dataset_path: str | Path,
    checkpoint_path: str | Path,
    output_directory: str | Path,
    *,
    weight_kg: float = 70.0,
    substeps: int = 5,
    batch_size: int = 512,
) -> dict:
    dataset_path, checkpoint_path = Path(dataset_path), Path(checkpoint_path)
    out = Path(output_directory)
    out.mkdir(parents=True, exist_ok=True)
    data, patient_splits, data_audit = read_optimization_data(dataset_path)
    frozen = load_frozen_gru(checkpoint_path, expected_sha256=FROZEN_CHECKPOINT_SHA256)
    if patient_splits != frozen.checkpoint["patient_splits"]:
        raise ValueError("Patient splits differ from the frozen checkpoint")
    definitions = build_episode_definitions(data)
    manifest = _manifest_frame(definitions)
    eligible = [item for item in definitions if item.eligible]
    groups = {
        (str(dataset), str(patient)): group.sort_values("timestamp").reset_index(drop=True)
        for (dataset, patient), group in data[data["split"].isin(ALLOWED_SPLITS)].groupby(
            ["dataset", "patient_id"], sort=False
        )
    }
    prepared = [prepare_episode(groups[(item.dataset, item.patient_id)], item) for item in eligible]
    histories = torch.stack([item.gru_history for item in prepared])
    glucose = torch.stack([item.glucose_history for item in prepared])
    inputs = torch.stack([item.physiological_input_history for item in prepared])
    parameter_chunks = []
    for start in range(0, len(prepared), batch_size):
        parameter_chunks.append(predict_parameters(frozen, histories[start:start + batch_size]))
    parameters = torch.cat(parameter_chunks)
    initialized = initialize_state(glucose, inputs, parameters, weight_kg, substeps)
    failure_by_index = {failure.candidate_index: failure for failure in initialized.validity.failures}

    parameter_rows, state_rows, failure_rows = [], [], []
    equality_checks = 0
    storage_checks = 0
    for index, item in enumerate(prepared):
        failure = failure_by_index.get(index)
        episode = assemble_initialized_episode(
            item, parameters[index], initialized.state[index], failure,
            initialized.validity.roundoff_corrections[index],
        )
        parameter_row = {
            "episode_id": item.definition.episode_id,
            "dataset": item.definition.dataset, "patient_id": item.definition.patient_id,
            "split": item.definition.split, "start_timestamp": item.definition.start_timestamp,
            "initialization_status": episode.initialization_status,
        }
        parameter_row.update({name: float(value) for name, value in zip(PARAMETER_NAMES, parameters[index])})
        parameter_rows.append(parameter_row)
        if failure is not None:
            failure_rows.append({
                "episode_id": item.definition.episode_id, "dataset": item.definition.dataset,
                "patient_id": item.definition.patient_id, "split": item.definition.split,
                "start_timestamp": item.definition.start_timestamp,
                "first_failing_interval": failure.first_failing_interval,
                "first_failing_substep": failure.first_failing_substep,
                "reason": failure.reason,
            })
            continue
        equality_checks += int(arms_are_numerically_equal(episode))
        storage_checks += int(mutable_storage_is_independent(episode))
        for arm in (episode.baseline_arm, episode.optimized_arm):
            row = {
                "episode_id": item.definition.episode_id, "dataset": item.definition.dataset,
                "patient_id": item.definition.patient_id, "split": item.definition.split,
                "start_timestamp": item.definition.start_timestamp, "arm": arm.arm_name,
                "roundoff_corrections": episode.roundoff_corrections,
            }
            row.update({name: float(value) for name, value in zip(STATE_NAMES, arm.physiological_state)})
            state_rows.append(row)

    status = {item.definition.episode_id: "failed" if index in failure_by_index else "initialized"
              for index, item in enumerate(prepared)}
    manifest["initialization_status"] = manifest["episode_id"].map(status).fillna("not_applicable")
    manifest.to_csv(out / "episode_manifest.csv", index=False)
    pd.DataFrame(parameter_rows).to_csv(out / "initial_parameters.csv", index=False)
    pd.DataFrame(state_rows).to_parquet(out / "initial_states.parquet", index=False)
    failure_columns = ["episode_id", "dataset", "patient_id", "split", "start_timestamp",
                       "first_failing_interval", "first_failing_substep", "reason"]
    pd.DataFrame(failure_rows, columns=failure_columns).to_csv(out / "initialization_failures.csv", index=False)

    dataset_hash = sha256(dataset_path)
    source_hashes = {path: sha256(path) for path in RELEVANT_SOURCE_FILES}
    checkpoint_dataset_hash = frozen.checkpoint.get("data_sha256")
    counts_by_patient = (
        manifest.groupby(["split", "dataset", "patient_id", "eligibility_status"])
        .size().rename("count").reset_index().to_dict("records")
    )
    failed = len(failure_rows)
    configuration = {
        "step": 5, "dataset": str(dataset_path.resolve()), "dataset_sha256": dataset_hash,
        "checkpoint": str(checkpoint_path.resolve()), "checkpoint_sha256": frozen.checkpoint_sha256,
        "checkpoint_dataset_sha256": checkpoint_dataset_hash,
        "dataset_hash_discrepancy": {
            "status": "unresolved",
            "current_dataset_matches_checkpoint_record": dataset_hash == checkpoint_dataset_hash,
        },
        "source_hashes": source_hashes, "expected_source_hashes": EXPECTED_SOURCE_HASHES,
        "splits": list(ALLOWED_SPLITS), "episode_intervals": EPISODE_INTERVALS,
        "episode_hours": 24, "initialization_intervals": INITIALIZATION_INTERVALS,
        "weight_kg": weight_kg, "substeps": substeps, "batch_size": batch_size,
        "model_feature_order": list(MODEL_FEATURES),
        "physiological_input_order": list(PHYSIOLOGICAL_INPUT_NAMES),
        "prospective_gru_boundary_row": {
            "features": ["current CGM", "current basal", "zero not-yet-delivered bolus", "current announced carbs_g"],
            "difference_from_step4": "Step 4 replay included the recorded current bolus; Step 5 forces it to zero.",
        },
        "initial_state_boundary": "Before the episode-start interval's bolus and consumed carbohydrate.",
        "future_information": "No future CGM is stored; events are revealed by current arm timestamp.",
        "data_loader_audit": data_audit, "software_versions": _versions(),
    }
    (out / "configuration.json").write_text(json.dumps(configuration, indent=2, default=str) + "\n")
    counts = {
        "manifest_entries": len(definitions), "eligible": len(eligible),
        "initialized": len(eligible) - failed, "failed": failed,
        "omitted_incomplete": sum(not item.eligible for item in definitions),
    }
    initialized_count = counts["initialized"]
    failure_counts = pd.Series([row["reason"] for row in failure_rows]).value_counts().to_dict()
    summary = {
        "counts": counts, "counts_by_patient": counts_by_patient,
        "counts_by_split": manifest.groupby(["split", "eligibility_status"]).size().rename("count").reset_index().to_dict("records"),
        "initialization_failure_reasons": failure_counts,
        "roundoff_corrections": int(sum(initialized.validity.roundoff_corrections)),
        "arm_equality_checks": {"passed": equality_checks, "required": initialized_count},
        "arm_storage_independence_checks": {"passed": storage_checks, "required": initialized_count},
        "testing_patients_used": bool((manifest["split"] == "testing").any()),
        "checkpoint_preserved": frozen.checkpoint_sha256 == FROZEN_CHECKPOINT_SHA256,
        "source_files_preserved": {path: source_hashes[path] == expected for path, expected in EXPECTED_SOURCE_HASHES.items()},
        "dataset_hash_discrepancy": "unresolved",
        "scope": "Initialization only; no episode advancement, dose candidates, trigger, scoring, or optimization.",
    }
    summary["overall_pass"] = bool(
        not summary["testing_patients_used"]
        and summary["checkpoint_preserved"]
        and all(summary["source_files_preserved"].values())
        and equality_checks == initialized_count
        and storage_checks == initialized_count
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    (out / "summary.md").write_text(_summary_markdown(summary))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--checkpoint", default="baseline/model.pt")
    parser.add_argument("--out", default="results/bolus_optimization_migrated_final/step5_episode_initialization")
    parser.add_argument("--weight-kg", type=float, default=70.0)
    parser.add_argument("--substeps", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=512)
    args = parser.parse_args()
    if args.weight_kg <= 0 or args.substeps <= 0 or args.batch_size <= 0:
        parser.error("weight, substeps and batch size must be positive")
    summary = run_initialization(
        args.dataset, args.checkpoint, args.out, weight_kg=args.weight_kg,
        substeps=args.substeps, batch_size=args.batch_size,
    )
    print(Path(args.out) / "summary.json")
    if not summary["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
