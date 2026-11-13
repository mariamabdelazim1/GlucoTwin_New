"""Materialize recorded 48-hour inputs for constant basal candidates only."""

from __future__ import annotations

import numbers
from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch

from bolus_optimization.physiology import PHYSIOLOGICAL_INPUT_NAMES

from .candidate_generation import (
    BasalCandidateSet,
    BasalRateCandidate,
    extract_constant_baseline_rate,
)
from .preparation import (
    INTERVAL,
    REPLAY_INTERVALS,
    PatientIdentity,
    PreparedBasalSnapshot,
)


PHYSIOLOGICAL_INPUT_UNITS = (
    "U/hour",
    "U/interval",
    "g/interval",
)
REPLAY_HOURS = 48.0
ACCOUNTING_RTOL = 2e-6
ACCOUNTING_ATOL = 1e-6


@dataclass(frozen=True)
class CandidatePhysiologicalInputs:
    candidate_id: str
    rate_u_per_hour: float
    is_recorded_baseline: bool
    interval_inputs: torch.Tensor
    initial_state: torch.Tensor
    parameters: torch.Tensor
    basal_total_u: float
    bolus_total_u: float
    consumed_carbs_total_g: float


@dataclass(frozen=True)
class BasalCandidateInputBatch:
    identity: PatientIdentity
    decision_timestamp: pd.Timestamp
    replay_start_timestamp: pd.Timestamp
    replay_end_timestamp: pd.Timestamp
    input_names: tuple[str, ...]
    input_units: tuple[str, ...]
    input_timestamps: tuple[pd.Timestamp, ...]
    expected_output_timestamps: tuple[pd.Timestamp, ...]
    configuration_version: str
    configuration_hash: str
    baseline_candidate_id: str
    candidate_count: int
    candidates: tuple[CandidatePhysiologicalInputs, ...]
    baseline_replacement_note: str


def _same_timestamp(left: object, right: object) -> bool:
    """Compare exact values after precision upcasting, retaining timezone metadata."""

    try:
        left_index = pd.DatetimeIndex([pd.Timestamp(left)]).as_unit("ns")
        right_index = pd.DatetimeIndex([pd.Timestamp(right)]).as_unit("ns")
    except (TypeError, ValueError, OverflowError):
        return False
    return left_index.equals(right_index)


def _validate_recorded_column(replay: pd.DataFrame, name: str) -> np.ndarray:
    if name not in replay.columns:
        raise ValueError(f"Prepared replay is missing required physiological input {name}")
    raw = replay[name]
    boolean = raw.map(lambda value: isinstance(value, (bool, np.bool_)))
    if boolean.any():
        locations = replay.loc[boolean, "timestamp"].astype(str).head(5).tolist()
        raise ValueError(f"{name} contains Boolean values at {locations}")
    numeric = raw.map(lambda value: isinstance(value, numbers.Real))
    if not numeric.all():
        locations = replay.loc[~numeric, "timestamp"].astype(str).head(5).tolist()
        raise ValueError(f"{name} contains missing or nonnumeric values at {locations}")
    values = raw.to_numpy(dtype=np.float64, copy=True)
    finite = np.isfinite(values)
    if not finite.all():
        locations = replay.loc[~finite, "timestamp"].astype(str).head(5).tolist()
        raise ValueError(f"{name} contains missing or nonfinite values at {locations}")
    if (values < 0).any():
        locations = replay.loc[values < 0, "timestamp"].astype(str).head(5).tolist()
        raise ValueError(f"{name} contains negative values at {locations}")
    return values


