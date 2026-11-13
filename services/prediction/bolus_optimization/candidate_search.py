"""Bounded bolus-grid generation and four-hour Hovorka simulation.

This module reports numerical simulation results only.  It does not score,
rank, recommend, select, acknowledge or deliver any candidate.
"""

from __future__ import annotations

import hashlib
import json
import numbers
import time
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from .candidate_inputs import (
    CandidateBolus, CandidateInputBatch, ConsumptionConfiguration,
    DecisionSnapshot, KnownBasalSchedule, build_candidate_inputs,
    validate_decision_snapshot,
)
from .configuration_loading import (
    DEFAULT_RESEARCH_CONFIGURATION, load_component_payload,
)
from .physiology import STATE_NAMES, _normalize_state, predict_from_state


DEFAULT_SEARCH_CONFIGURATION = DEFAULT_RESEARCH_CONFIGURATION


def _finite_number(value, name: str, *, positive: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be numeric and not Boolean")
    result = float(value)
    if not np.isfinite(result) or result < 0 or (positive and result <= 0):
        qualifier = "strictly positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be finite and {qualifier}")
    return result


def _positive_integer(value, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Integral):
        raise ValueError(f"{name} must be a positive integer")
    result = int(value)
    if result <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return result


@dataclass(frozen=True)
class BolusSearchConfiguration:
    configuration_version: str
    maximum_bolus_u: float
    bolus_increment_u: float
    maximum_candidate_count: int
    candidate_batch_size: int
    intended_use: str

    def __post_init__(self):
        if not self.configuration_version or not self.intended_use:
            raise ValueError("Search configuration version and intended use are required")
        object.__setattr__(self, "maximum_bolus_u", _finite_number(
            self.maximum_bolus_u, "maximum_bolus_u"
        ))
        object.__setattr__(self, "bolus_increment_u", _finite_number(
            self.bolus_increment_u, "bolus_increment_u", positive=True
        ))
        object.__setattr__(self, "maximum_candidate_count", _positive_integer(
            self.maximum_candidate_count, "maximum_candidate_count"
        ))
        object.__setattr__(self, "candidate_batch_size", _positive_integer(
            self.candidate_batch_size, "candidate_batch_size"
        ))


def load_search_configuration(path: str | Path = DEFAULT_SEARCH_CONFIGURATION):
    _, _, payload, content_hash = load_component_payload(path, "search")
    return BolusSearchConfiguration(**payload), content_hash


def _decimal(value: float, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} cannot be represented as a decimal") from None
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result


