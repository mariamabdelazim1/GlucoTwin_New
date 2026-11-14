"""Recorded-CGM fit assessment and reliability gating for the baseline candidate."""

from __future__ import annotations

import hashlib
import json
import numbers
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import torch

from .preparation import INTERVAL, PreparedBasalSnapshot, REPLAY_INTERVALS, PatientIdentity
from .simulation import (
    BasalCandidateSimulationResult,
    BasalSimulationBatchResult,
)


UNCALIBRATED_CRITERIA_PATH = Path(__file__).with_name(
    "uncalibrated_reliability_configuration_v1.json"
)
CRITERION_FIELDS = (
    "full_mae_limit_mg_dl",
    "full_rmse_limit_mg_dl",
    "day0_mae_limit_mg_dl",
    "day0_rmse_limit_mg_dl",
    "day1_mae_limit_mg_dl",
    "day1_rmse_limit_mg_dl",
)


def _positive_optional(value: object, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be numeric and not Boolean")
    result = float(value)
    if not np.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and strictly positive")
    return result


@dataclass(frozen=True)
class ReliabilityCriteria:
    configuration_version: str
    calibration_status: str
    intended_use: str
    full_mae_limit_mg_dl: float | None = None
    full_rmse_limit_mg_dl: float | None = None
    day0_mae_limit_mg_dl: float | None = None
    day0_rmse_limit_mg_dl: float | None = None
    day1_mae_limit_mg_dl: float | None = None
    day1_rmse_limit_mg_dl: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.configuration_version, str) or not self.configuration_version:
            raise ValueError("configuration_version must be nonempty")
        if self.calibration_status not in {"not_calibrated", "provisional_development"}:
            raise ValueError(
                "calibration_status must be not_calibrated or provisional_development"
            )
        if not isinstance(self.intended_use, str) or not self.intended_use:
            raise ValueError("intended_use must be nonempty")
        for field in CRITERION_FIELDS:
            object.__setattr__(self, field, _positive_optional(getattr(self, field), field))
        configured = [getattr(self, field) is not None for field in CRITERION_FIELDS]
        if self.calibration_status == "not_calibrated" and any(configured):
            raise ValueError("not_calibrated criteria must not contain error limits")
        if self.calibration_status == "provisional_development" and not all(configured):
            raise ValueError("provisional_development criteria require all six error limits")