def _validate_candidate(candidate: BasalRateCandidate, index: int) -> None:
    if not isinstance(candidate.candidate_id, str) or not candidate.candidate_id:
        raise ValueError(f"Candidate at index {index} has an empty or nonstring candidate_id")
    rate = candidate.rate_u_per_hour
    if isinstance(rate, (bool, np.bool_)) or not isinstance(rate, numbers.Real):
        raise ValueError(f"Candidate {candidate.candidate_id} rate must be numeric and not Boolean")
    if not np.isfinite(float(rate)) or float(rate) < 0:
        raise ValueError(f"Candidate {candidate.candidate_id} rate must be finite and nonnegative")
    with np.errstate(over="ignore", invalid="ignore"):
        float32_rate = np.float32(float(rate))
    if not np.isfinite(float32_rate):
        raise ValueError(
            f"Candidate {candidate.candidate_id} basal_rate_u_per_hour becomes "
            "nonfinite after float32 conversion"
        )
    if not isinstance(candidate.is_recorded_baseline, (bool, np.bool_)):
        raise ValueError(
            f"Candidate {candidate.candidate_id} baseline flag must be Boolean"
        )


def _storage_pointer(tensor: torch.Tensor) -> int:
    return tensor.untyped_storage().data_ptr()


def _locations(mask: torch.Tensor, timestamps: tuple[pd.Timestamp, ...]) -> list[str]:
    indexes = mask.detach().cpu().nonzero().flatten().tolist()
    return [str(timestamps[index]) for index in indexes[:5]]


def _validate_converted_recorded_tensor(
    values: torch.Tensor,
    column: str,
    timestamps: tuple[pd.Timestamp, ...],
) -> None:
    nonfinite = ~torch.isfinite(values)
    if nonfinite.any().item():
        raise ValueError(
            f"{column} becomes nonfinite after float32 conversion at interval "
            f"timestamps {_locations(nonfinite, timestamps)}"
        )
    negative = values < 0
    if negative.any().item():
        raise ValueError(
            f"{column} becomes negative after float32 conversion at interval "
            f"timestamps {_locations(negative, timestamps)}"
        )


def _validate_materialized_inputs(
    candidate_id: str,
    inputs: torch.Tensor,
    timestamps: tuple[pd.Timestamp, ...],
) -> None:
    for column_index, column in enumerate(PHYSIOLOGICAL_INPUT_NAMES):
        values = inputs[:, column_index]
        nonfinite = ~torch.isfinite(values)
        if nonfinite.any().item():
            raise ValueError(
                f"Candidate {candidate_id} materialized {column} is nonfinite at interval "
                f"timestamps {_locations(nonfinite, timestamps)}"
            )
        negative = values < 0
        if negative.any().item():
            raise ValueError(
                f"Candidate {candidate_id} materialized {column} is negative at interval "
                f"timestamps {_locations(negative, timestamps)}"
            )


def _require_finite_total(value: float, description: str) -> None:
    if not np.isfinite(value):
        raise ValueError(f"{description} is nonfinite")


