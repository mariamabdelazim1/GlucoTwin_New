"""Prepare a patient-specific 72-hour retrospective basal snapshot.

This module implements only historical-window construction, validation, GRU
parameter estimation, and Hovorka initialization.  It deliberately contains
no basal candidates, simulation, scoring, selection, or delivery behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

import numpy as np
import pandas as pd
import torch

from final_model_adapter import HISTORY
from bolus_optimization.checkpoint import load_frozen_gru, predict_parameters
from bolus_optimization.configuration import (
    FROZEN_CHECKPOINT_SHA256,
    MODEL_FEATURES,
    SAMPLE_INTERVAL_MINUTES,
)
from bolus_optimization.physiology import (
    PARAMETER_NAMES,
    PHYSIOLOGICAL_INPUT_NAMES,
    STATE_NAMES,
    initialize_state,
    physiological_inputs_from_frame,
)


PREDICTION_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PREDICTION_ROOT.parents[1]
DEFAULT_DATASET_PATH = Path("services/prediction/model_ready_5min.parquet")
DEFAULT_CHECKPOINT_PATH = PREDICTION_ROOT / "baseline/model.pt"
INTERVAL = pd.Timedelta(minutes=SAMPLE_INTERVAL_MINUTES)
INITIALIZATION_INTERVALS = HISTORY
REPLAY_INTERVALS = 2 * HISTORY
PHYSIOLOGICAL_INITIALIZATION_INTERVALS = 72
EFFECTIVE_WEIGHT_KG = 70.0
EFFECTIVE_WEIGHT_PROVENANCE = "checkpoint fixed_parameters.weight_kg"

REQUIRED_COLUMNS = (
    "dataset",
    "patient_id",
    "split",
    "timestamp",
    "cgm_mg_dl",
    "basal_rate_u_per_hour",
    "bolus_u",
    "carbs_g",
    "consumed_carbs_g",
)
NONNEGATIVE_COLUMNS = (
    "basal_rate_u_per_hour",
    "bolus_u",
    "carbs_g",
    "consumed_carbs_g",
)


class BasalPreparationError(ValueError):
    """An actionable, patient-window-specific preparation rejection."""

    def __init__(self, reasons: str | Sequence[str]):
        self.reasons = (reasons,) if isinstance(reasons, str) else tuple(reasons)
        super().__init__("Basal preparation rejected: " + "; ".join(self.reasons))


@dataclass(frozen=True)
class PatientIdentity:
    dataset: str
    patient_id: str


@dataclass(frozen=True)
class ValidationOutcome:
    valid: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoricalWindows:
    identity: PatientIdentity
    split: str
    decision_timestamp: pd.Timestamp
    simulation_start: pd.Timestamp
    initialization_intervals: pd.DataFrame
    boundary_row: pd.Series
    replay_intervals: pd.DataFrame
    outcome_row_at_decision: pd.Series | None
    validation: ValidationOutcome


@dataclass(frozen=True)
class SnapshotClone:
    physiological_state: torch.Tensor
    parameters: torch.Tensor


@dataclass(frozen=True)
class PreparedBasalSnapshot:
    identity: PatientIdentity
    split: str
    decision_timestamp: pd.Timestamp
    simulation_start: pd.Timestamp
    initialization_intervals: pd.DataFrame
    boundary_row: pd.Series
    replay_intervals: pd.DataFrame
    outcome_row_at_decision: pd.Series | None
    gru_input: torch.Tensor
    physiological_initialization_glucose: torch.Tensor
    physiological_initialization_inputs: torch.Tensor
    physiological_state: torch.Tensor
    parameters: torch.Tensor
    parameter_names: tuple[str, ...]
    state_names: tuple[str, ...]
    parameter_estimation_timestamp: pd.Timestamp
    effective_weight_kg: float
    effective_weight_provenance: str
    checkpoint_sha256: str
    dataset_path: str
    checkpoint_dataset_provenance: str
    dataset_provenance_note: str
    model_features: tuple[str, ...]
    validation: ValidationOutcome
    initialization_provenance: Mapping[str, object]

    def clone_initial_conditions(self) -> SnapshotClone:
        """Return independent candidate-owned tensor storage."""

        return SnapshotClone(
            self.physiological_state.detach().clone(),
            self.parameters.detach().clone(),
        )


def _timestamp(value: object, label: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
    except Exception as exc:  # pragma: no cover - pandas supplies useful detail
        raise BasalPreparationError(f"{label} is not a valid timestamp: {value!r}") from exc
    if pd.isna(result):
        raise BasalPreparationError(f"{label} is not a valid timestamp: {value!r}")
    return result


def _timezone_kind(value: pd.Timestamp) -> str:
    return "aware" if value.tzinfo is not None else "naive"


def _resolve_repository_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPOSITORY_ROOT / candidate


def _coverage_reason(
    frame: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    expected_count: int,
    label: str,
) -> str | None:
    expected = pd.date_range(start=start, periods=expected_count, freq=INTERVAL)
    actual = pd.DatetimeIndex(frame["timestamp"])
    if len(actual) == expected_count and actual.equals(expected):
        return None
    missing = expected.difference(actual)
    extra = actual.difference(expected)
    return (
        f"{label} coverage must be [{start}, {end}) with {expected_count} five-minute "
        f"intervals; found {len(actual)}, missing={list(missing[:5])}, extra={list(extra[:5])}"
    )


def build_historical_windows(
    data: pd.DataFrame,
    identity: PatientIdentity,
    decision_timestamp: object,
) -> HistoricalWindows:
    """Build `[S-24h,S)` initialization and `[S,T)` replay windows.

    Timestamp-naive and timestamp-aware values are never coerced into one
    another.  The row at ``T`` is retained only as an optional outcome row.
    """

    reasons: list[str] = []
    missing_columns = sorted(set(REQUIRED_COLUMNS).difference(data.columns))
    if missing_columns:
        raise BasalPreparationError(f"missing required columns: {missing_columns}")

    decision = _timestamp(decision_timestamp, "decision timestamp T")
    if (
        decision.second != 0
        or decision.microsecond != 0
        or decision.nanosecond != 0
        or decision.minute % SAMPLE_INTERVAL_MINUTES != 0
    ):
        reasons.append("decision timestamp T must be aligned to the five-minute grid")

    raw_timestamps = pd.to_datetime(data["timestamp"], errors="coerce")
    if raw_timestamps.isna().any():
        reasons.append("timestamp contains missing or unparseable values")
    else:
        sample = pd.Timestamp(raw_timestamps.iloc[0]) if len(raw_timestamps) else decision
        if _timezone_kind(sample) != _timezone_kind(decision):
            reasons.append(
                "decision timestamp timezone convention differs from dataset timestamps "
                f"(T is {_timezone_kind(decision)}, data is {_timezone_kind(sample)})"
            )
    if reasons:
        raise BasalPreparationError(reasons)

    frame = data.copy(deep=True)
    frame["timestamp"] = raw_timestamps
    selected = frame.loc[
        frame["dataset"].astype(str).eq(identity.dataset)
        & frame["patient_id"].astype(str).eq(identity.patient_id)
    ].copy(deep=True)
    if selected.empty:
        raise BasalPreparationError(
            f"patient identity not found: dataset={identity.dataset!r}, patient_id={identity.patient_id!r}"
        )
    selected = selected.sort_values("timestamp", kind="stable").reset_index(drop=True)

    if selected.duplicated("timestamp").any():
        duplicate_values = selected.loc[selected.duplicated("timestamp", keep=False), "timestamp"]
        reasons.append(f"duplicate timestamps: {duplicate_values.astype(str).head(5).tolist()}")
    if selected["split"].nunique(dropna=False) != 1:
        reasons.append(f"patient has inconsistent split metadata: {selected['split'].unique().tolist()}")
    if selected["dataset"].astype(str).nunique() != 1 or selected["patient_id"].astype(str).nunique() != 1:
        reasons.append("window contains more than one patient identity")

    simulation_start = decision - pd.Timedelta(hours=48)
    initialization_start = simulation_start - pd.Timedelta(hours=24)
    initialization = selected.loc[
        selected["timestamp"].ge(initialization_start)
        & selected["timestamp"].lt(simulation_start)
    ].copy(deep=True)
    boundary = selected.loc[selected["timestamp"].eq(simulation_start)].copy(deep=True)
    replay = selected.loc[
        selected["timestamp"].ge(simulation_start)
        & selected["timestamp"].lt(decision)
    ].copy(deep=True)
    outcome = selected.loc[selected["timestamp"].eq(decision)].copy(deep=True)

    for reason in (
        _coverage_reason(
            initialization,
            initialization_start,
            simulation_start,
            INITIALIZATION_INTERVALS,
            "initialization",
        ),
        _coverage_reason(replay, simulation_start, decision, REPLAY_INTERVALS, "replay"),
    ):
        if reason:
            reasons.append(reason)
    if len(boundary) != 1:
        reasons.append(f"boundary glucose at S={simulation_start} must have exactly one row; found {len(boundary)}")
    if len(outcome) > 1:
        reasons.append(f"outcome timestamp T={decision} is ambiguous; found {len(outcome)} rows")

    combined = pd.concat((initialization, replay), ignore_index=True)
    if len(combined):
        numeric = ["cgm_mg_dl", *NONNEGATIVE_COLUMNS]
        converted = combined.loc[:, numeric].apply(pd.to_numeric, errors="coerce")
        for column in numeric:
            values = converted[column].to_numpy(dtype=float)
            missing = combined[column].isna().to_numpy() | ~np.isfinite(values)
            if missing.any():
                locations = combined.loc[missing, "timestamp"].astype(str).head(5).tolist()
                reasons.append(f"{column} is missing or nonfinite at {locations}")
        glucose = converted["cgm_mg_dl"].to_numpy(dtype=float)
        if np.isfinite(glucose).all() and (glucose <= 0).any():
            reasons.append("cgm_mg_dl must be strictly positive under the model contract")
        for column in NONNEGATIVE_COLUMNS:
            values = converted[column].to_numpy(dtype=float)
            if np.isfinite(values).all() and (values < 0).any():
                reasons.append(f"{column} must be nonnegative")

        if "source_minute_count" in combined.columns:
            counts = pd.to_numeric(combined["source_minute_count"], errors="coerce")
            bad = counts.isna() | counts.ne(SAMPLE_INTERVAL_MINUTES)
            if bad.any():
                rows = combined.loc[bad, ["timestamp", "source_minute_count"]].head(5)
                reasons.append(
                    "partial or discontinuous source intervals are unsupported: "
                    f"{rows.to_dict('records')}"
                )
        for source_column in ("source_run_id", "source_record_id"):
            if source_column in combined.columns and combined[source_column].nunique(dropna=False) != 1:
                reasons.append(f"window crosses {source_column} boundaries")

    if reasons:
        raise BasalPreparationError(reasons)

    split = str(selected["split"].iloc[0])
    return HistoricalWindows(
        identity=identity,
        split=split,
        decision_timestamp=decision,
        simulation_start=simulation_start,
        initialization_intervals=initialization.reset_index(drop=True),
        boundary_row=boundary.iloc[0].copy(deep=True),
        replay_intervals=replay.reset_index(drop=True),
        outcome_row_at_decision=None if outcome.empty else outcome.iloc[0].copy(deep=True),
        validation=ValidationOutcome(True),
    )


def prepare_basal_snapshot(
    data: pd.DataFrame,
    identity: PatientIdentity,
    decision_timestamp: object,
    parameter_estimator: Callable[[torch.Tensor], torch.Tensor],
    *,
    dataset_path: str,
    checkpoint_sha256: str,
    checkpoint_metadata: Mapping[str, object],
) -> PreparedBasalSnapshot:
    """Validate windows, estimate seven parameters once, and initialize at S."""

    windows = build_historical_windows(data, identity, decision_timestamp)
    fixed = checkpoint_metadata.get("fixed_parameters", {})
    config = checkpoint_metadata.get("config", {})
    fixed_weight = fixed.get("weight_kg") if isinstance(fixed, Mapping) else None
    configured_weight = config.get("weight_kg") if isinstance(config, Mapping) else None
    if fixed_weight != EFFECTIVE_WEIGHT_KG or configured_weight != EFFECTIVE_WEIGHT_KG:
        raise BasalPreparationError(
            "checkpoint weight contract mismatch: expected fixed_parameters.weight_kg "
            f"and config.weight_kg to both equal {EFFECTIVE_WEIGHT_KG}, found "
            f"{fixed_weight!r} and {configured_weight!r}"
        )

    completed = windows.initialization_intervals.loc[:, MODEL_FEATURES].to_numpy(
        dtype=np.float32, copy=True
    )
    boundary = windows.boundary_row
    prospective_boundary = np.asarray(
        [[
            boundary["cgm_mg_dl"],
            boundary["basal_rate_u_per_hour"],
            0.0,
            boundary["carbs_g"],
        ]],
        dtype=np.float32,
    )
    gru_input = torch.from_numpy(np.concatenate((completed, prospective_boundary), axis=0))
    if tuple(gru_input.shape) != (HISTORY + 1, len(MODEL_FEATURES)):
        raise RuntimeError("GRU input shape invariant failed")

    with torch.inference_mode():
        estimated = parameter_estimator(gru_input.unsqueeze(0))
    if tuple(estimated.shape) == (1, len(PARAMETER_NAMES)):
        parameters = estimated[0].detach().clone()
    elif tuple(estimated.shape) == (len(PARAMETER_NAMES),):
        parameters = estimated.detach().clone()
    else:
        raise BasalPreparationError(
            f"parameter estimator returned shape {tuple(estimated.shape)}; expected (1, 7) or (7,)"
        )
    if parameters.dtype != torch.float32:
        parameters = parameters.to(torch.float32)
    if not torch.isfinite(parameters).all():
        raise BasalPreparationError("parameter estimator returned nonfinite values")

    six_hour_rows = windows.initialization_intervals.iloc[-PHYSIOLOGICAL_INITIALIZATION_INTERVALS:]
    glucose = torch.from_numpy(np.concatenate((
        six_hour_rows["cgm_mg_dl"].to_numpy(dtype=np.float32, copy=True),
        np.asarray([boundary["cgm_mg_dl"]], dtype=np.float32),
    )))
    inputs = physiological_inputs_from_frame(six_hour_rows)
    initialized = initialize_state(
        glucose,
        inputs,
        parameters,
        weight_kg=EFFECTIVE_WEIGHT_KG,
        substeps=5,
    )
    if initialized.validity.failures:
        failure = initialized.validity.failures[0]
        raise BasalPreparationError(
            "physiological initialization failed at interval "
            f"{failure.first_failing_interval}, substep {failure.first_failing_substep}: "
            f"{failure.reason}"
        )

    state = initialized.state.detach().clone()
    return PreparedBasalSnapshot(
        identity=windows.identity,
        split=windows.split,
        decision_timestamp=windows.decision_timestamp,
        simulation_start=windows.simulation_start,
        initialization_intervals=windows.initialization_intervals.copy(deep=True),
        boundary_row=windows.boundary_row.copy(deep=True),
        replay_intervals=windows.replay_intervals.copy(deep=True),
        outcome_row_at_decision=(
            None
            if windows.outcome_row_at_decision is None
            else windows.outcome_row_at_decision.copy(deep=True)
        ),
        gru_input=gru_input.detach().clone(),
        physiological_initialization_glucose=glucose.detach().clone(),
        physiological_initialization_inputs=inputs.detach().clone(),
        physiological_state=state,
        parameters=parameters,
        parameter_names=tuple(PARAMETER_NAMES),
        state_names=tuple(STATE_NAMES),
        parameter_estimation_timestamp=windows.simulation_start,
        effective_weight_kg=EFFECTIVE_WEIGHT_KG,
        effective_weight_provenance=EFFECTIVE_WEIGHT_PROVENANCE,
        checkpoint_sha256=checkpoint_sha256,
        dataset_path=dataset_path,
        checkpoint_dataset_provenance=str(config.get("data", "unspecified")),
        dataset_provenance_note=(
            "Basal preparation uses the explicitly mandated model_ready_5min.parquet. "
            "The frozen checkpoint records training provenance as "
            f"{config.get('data', 'unspecified')}; model-contract checks passed, but these "
            "dataset filenames are not identical."
        ),
        model_features=tuple(MODEL_FEATURES),
        validation=windows.validation,
        initialization_provenance={
            "initialization_window": f"[{windows.simulation_start - pd.Timedelta(hours=24)}, {windows.simulation_start})",
            "physiological_replay_window": f"[{windows.simulation_start - pd.Timedelta(hours=6)}, {windows.simulation_start})",
            "gru_boundary": "observed glucose and prospective basal/announced carbs at S; bolus forced to zero",
            "state_boundary": "before basal/bolus/consumed carbohydrate in the interval starting at S",
            "parameters_held_fixed": True,
            "physiological_input_order": tuple(PHYSIOLOGICAL_INPUT_NAMES),
        },
    )


def prepare_basal_snapshot_from_file(
    identity: PatientIdentity,
    decision_timestamp: object,
    *,
    dataset_path: str | Path = DEFAULT_DATASET_PATH,
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT_PATH,
) -> PreparedBasalSnapshot:
    """Real-model entry point using only the mandated repository dataset."""

    resolved_dataset = _resolve_repository_path(dataset_path)
    mandated = _resolve_repository_path(DEFAULT_DATASET_PATH).resolve()
    if resolved_dataset.resolve() != mandated:
        raise BasalPreparationError(
            f"basal preparation requires {mandated}; received {resolved_dataset.resolve()}"
        )
    frozen = load_frozen_gru(checkpoint_path, expected_sha256=FROZEN_CHECKPOINT_SHA256)
    data = pd.read_parquet(resolved_dataset)
    split_map = frozen.checkpoint["patient_splits"]
    actual_splits = {
        str((str(dataset), str(patient))): str(group["split"].iloc[0])
        for (dataset, patient), group in data.groupby(["dataset", "patient_id"], sort=False)
    }
    if actual_splits != split_map:
        raise BasalPreparationError("patient split metadata differs from the frozen checkpoint")
    return prepare_basal_snapshot(
        data,
        identity,
        decision_timestamp,
        lambda history: predict_parameters(frozen, history),
        dataset_path=str(resolved_dataset.resolve()),
        checkpoint_sha256=frozen.checkpoint_sha256,
        checkpoint_metadata=frozen.checkpoint,
    )
