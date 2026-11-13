"""Continuous 48-hour Hovorka simulation for prepared basal candidates."""

from __future__ import annotations

import numbers
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch

from bolus_optimization.physiology import (
    DEFAULT_SUBSTEPS,
    INTERVAL_MINUTES,
    PHYSIOLOGICAL_INPUT_NAMES,
    CandidateFailure,
    predict_from_state,
)

from .candidate_inputs import (
    BasalCandidateInputBatch,
    CandidatePhysiologicalInputs,
)
from .preparation import INTERVAL, REPLAY_INTERVALS, PatientIdentity


FIXED_WEIGHT_KG = 70.0
SIMULATOR_DTYPE = torch.float32
DEFAULT_CANDIDATE_BATCH_SIZE = 8


@dataclass(frozen=True)
class BasalSimulationFailure:
    candidate_id: str
    first_failing_interval: int
    first_failing_substep: int
    input_timestamp: pd.Timestamp | None
    expected_output_timestamp: pd.Timestamp | None
    reason: str


@dataclass(frozen=True)
class BasalCandidateSimulationResult:
    candidate_id: str
    rate_u_per_hour: float
    is_recorded_baseline: bool
    simulation_status: str
    expected_output_timestamps: tuple[pd.Timestamp, ...]
    predicted_glucose_mg_dl: torch.Tensor
    final_state: torch.Tensor
    fixed_parameters: torch.Tensor
    failure: BasalSimulationFailure | None
    available_prediction_steps: int
    roundoff_corrections: int
    minimum_glucose_mg_dl: float | None
    maximum_glucose_mg_dl: float | None
    endpoint_glucose_mg_dl: float | None


@dataclass(frozen=True)
class BasalSimulationBatchResult:
    identity: PatientIdentity
    decision_timestamp: pd.Timestamp
    replay_start_timestamp: pd.Timestamp
    replay_end_timestamp: pd.Timestamp
    configuration_version: str
    configuration_hash: str
    baseline_candidate_id: str
    weight_kg: float
    dtype: str
    device: str
    interval_minutes: float
    substeps: int
    candidate_batch_size: int
    output_timestamps: tuple[pd.Timestamp, ...]
    candidates: tuple[BasalCandidateSimulationResult, ...]
    candidate_count: int
    valid_candidate_count: int
    failed_candidate_count: int
    runtime_seconds: float
    numerical_scope_note: str
    state_trajectory_returned: bool = False


def _same_timestamp(left: object, right: object) -> bool:
    try:
        left_index = pd.DatetimeIndex([pd.Timestamp(left)]).as_unit("ns")
        right_index = pd.DatetimeIndex([pd.Timestamp(right)]).as_unit("ns")
    except (TypeError, ValueError, OverflowError):
        return False
    return left_index.equals(right_index)


def _validate_candidate(candidate: CandidatePhysiologicalInputs, index: int) -> None:
    if not isinstance(candidate.candidate_id, str) or not candidate.candidate_id:
        raise ValueError(f"Candidate at index {index} has an invalid candidate_id")
    if not isinstance(candidate.is_recorded_baseline, (bool, np.bool_)):
        raise ValueError(f"Candidate {candidate.candidate_id} baseline flag must be Boolean")
    rate = candidate.rate_u_per_hour
    if isinstance(rate, (bool, np.bool_)) or not isinstance(rate, numbers.Real):
        raise ValueError(f"Candidate {candidate.candidate_id} rate must be numeric and not Boolean")
    if not np.isfinite(float(rate)) or float(rate) < 0:
        raise ValueError(f"Candidate {candidate.candidate_id} rate must be finite and nonnegative")
    tensors = (
        ("interval_inputs", candidate.interval_inputs, (REPLAY_INTERVALS, 3)),
        ("initial_state", candidate.initial_state, (10,)),
        ("parameters", candidate.parameters, (7,)),
    )
    for name, tensor, shape in tensors:
        if not isinstance(tensor, torch.Tensor) or tuple(tensor.shape) != shape:
            raise ValueError(
                f"Candidate {candidate.candidate_id} {name} must have shape {shape}"
            )
        if tensor.dtype != SIMULATOR_DTYPE:
            raise ValueError(
                f"Candidate {candidate.candidate_id} {name} must use torch.float32"
            )
    devices = {tensor.device for _, tensor, _ in tensors}
    if len(devices) != 1:
        raise ValueError(
            f"Candidate {candidate.candidate_id} inputs, state, and parameters must share a device"
        )
    if not torch.isfinite(candidate.interval_inputs).all().item():
        raise ValueError(f"Candidate {candidate.candidate_id} interval_inputs contain nonfinite values")
    if (candidate.interval_inputs < 0).any().item():
        raise ValueError(f"Candidate {candidate.candidate_id} interval_inputs contain negative values")
    if not torch.isfinite(candidate.initial_state).all().item():
        raise ValueError(f"Candidate {candidate.candidate_id} initial_state contains nonfinite values")
    if not torch.isfinite(candidate.parameters).all().item():
        raise ValueError(f"Candidate {candidate.candidate_id} parameters contain nonfinite values")
    expected_basal = torch.full(
        (REPLAY_INTERVALS,),
        float(rate),
        dtype=SIMULATOR_DTYPE,
        device=candidate.interval_inputs.device,
    )
    if not torch.equal(candidate.interval_inputs[:, 0], expected_basal):
        raise ValueError(
            f"Candidate {candidate.candidate_id} basal_rate_u_per_hour column does not "
            "match its constant rate metadata"
        )