def _validate_compatibility(
    snapshot: PreparedBasalSnapshot,
    candidate_set: BasalCandidateSet,
) -> tuple[np.ndarray, np.ndarray, tuple[pd.Timestamp, ...], float]:
    if not isinstance(candidate_set, BasalCandidateSet):
        raise TypeError("candidate_set must be a BasalCandidateSet")
    if candidate_set.identity != snapshot.identity:
        raise ValueError("Candidate-set patient identity does not match the prepared snapshot")
    if not _same_timestamp(candidate_set.decision_timestamp, snapshot.decision_timestamp):
        raise ValueError("Candidate-set decision timestamp does not match the prepared snapshot")
    if not _same_timestamp(candidate_set.replay_start_timestamp, snapshot.simulation_start):
        raise ValueError("Candidate-set replay start does not match the prepared snapshot")
    if not _same_timestamp(candidate_set.replay_end_timestamp, snapshot.decision_timestamp):
        raise ValueError("Candidate-set replay end does not match the prepared snapshot")
    if candidate_set.replay_interval_count != REPLAY_INTERVALS:
        raise ValueError(
            f"Candidate set must describe {REPLAY_INTERVALS} replay intervals; "
            f"found {candidate_set.replay_interval_count}"
        )
    replay = snapshot.replay_intervals
    if len(replay) != REPLAY_INTERVALS:
        raise ValueError(
            f"Prepared replay must contain {REPLAY_INTERVALS} intervals; found {len(replay)}"
        )
    if "timestamp" not in replay.columns:
        raise ValueError("Prepared replay is missing timestamp")
    actual_timestamps = pd.DatetimeIndex(replay["timestamp"])
    expected_timestamps = pd.date_range(
        start=snapshot.simulation_start,
        periods=REPLAY_INTERVALS,
        freq=INTERVAL,
    )
    if not actual_timestamps.as_unit("ns").equals(expected_timestamps.as_unit("ns")):
        raise ValueError(
            "Prepared replay timestamps must exactly cover [S, T) at five-minute cadence "
            "without reordering, padding, or truncation"
        )
    output_timestamps = actual_timestamps + INTERVAL
    if not _same_timestamp(actual_timestamps[0], snapshot.simulation_start):
        raise ValueError("First replay interval must start at S")
    if not _same_timestamp(actual_timestamps[-1], snapshot.decision_timestamp - INTERVAL):
        raise ValueError("Last replay interval must start at T - 5 minutes")
    if not _same_timestamp(output_timestamps[-1], snapshot.decision_timestamp):
        raise ValueError("Last replay interval must end at T")
    if any(_same_timestamp(value, snapshot.decision_timestamp) for value in actual_timestamps):
        raise ValueError("Replay must not contain an interval starting at T")

    bolus = _validate_recorded_column(replay, "bolus_u")
    consumed_carbs = _validate_recorded_column(replay, "consumed_carbs_g")
    recorded_baseline = extract_constant_baseline_rate(snapshot)

    if (
        isinstance(candidate_set.candidate_count, (bool, np.bool_))
        or not isinstance(candidate_set.candidate_count, numbers.Integral)
    ):
        raise ValueError("Candidate count metadata must be an integer and not Boolean")
    if candidate_set.candidate_count != len(candidate_set.candidates):
        raise ValueError(
            "Candidate count metadata disagrees with the number of candidate records"
        )
    if not candidate_set.candidates:
        raise ValueError("Candidate set must contain at least one candidate")
    if not isinstance(candidate_set.configuration_version, str) or not candidate_set.configuration_version:
        raise ValueError("Candidate-set configuration_version must be nonempty")
    if not isinstance(candidate_set.configuration_hash, str) or not candidate_set.configuration_hash:
        raise ValueError("Candidate-set configuration_hash must be nonempty")
    for index, candidate in enumerate(candidate_set.candidates):
        _validate_candidate(candidate, index)
    candidate_ids = [candidate.candidate_id for candidate in candidate_set.candidates]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("Candidate IDs must be unique")
    rates = np.asarray(
        [candidate.rate_u_per_hour for candidate in candidate_set.candidates],
        dtype=np.float64,
    )
    if len(np.unique(rates)) != len(rates):
        raise ValueError("Candidate rates must be unique")
    float32_rates = rates.astype(np.float32)
    if len(np.unique(float32_rates)) != len(rates):
        raise ValueError("Distinct candidate rates collapse in simulator float32 dtype")

    baseline_candidates = [
        candidate for candidate in candidate_set.candidates if candidate.is_recorded_baseline
    ]
    if len(baseline_candidates) != 1:
        raise ValueError("Candidate set must contain exactly one recorded baseline candidate")
    baseline_candidate = baseline_candidates[0]
    if candidate_set.baseline_candidate_id != baseline_candidate.candidate_id:
        raise ValueError("Baseline candidate ID metadata does not match the flagged candidate")
    if candidate_set.baseline_rate_u_per_hour != baseline_candidate.rate_u_per_hour:
        raise ValueError("Baseline candidate rate metadata does not match the flagged candidate")
    if candidate_set.baseline_rate_u_per_hour != recorded_baseline:
        raise ValueError(
            "Candidate-set baseline rate does not match the prepared replay baseline"
        )

    state = snapshot.physiological_state
    parameters = snapshot.parameters
    if not isinstance(state, torch.Tensor) or tuple(state.shape) != (10,):
        raise ValueError("Prepared physiological state must have shape (10,)")
    if not isinstance(parameters, torch.Tensor) or tuple(parameters.shape) != (7,):
        raise ValueError("Prepared parameters must have shape (7,)")
    if not state.dtype.is_floating_point or not parameters.dtype.is_floating_point:
        raise ValueError("Prepared state and parameters must use floating-point dtypes")
    if state.dtype != parameters.dtype or state.device != parameters.device:
        raise ValueError("Prepared state and parameters must share dtype and device")
    if state.dtype != torch.float32:
        raise ValueError("Prepared simulator state and parameters must use torch.float32")
    if not torch.isfinite(state).all() or not torch.isfinite(parameters).all():
        raise ValueError("Prepared state and parameters must be finite")
    return bolus, consumed_carbs, tuple(pd.Timestamp(value) for value in actual_timestamps), recorded_baseline