def criteria_hash(criteria: ReliabilityCriteria) -> str:
    payload = json.dumps(asdict(criteria), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def load_reliability_criteria(path: str | Path) -> tuple[ReliabilityCriteria, str]:
    payload: Any = json.loads(Path(path).read_text())
    if not isinstance(payload, Mapping):
        raise ValueError("Reliability criteria must be a JSON object")
    criteria = ReliabilityCriteria(**payload)
    return criteria, criteria_hash(criteria)


@dataclass(frozen=True)
class CoverageDiagnostics:
    expected_observation_count: int
    matched_observation_count: int
    missing_observation_count: int
    invalid_observation_count: int
    duplicate_timestamp_count: int
    complete: bool


@dataclass(frozen=True)
class AlignedGlucoseObservation:
    availability_timestamp: pd.Timestamp
    measurement_timestamp: pd.Timestamp | None
    predicted_glucose_mg_dl: float
    observed_glucose_mg_dl: float | None
    valid: bool
    invalid_reason: str | None = None


@dataclass(frozen=True)
class GlucoseFitMetrics:
    mae_mg_dl: float
    rmse_mg_dl: float
    mean_signed_error_mg_dl: float
    maximum_absolute_error_mg_dl: float
    matched_count: int
    expected_count: int


@dataclass(frozen=True)
class ReliabilityCriterionResult:
    criterion: str
    observed_value: float
    inclusive_limit: float
    passed: bool


@dataclass(frozen=True)
class BaselineReliabilityAssessment:
    identity: PatientIdentity
    decision_timestamp: pd.Timestamp
    replay_start_timestamp: pd.Timestamp
    replay_end_timestamp: pd.Timestamp
    baseline_candidate_id: str
    baseline_rate_u_per_hour: float
    baseline_simulation_status: str
    coverage: CoverageDiagnostics
    aligned_observations: tuple[AlignedGlucoseObservation, ...]
    full_window_metrics: GlucoseFitMetrics | None
    day0_metrics: GlucoseFitMetrics | None
    day1_metrics: GlucoseFitMetrics | None
    endpoint_error_mg_dl: float | None
    criteria: ReliabilityCriteria | None
    criteria_configuration_hash: str | None
    criterion_results: tuple[ReliabilityCriterionResult, ...]
    status: str
    future_selection_authorized: bool
    reasons: tuple[str, ...]
    interpretation: str


def _timezone_label(value: pd.Timestamp) -> str:
    return "naive" if value.tzinfo is None else str(value.tzinfo)


def _timestamp_key(value: object) -> tuple[str, int]:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("timestamp is missing")
    normalized = pd.DatetimeIndex([timestamp]).as_unit("ns")[0]
    return _timezone_label(normalized), int(normalized.value)


def _same_timestamp(left: object, right: object) -> bool:
    try:
        return _timestamp_key(left) == _timestamp_key(right)
    except (TypeError, ValueError, OverflowError):
        return False


def _baseline_candidate(
    simulation: BasalSimulationBatchResult,
) -> BasalCandidateSimulationResult:
    flagged = [candidate for candidate in simulation.candidates if candidate.is_recorded_baseline]
    if len(flagged) != 1:
        raise ValueError("Simulation batch must contain exactly one flagged baseline candidate")
    baseline = flagged[0]
    if baseline.candidate_id != simulation.baseline_candidate_id:
        raise ValueError("Simulation baseline_candidate_id disagrees with the flagged candidate")
    return baseline


def _source_rows(snapshot: PreparedBasalSnapshot) -> list[dict[str, object]]:
    required = {"timestamp", "cgm_mg_dl"}
    missing = required.difference(snapshot.replay_intervals.columns)
    if missing:
        raise ValueError(f"Prepared replay is missing glucose outcome columns: {sorted(missing)}")
    has_measurement = "cgm_measurement_timestamp" in snapshot.replay_intervals.columns
    rows: list[dict[str, object]] = []
    for row in snapshot.replay_intervals.itertuples(index=False):
        timestamp = pd.Timestamp(getattr(row, "timestamp"))
        if _same_timestamp(timestamp, snapshot.simulation_start):
            continue
        rows.append({
            "timestamp": timestamp,
            "cgm_mg_dl": getattr(row, "cgm_mg_dl"),
            "cgm_measurement_timestamp": (
                getattr(row, "cgm_measurement_timestamp") if has_measurement else None
            ),
        })
    outcome = snapshot.outcome_row_at_decision
    if outcome is not None:
        rows.append({
            "timestamp": outcome.get("timestamp"),
            "cgm_mg_dl": outcome.get("cgm_mg_dl"),
            "cgm_measurement_timestamp": outcome.get("cgm_measurement_timestamp", None),
        })
    return rows


def _measurement_reason(measurement: object, availability: pd.Timestamp) -> tuple[pd.Timestamp | None, str | None]:
    if measurement is None or pd.isna(measurement):
        return None, None
    try:
        timestamp = pd.Timestamp(measurement)
    except (TypeError, ValueError, OverflowError):
        return None, "cgm_measurement_timestamp is invalid"
    if (timestamp.tzinfo is None) != (availability.tzinfo is None):
        return timestamp, "measurement and availability timezone conventions differ"
    if timestamp > availability:
        return timestamp, "cgm_measurement_timestamp is later than availability timestamp"
    return timestamp, None


def calculate_glucose_fit_metrics(
    predicted: np.ndarray, observed: np.ndarray
) -> GlucoseFitMetrics:
    """Calculate the canonical baseline-fit metrics in float64."""

    predicted = np.asarray(predicted, dtype=np.float64)
    observed = np.asarray(observed, dtype=np.float64)
    if predicted.ndim != 1 or observed.ndim != 1 or predicted.shape != observed.shape:
        raise ValueError("Predicted and observed glucose must be equal-length 1-D arrays")
    if not len(predicted):
        raise ValueError("At least one matched glucose observation is required")
    if not np.isfinite(predicted).all() or not np.isfinite(observed).all():
        raise ValueError("Predicted and observed glucose must be finite")
    error = predicted.astype(np.float64) - observed.astype(np.float64)
    absolute = np.abs(error)
    values = (
        float(absolute.mean()),
        float(np.sqrt(np.mean(np.square(error)))),
        float(error.mean()),
        float(absolute.max()),
    )
    if not np.isfinite(values).all():
        raise ValueError("Baseline glucose-fit metrics are nonfinite")
    return GlucoseFitMetrics(*values, len(error), len(error))


def assess_baseline_reliability(
    snapshot: PreparedBasalSnapshot,
    simulation: BasalSimulationBatchResult,
    criteria: ReliabilityCriteria | None = None,
) -> BaselineReliabilityAssessment:
    """Align baseline predictions to recorded outcomes and apply an optional gate."""

    if simulation.identity != snapshot.identity:
        raise ValueError("Simulation patient identity differs from the prepared snapshot")
    if not _same_timestamp(simulation.decision_timestamp, snapshot.decision_timestamp):
        raise ValueError("Simulation decision timestamp differs from the prepared snapshot")
    if not _same_timestamp(simulation.replay_start_timestamp, snapshot.simulation_start):
        raise ValueError("Simulation replay start differs from the prepared snapshot")
    if not _same_timestamp(simulation.replay_end_timestamp, snapshot.decision_timestamp):
        raise ValueError("Simulation replay end differs from the prepared snapshot")
    baseline = _baseline_candidate(simulation)
    expected = tuple(pd.Timestamp(value) for value in simulation.output_timestamps)
    if len(expected) != REPLAY_INTERVALS:
        raise ValueError(f"Simulation output metadata must contain {REPLAY_INTERVALS} timestamps")
    required_outputs = pd.date_range(
        snapshot.simulation_start + INTERVAL, periods=REPLAY_INTERVALS, freq=INTERVAL
    )
    if not pd.DatetimeIndex(expected).as_unit("ns").equals(required_outputs.as_unit("ns")):
        raise ValueError("Simulation outputs must exactly cover S + 5 minutes through T")
    baseline_timestamps = pd.DatetimeIndex(baseline.expected_output_timestamps)
    batch_timestamps = pd.DatetimeIndex(expected)
    if not baseline_timestamps.as_unit("ns").equals(batch_timestamps.as_unit("ns")):
        raise ValueError("Baseline output timestamps differ from simulation batch metadata")

    reasons: list[str] = []
    rows_by_key: dict[tuple[str, int], list[dict[str, object]]] = {}
    invalid_source_timestamps = 0
    for row in _source_rows(snapshot):
        try:
            key = _timestamp_key(row["timestamp"])
        except (TypeError, ValueError, OverflowError):
            invalid_source_timestamps += 1
            continue
        rows_by_key.setdefault(key, []).append(row)
    duplicate_count = sum(len(rows) - 1 for rows in rows_by_key.values() if len(rows) > 1)

    predicted = baseline.predicted_glucose_mg_dl.detach().cpu().numpy().astype(np.float64, copy=True)
    prediction_complete = (
        baseline.simulation_status == "simulation_valid"
        and baseline.available_prediction_steps == REPLAY_INTERVALS
        and predicted.shape == (REPLAY_INTERVALS,)
        and np.isfinite(predicted).all()
    )
    if not prediction_complete:
        reasons.append(
            "baseline simulation is failed, incomplete, or nonfinite; complete numerical "
            "validity is required"
        )

    aligned: list[AlignedGlucoseObservation] = []
    missing_count = invalid_count = matched_count = 0
    observed_values: list[float] = []
    for index, timestamp in enumerate(expected):
        key = _timestamp_key(timestamp)
        rows = rows_by_key.get(key, [])
        predicted_value = float(predicted[index]) if index < len(predicted) else float("nan")
        if not rows:
            missing_count += 1
            aligned.append(AlignedGlucoseObservation(timestamp, None, predicted_value, None, False, "missing observation"))
            continue
        if len(rows) != 1:
            invalid_count += 1
            aligned.append(AlignedGlucoseObservation(timestamp, None, predicted_value, None, False, "duplicate availability timestamp"))
            continue
        row = rows[0]
        value = row["cgm_mg_dl"]
        measurement, measurement_reason = _measurement_reason(
            row.get("cgm_measurement_timestamp"), timestamp
        )
        value_reason = None
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real):
            value_reason = "cgm_mg_dl is missing, Boolean, or nonnumeric"
        elif not np.isfinite(float(value)) or float(value) <= 0:
            value_reason = "cgm_mg_dl must be finite and strictly positive"
        invalid_reason = value_reason or measurement_reason
        if invalid_reason is not None:
            invalid_count += 1
            aligned.append(AlignedGlucoseObservation(timestamp, measurement, predicted_value, None, False, invalid_reason))
            continue
        observed = float(value)
        observed_values.append(observed)
        matched_count += 1
        aligned.append(AlignedGlucoseObservation(timestamp, measurement, predicted_value, observed, True))

    invalid_count += invalid_source_timestamps
    coverage = CoverageDiagnostics(
        expected_observation_count=REPLAY_INTERVALS,
        matched_observation_count=matched_count,
        missing_observation_count=missing_count,
        invalid_observation_count=invalid_count,
        duplicate_timestamp_count=duplicate_count,
        complete=(matched_count == REPLAY_INTERVALS and missing_count == 0 and invalid_count == 0 and duplicate_count == 0),
    )
    if not coverage.complete:
        reasons.append(
            "complete recorded-CGM coverage is required: "
            f"matched={matched_count}, missing={missing_count}, invalid={invalid_count}, "
            f"duplicate_timestamps={duplicate_count}"
        )

    full_metrics = day0_metrics = day1_metrics = None
    endpoint_error = None
    if prediction_complete and aligned[-1].valid:
        endpoint_error = float(predicted[-1] - aligned[-1].observed_glucose_mg_dl)
        if not np.isfinite(endpoint_error):
            raise ValueError("Endpoint error is nonfinite")
    if prediction_complete and coverage.complete:
        observed = np.asarray(observed_values, dtype=np.float64)
        full_metrics = calculate_glucose_fit_metrics(predicted, observed)
        day0_metrics = calculate_glucose_fit_metrics(predicted[:288], observed[:288])
        day1_metrics = calculate_glucose_fit_metrics(predicted[288:], observed[288:])

    criterion_results: list[ReliabilityCriterionResult] = []
    criteria_configuration_hash = criteria_hash(criteria) if criteria is not None else None
    if not prediction_complete or not coverage.complete:
        status = "insufficient_model_reliability"
    elif criteria is None or criteria.calibration_status == "not_calibrated":
        status = "criteria_not_calibrated"
        reasons.append("reliability criteria are not calibrated; future selection is not authorized")
    else:
        metric_values = {
            "full_mae_limit_mg_dl": full_metrics.mae_mg_dl,
            "full_rmse_limit_mg_dl": full_metrics.rmse_mg_dl,
            "day0_mae_limit_mg_dl": day0_metrics.mae_mg_dl,
            "day0_rmse_limit_mg_dl": day0_metrics.rmse_mg_dl,
            "day1_mae_limit_mg_dl": day1_metrics.mae_mg_dl,
            "day1_rmse_limit_mg_dl": day1_metrics.rmse_mg_dl,
        }
        for name in CRITERION_FIELDS:
            observed_value = metric_values[name]
            limit = getattr(criteria, name)
            if limit is None:  # guarded by ReliabilityCriteria, retained for type safety
                raise RuntimeError(f"configured reliability limit {name} is unexpectedly absent")
            passed = observed_value <= limit
            criterion_results.append(
                ReliabilityCriterionResult(name, observed_value, limit, passed)
            )
            if not passed:
                reasons.append(
                    f"{name} failed: observed {observed_value} exceeds inclusive limit {limit}"
                )
        status = (
            "reliable_under_experimental_criteria"
            if all(result.passed for result in criterion_results)
            else "insufficient_model_reliability"
        )

    return BaselineReliabilityAssessment(
        identity=snapshot.identity,
        decision_timestamp=snapshot.decision_timestamp,
        replay_start_timestamp=snapshot.simulation_start,
        replay_end_timestamp=snapshot.decision_timestamp,
        baseline_candidate_id=baseline.candidate_id,
        baseline_rate_u_per_hour=baseline.rate_u_per_hour,
        baseline_simulation_status=baseline.simulation_status,
        coverage=coverage,
        aligned_observations=tuple(aligned),
        full_window_metrics=full_metrics,
        day0_metrics=day0_metrics,
        day1_metrics=day1_metrics,
        endpoint_error_mg_dl=endpoint_error,
        criteria=criteria,
        criteria_configuration_hash=criteria_configuration_hash,
        criterion_results=tuple(criterion_results),
        status=status,
        future_selection_authorized=(status == "reliable_under_experimental_criteria"),
        reasons=tuple(reasons),
        interpretation=(
            "Baseline fit assesses observed glucose agreement under unchanged basal only; "
            "it does not validate alternative-basal counterfactuals or clinical safety."
        ),
    )