def _validate_batch(batch: BasalCandidateInputBatch, candidate_batch_size: int) -> None:
    if not isinstance(batch, BasalCandidateInputBatch):
        raise TypeError("batch must be a BasalCandidateInputBatch")
    if (
        isinstance(candidate_batch_size, (bool, np.bool_))
        or not isinstance(candidate_batch_size, numbers.Integral)
        or int(candidate_batch_size) <= 0
    ):
        raise ValueError("candidate_batch_size must be a positive integer")
    if batch.candidate_count != len(batch.candidates) or not batch.candidates:
        raise ValueError("Candidate count metadata is inconsistent or empty")
    if not _same_timestamp(batch.replay_end_timestamp, batch.decision_timestamp):
        raise ValueError("Replay end must equal the decision timestamp")
    if len(batch.input_timestamps) != REPLAY_INTERVALS:
        raise ValueError(f"Input timestamps must contain {REPLAY_INTERVALS} positions")
    if len(batch.expected_output_timestamps) != REPLAY_INTERVALS:
        raise ValueError(f"Output timestamps must contain {REPLAY_INTERVALS} positions")
    expected_inputs = pd.date_range(
        start=batch.replay_start_timestamp,
        periods=REPLAY_INTERVALS,
        freq=INTERVAL,
    )
    actual_inputs = pd.DatetimeIndex(batch.input_timestamps)
    if not actual_inputs.as_unit("ns").equals(expected_inputs.as_unit("ns")):
        raise ValueError("Input timestamps must exactly cover the 48-hour five-minute replay")
    expected_outputs = expected_inputs + INTERVAL
    actual_outputs = pd.DatetimeIndex(batch.expected_output_timestamps)
    if not actual_outputs.as_unit("ns").equals(expected_outputs.as_unit("ns")):
        raise ValueError("Expected output timestamps must equal each input timestamp plus five minutes")
    if not _same_timestamp(actual_outputs[-1], batch.decision_timestamp):
        raise ValueError("Final output timestamp must equal the decision timestamp")
    if tuple(batch.input_names) != tuple(PHYSIOLOGICAL_INPUT_NAMES):
        raise ValueError("Input names do not match the physiological simulator contract")
    if not isinstance(batch.configuration_version, str) or not batch.configuration_version:
        raise ValueError("configuration_version must be nonempty")
    if not isinstance(batch.configuration_hash, str) or not batch.configuration_hash:
        raise ValueError("configuration_hash must be nonempty")
    for index, candidate in enumerate(batch.candidates):
        _validate_candidate(candidate, index)
    candidate_ids = [candidate.candidate_id for candidate in batch.candidates]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("Candidate IDs must be unique")
    baseline = [candidate for candidate in batch.candidates if candidate.is_recorded_baseline]
    if len(baseline) != 1 or baseline[0].candidate_id != batch.baseline_candidate_id:
        raise ValueError("Baseline candidate metadata is inconsistent")
    devices = {candidate.interval_inputs.device for candidate in batch.candidates}
    if len(devices) != 1:
        raise ValueError("All candidates must use the same simulator device")


def _available_prefix(values: torch.Tensor) -> int:
    invalid = (~torch.isfinite(values)).nonzero().flatten()
    return int(invalid[0].item()) if len(invalid) else len(values)