def build_candidate_inputs(
    snapshot: PreparedBasalSnapshot,
    candidate_set: BasalCandidateSet,
) -> BasalCandidateInputBatch:
    """Build independent `(576, 3)` float32 inputs without running simulation."""

    bolus, consumed_carbs, input_timestamps, recorded_baseline = _validate_compatibility(
        snapshot, candidate_set
    )
    device = snapshot.physiological_state.device
    recorded_bolus = torch.as_tensor(bolus, dtype=torch.float32, device=device)
    recorded_consumed_carbs = torch.as_tensor(
        consumed_carbs, dtype=torch.float32, device=device
    )
    _validate_converted_recorded_tensor(recorded_bolus, "bolus_u", input_timestamps)
    _validate_converted_recorded_tensor(
        recorded_consumed_carbs, "consumed_carbs_g", input_timestamps
    )
    expected_bolus_total = float(recorded_bolus.sum().item())
    expected_carbs_total = float(recorded_consumed_carbs.sum().item())
    _require_finite_total(
        expected_bolus_total,
        "Recorded bolus_u expected total after float32 reduction",
    )
    _require_finite_total(
        expected_carbs_total,
        "Recorded consumed_carbs_g expected total after float32 reduction",
    )
    materialized: list[CandidatePhysiologicalInputs] = []
    for candidate in candidate_set.candidates:
        clone = snapshot.clone_initial_conditions()
        if (
            not isinstance(clone.physiological_state, torch.Tensor)
            or tuple(clone.physiological_state.shape) != (10,)
            or clone.physiological_state.dtype != snapshot.physiological_state.dtype
            or clone.physiological_state.device != device
        ):
            raise RuntimeError("Cloned physiological state violates snapshot conventions")
        if (
            not isinstance(clone.parameters, torch.Tensor)
            or tuple(clone.parameters.shape) != (7,)
            or clone.parameters.dtype != snapshot.parameters.dtype
            or clone.parameters.device != device
        ):
            raise RuntimeError("Cloned parameters violate snapshot conventions")
        if _storage_pointer(clone.physiological_state) == _storage_pointer(
            snapshot.physiological_state
        ):
            raise RuntimeError("Cloned physiological state shares storage with the snapshot")
        if _storage_pointer(clone.parameters) == _storage_pointer(snapshot.parameters):
            raise RuntimeError("Cloned parameters share storage with the snapshot")
        inputs = torch.empty(
            (REPLAY_INTERVALS, len(PHYSIOLOGICAL_INPUT_NAMES)),
            dtype=torch.float32,
            device=device,
        )
        inputs[:, 0] = float(candidate.rate_u_per_hour)
        inputs[:, 1] = recorded_bolus
        inputs[:, 2] = recorded_consumed_carbs
        _validate_materialized_inputs(candidate.candidate_id, inputs, input_timestamps)
        basal_total = float((inputs[:, 0].sum() * (5.0 / 60.0)).item())
        bolus_total = float(inputs[:, 1].sum().item())
        carbs_total = float(inputs[:, 2].sum().item())
        expected_basal_total = float(candidate.rate_u_per_hour) * REPLAY_HOURS
        _require_finite_total(
            expected_basal_total,
            f"Candidate {candidate.candidate_id} expected basal_rate_u_per_hour total",
        )
        _require_finite_total(
            basal_total,
            f"Candidate {candidate.candidate_id} represented basal_rate_u_per_hour total",
        )
        _require_finite_total(
            bolus_total,
            f"Candidate {candidate.candidate_id} represented bolus_u total",
        )
        _require_finite_total(
            carbs_total,
            f"Candidate {candidate.candidate_id} represented consumed_carbs_g total",
        )
        if not np.isclose(
            basal_total,
            expected_basal_total,
            rtol=ACCOUNTING_RTOL,
            atol=ACCOUNTING_ATOL,
        ):
            raise RuntimeError(
                f"Candidate {candidate.candidate_id} basal accounting mismatch: "
                f"represented={basal_total}, expected={expected_basal_total}"
            )
        if not np.isclose(
            bolus_total,
            expected_bolus_total,
            rtol=ACCOUNTING_RTOL,
            atol=ACCOUNTING_ATOL,
        ):
            raise RuntimeError(
                f"Candidate {candidate.candidate_id} bolus accounting mismatch: "
                f"represented={bolus_total}, expected={expected_bolus_total}"
            )
        if not np.isclose(
            carbs_total,
            expected_carbs_total,
            rtol=ACCOUNTING_RTOL,
            atol=ACCOUNTING_ATOL,
        ):
            raise RuntimeError(
                f"Candidate {candidate.candidate_id} carbohydrate accounting mismatch: "
                f"represented={carbs_total}, expected={expected_carbs_total}"
            )
        materialized.append(
            CandidatePhysiologicalInputs(
                candidate_id=candidate.candidate_id,
                rate_u_per_hour=float(candidate.rate_u_per_hour),
                is_recorded_baseline=bool(candidate.is_recorded_baseline),
                interval_inputs=inputs,
                initial_state=clone.physiological_state,
                parameters=clone.parameters,
                basal_total_u=basal_total,
                bolus_total_u=bolus_total,
                consumed_carbs_total_g=carbs_total,
            )
        )

    for index, candidate in enumerate(materialized):
        for other in materialized[index + 1:]:
            if _storage_pointer(candidate.interval_inputs) == _storage_pointer(
                other.interval_inputs
            ):
                raise RuntimeError("Candidate input tensors share mutable storage")
            if _storage_pointer(candidate.initial_state) == _storage_pointer(
                other.initial_state
            ):
                raise RuntimeError("Candidate initial states share mutable storage")
            if _storage_pointer(candidate.parameters) == _storage_pointer(other.parameters):
                raise RuntimeError("Candidate parameters share mutable storage")
            if not torch.equal(candidate.interval_inputs[:, 1:], other.interval_inputs[:, 1:]):
                raise RuntimeError("Recorded bolus/carbohydrate inputs differ across candidates")
            if candidate.rate_u_per_hour != other.rate_u_per_hour and torch.equal(
                candidate.interval_inputs[:, 0], other.interval_inputs[:, 0]
            ):
                raise RuntimeError("Distinct candidate rates produced identical basal inputs")

    output_timestamps = tuple(timestamp + INTERVAL for timestamp in input_timestamps)
    return BasalCandidateInputBatch(
        identity=snapshot.identity,
        decision_timestamp=snapshot.decision_timestamp,
        replay_start_timestamp=snapshot.simulation_start,
        replay_end_timestamp=snapshot.decision_timestamp,
        input_names=tuple(PHYSIOLOGICAL_INPUT_NAMES),
        input_units=PHYSIOLOGICAL_INPUT_UNITS,
        input_timestamps=input_timestamps,
        expected_output_timestamps=output_timestamps,
        configuration_version=candidate_set.configuration_version,
        configuration_hash=candidate_set.configuration_hash,
        baseline_candidate_id=candidate_set.baseline_candidate_id,
        candidate_count=len(materialized),
        candidates=tuple(materialized),
        baseline_replacement_note=(
            "The baseline candidate repeats the exact first recorded reference rate before "
            "float32 conversion. Permitted sub-1e-9 U/hour differences in the raw recorded "
            "trajectory are therefore replaced by that constant reference."
        ),
    )