def generate_bolus_candidates(
    configuration: BolusSearchConfiguration,
    *,
    tensor_dtype: torch.dtype = torch.float32,
) -> tuple[CandidateBolus, ...]:
    """Generate ascending decimal ticks, stopping below a nondivisible maximum."""

    if not isinstance(configuration, BolusSearchConfiguration):
        raise TypeError("configuration must be a BolusSearchConfiguration")
    if not isinstance(tensor_dtype, torch.dtype) or not tensor_dtype.is_floating_point:
        raise TypeError("tensor_dtype must be a floating-point torch dtype")
    maximum = _decimal(configuration.maximum_bolus_u, "maximum_bolus_u")
    increment = _decimal(configuration.bolus_increment_u, "bolus_increment_u")
    ticks = int(maximum // increment)
    count = ticks + 1
    if count > configuration.maximum_candidate_count:
        raise ValueError(
            f"Configured grid has {count} candidates, exceeding maximum_candidate_count="
            f"{configuration.maximum_candidate_count}"
        )
    decimals = tuple(increment * index for index in range(count))
    if not decimals or decimals[0] != Decimal(0) or decimals[-1] > maximum:
        raise RuntimeError("Generated bolus grid violates configured bounds")
    doses = tuple(float(value) for value in decimals)
    converted = torch.tensor(doses, dtype=tensor_dtype)
    if not torch.isfinite(converted).all().item():
        raise ValueError("Configured doses are not finite in the simulator tensor dtype")
    if len(torch.unique(converted)) != len(doses):
        raise ValueError("Distinct configured doses collapse in the simulator tensor dtype")
    return tuple(
        CandidateBolus(f"bolus_{index:04d}", dose)
        for index, dose in enumerate(doses)
    )


def configuration_content_hash(configuration: BolusSearchConfiguration) -> str:
    payload = json.dumps(asdict(configuration), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class CandidateSimulationResult:
    candidate_index: int
    candidate_id: str
    dose_u: float
    simulation_status: str
    prediction_timestamps: tuple[pd.Timestamp, ...]
    predicted_glucose_mg_dl: torch.Tensor
    final_state: torch.Tensor
    failure_reason: str | None
    first_failing_interval: int | None
    first_failing_substep: int | None
    available_prediction_count: int
    roundoff_corrections: int
    trajectory_min_mg_dl: float | None
    trajectory_max_mg_dl: float | None
    endpoint_glucose_mg_dl: float | None
    score: None = None
    score_status: str = "not_implemented_step10"


@dataclass(frozen=True)
class CandidateSearchResult:
    evaluation_event_id: str
    episode_id: str
    patient_id: str
    arm_name: str
    decision_timestamp: pd.Timestamp
    parameter_estimation_timestamp: pd.Timestamp
    fixed_parameters: torch.Tensor
    search_configuration_hash: str
    event_status: str
    candidate_inputs: CandidateInputBatch
    candidates: tuple[CandidateSimulationResult, ...]
    expected_candidate_count: int
    generated_candidate_count: int
    simulated_candidate_count: int
    valid_candidate_count: int
    failed_candidate_count: int
    runtime_seconds: float
    score: None = None
    score_status: str = "not_implemented_step10"


def _available_prefix(predictions: torch.Tensor) -> int:
    finite = torch.isfinite(predictions)
    invalid = (~finite).nonzero().flatten()
    return int(invalid[0].item()) if len(invalid) else len(predictions)


def simulate_bolus_candidates(
    snapshot: DecisionSnapshot,
    search_configuration: BolusSearchConfiguration,
    consumption_configuration: ConsumptionConfiguration,
    known_basal_schedule: KnownBasalSchedule | None = None,
    *,
    weight_kg: float = 70.0,
    substeps: int = 5,
    search_configuration_hash: str | None = None,
) -> CandidateSearchResult:
    """Build and simulate every configured dose without changing the snapshot."""

    started = time.perf_counter()
    validate_decision_snapshot(snapshot)
    state_before = snapshot.physiological_state.detach().clone()
    parameters_before = snapshot.parameters.detach().clone()
    meals_before = snapshot.outstanding_meals
    candidates = generate_bolus_candidates(
        search_configuration, tensor_dtype=snapshot.physiological_state.dtype
    )
    materialized = build_candidate_inputs(
        snapshot, candidates, consumption_configuration, known_basal_schedule
    )
    results: list[CandidateSimulationResult | None] = [None] * len(candidates)
    batch_size = search_configuration.candidate_batch_size
    for start in range(0, len(candidates), batch_size):
        chunk = materialized.candidates[start:start + batch_size]
        states = torch.stack([item.initial_state for item in chunk])
        parameters = torch.stack([item.fixed_parameters for item in chunk])
        inputs = torch.stack([item.future_inputs for item in chunk])
        with torch.inference_mode():
            prediction = predict_from_state(
                states, parameters, inputs, weight_kg=weight_kg, substeps=substeps
            )
        failures = {item.candidate_index: item for item in prediction.validity.failures}
        for local_index, item in enumerate(chunk):
            global_index = start + local_index
            glucose = prediction.glucose_mg_dl[local_index].detach().clone()
            final_state = prediction.final_state[local_index].detach().clone()
            simulator_valid = bool(prediction.validity.valid_mask[local_index].item())
            failure = failures.get(local_index)
            prefix = _available_prefix(glucose)
            status = "simulation_valid"
            reason = None
            failing_interval = failing_substep = None
            if not simulator_valid:
                status = "simulation_failed"
                reason = failure.reason if failure else "simulator_reported_invalid_without_detail"
                failing_interval = failure.first_failing_interval if failure else prefix
                failing_substep = failure.first_failing_substep if failure else None
            elif prefix != len(glucose):
                status, reason, failing_interval = "simulation_failed", "nonfinite_prediction", prefix
            else:
                _, final_reason, _ = _normalize_state(final_state.detach().clone())
                if final_reason is not None:
                    status, reason = "simulation_failed", f"invalid_final_state:{final_reason}"
                    failing_interval = len(glucose) - 1
            finite_prefix = glucose[:prefix]
            minimum = float(finite_prefix.min()) if len(finite_prefix) else None
            maximum = float(finite_prefix.max()) if len(finite_prefix) else None
            endpoint = float(glucose[-1]) if status == "simulation_valid" else None
            results[global_index] = CandidateSimulationResult(
                global_index, item.candidate_id, item.bolus_u, status,
                materialized.output_timestamps, glucose, final_state, reason,
                failing_interval, failing_substep, prefix,
                int(prediction.validity.roundoff_corrections[local_index]),
                minimum, maximum, endpoint,
            )
    completed = tuple(results)
    if any(item is None for item in completed):
        raise RuntimeError("Candidate simulation inventory is incomplete")
    if not torch.equal(snapshot.physiological_state, state_before) \
            or not torch.equal(snapshot.parameters, parameters_before) \
            or snapshot.outstanding_meals != meals_before:
        raise RuntimeError("Candidate search mutated its decision snapshot")
    failed = sum(item.simulation_status == "simulation_failed" for item in completed)
    status = (
        "all_candidate_simulations_failed" if failed == len(completed)
        else "candidate_simulations_completed"
    )
    return CandidateSearchResult(
        snapshot.evaluation_event_id, snapshot.episode_id, snapshot.patient_id,
        snapshot.arm_name, snapshot.decision_timestamp,
        snapshot.parameter_estimation_timestamp, snapshot.parameters.detach().clone(),
        search_configuration_hash or configuration_content_hash(search_configuration),
        status, materialized, completed, len(candidates), len(candidates),
        len(completed), len(completed) - failed, failed,
        time.perf_counter() - started,
    )