def _failure(
    candidate_id: str,
    failure: CandidateFailure | None,
    batch: BasalCandidateInputBatch,
) -> BasalSimulationFailure:
    if failure is None:
        return BasalSimulationFailure(
            candidate_id,
            -1,
            -1,
            None,
            None,
            "simulator_reported_invalid_without_failure_detail",
        )
    interval = failure.first_failing_interval
    return BasalSimulationFailure(
        candidate_id=candidate_id,
        first_failing_interval=interval,
        first_failing_substep=failure.first_failing_substep,
        input_timestamp=batch.input_timestamps[interval] if interval >= 0 else None,
        expected_output_timestamp=(
            batch.expected_output_timestamps[interval] if interval >= 0 else None
        ),
        reason=failure.reason,
    )


def simulate_candidate_batch(
    batch: BasalCandidateInputBatch,
    *,
    candidate_batch_size: int = DEFAULT_CANDIDATE_BATCH_SIZE,
) -> BasalSimulationBatchResult:
    """Run one continuous 576-interval replay per candidate without CGM correction."""

    _validate_batch(batch, candidate_batch_size)
    started = time.perf_counter()
    results: list[BasalCandidateSimulationResult] = []
    for start in range(0, len(batch.candidates), int(candidate_batch_size)):
        chunk = batch.candidates[start:start + int(candidate_batch_size)]
        initial_states = torch.stack([candidate.initial_state for candidate in chunk])
        parameters = torch.stack([candidate.parameters for candidate in chunk])
        inputs = torch.stack([candidate.interval_inputs for candidate in chunk])
        with torch.inference_mode():
            prediction = predict_from_state(
                initial_states,
                parameters,
                inputs,
                weight_kg=FIXED_WEIGHT_KG,
                substeps=DEFAULT_SUBSTEPS,
            )
        failures = {
            failure.candidate_index: failure for failure in prediction.validity.failures
        }
        for local_index, candidate in enumerate(chunk):
            glucose = prediction.glucose_mg_dl[local_index].detach().clone()
            final_state = prediction.final_state[local_index].detach().clone()
            fixed_parameters = candidate.parameters.detach().clone()
            valid = bool(prediction.validity.valid_mask[local_index].item())
            available = _available_prefix(glucose)
            failure = None if valid else _failure(
                candidate.candidate_id,
                failures.get(local_index),
                batch,
            )
            if valid:
                if available != REPLAY_INTERVALS or not torch.isfinite(final_state).all().item():
                    raise RuntimeError(
                        f"Simulator marked candidate {candidate.candidate_id} valid but "
                        "returned incomplete or nonfinite results"
                    )
                minimum = float(glucose.min().item())
                maximum = float(glucose.max().item())
                endpoint = float(glucose[-1].item())
                status = "simulation_valid"
            else:
                minimum = maximum = endpoint = None
                status = "simulation_failed"
            results.append(
                BasalCandidateSimulationResult(
                    candidate_id=candidate.candidate_id,
                    rate_u_per_hour=candidate.rate_u_per_hour,
                    is_recorded_baseline=candidate.is_recorded_baseline,
                    simulation_status=status,
                    expected_output_timestamps=batch.expected_output_timestamps,
                    predicted_glucose_mg_dl=glucose,
                    final_state=final_state,
                    fixed_parameters=fixed_parameters,
                    failure=failure,
                    available_prediction_steps=available,
                    roundoff_corrections=int(
                        prediction.validity.roundoff_corrections[local_index]
                    ),
                    minimum_glucose_mg_dl=minimum,
                    maximum_glucose_mg_dl=maximum,
                    endpoint_glucose_mg_dl=endpoint,
                )
            )
    valid_count = sum(result.simulation_status == "simulation_valid" for result in results)
    device = str(batch.candidates[0].interval_inputs.device)
    return BasalSimulationBatchResult(
        identity=batch.identity,
        decision_timestamp=batch.decision_timestamp,
        replay_start_timestamp=batch.replay_start_timestamp,
        replay_end_timestamp=batch.replay_end_timestamp,
        configuration_version=batch.configuration_version,
        configuration_hash=batch.configuration_hash,
        baseline_candidate_id=batch.baseline_candidate_id,
        weight_kg=FIXED_WEIGHT_KG,
        dtype=str(SIMULATOR_DTYPE),
        device=device,
        interval_minutes=INTERVAL_MINUTES,
        substeps=DEFAULT_SUBSTEPS,
        candidate_batch_size=int(candidate_batch_size),
        output_timestamps=batch.expected_output_timestamps,
        candidates=tuple(results),
        candidate_count=len(results),
        valid_candidate_count=valid_count,
        failed_candidate_count=len(results) - valid_count,
        runtime_seconds=time.perf_counter() - started,
        numerical_scope_note=(
            "simulation_valid denotes numerical validity only; it does not establish "
            "clinical safety, effectiveness, or long-rollout predictive accuracy"
        ),
    )
