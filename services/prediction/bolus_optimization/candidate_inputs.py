"""Leakage-safe four-hour input construction for explicitly supplied boluses.

This module only snapshots state and materializes simulator inputs.  It does
not run the GRU, forecast glucose, create a dose grid, score, rank or deliver.
Each candidate owns state ``(10,)``, parameters ``(7,)`` and inputs ``(48, 3)``
ordered as basal U/hour, bolus U and consumed carbohydrate g.
"""

from __future__ import annotations

import hashlib
import json
import numbers
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

import numpy as np
import pandas as pd
import torch

from .configuration import PREDICTION_HORIZON_STEPS, SAMPLE_INTERVAL_MINUTES
from .physiology import (
    PARAMETER_NAMES, PHYSIOLOGICAL_INPUT_NAMES, STATE_NAMES,
    _normalize_state, _parameter_reason,
)

if TYPE_CHECKING:
    from .episodes import ArmState, IntervalEvents
    from .events import EvaluationEvent, EventDetectorState


DEFAULT_CONSUMPTION_CONFIGURATION = Path(__file__).with_name(
    "consumption_configuration_v1.json"
)
INTERVAL = pd.Timedelta(minutes=SAMPLE_INTERVAL_MINUTES)
MEAL_QUANTITY_TOLERANCE_G = 1e-6


def _finite_nonnegative(value, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be a numeric value, not a boolean")
    result = float(value)
    if not np.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return result


def _valid_timestamp(value, name: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{name} must be a valid timestamp") from None
    if pd.isna(result):
        raise ValueError(f"{name} must not be NaT")
    return result


@dataclass(frozen=True)
class ConsumptionConfiguration:
    configuration_version: str
    profile_name: str
    interval_fractions: tuple[float, ...]
    sum_tolerance: float = 1e-9
    intended_use: str = "Experimental assumed consumption; not observed future data."

    def __post_init__(self):
        if not self.configuration_version or not self.profile_name:
            raise ValueError("Consumption configuration version and profile name are required")
        tolerance = _finite_nonnegative(self.sum_tolerance, "sum_tolerance")
        if tolerance == 0:
            raise ValueError("sum_tolerance must be positive")
        fractions = tuple(
            _finite_nonnegative(value, f"interval_fractions[{index}]")
            for index, value in enumerate(self.interval_fractions)
        )
        if not fractions:
            raise ValueError("Consumption profile must contain at least one fraction")
        if len(fractions) > PREDICTION_HORIZON_STEPS:
            raise ValueError("Consumption profile does not fit the four-hour horizon")
        if not np.isclose(sum(fractions), 1.0, rtol=0.0, atol=tolerance):
            raise ValueError("Consumption fractions must sum to one; malformed profiles are not normalized")
        object.__setattr__(self, "interval_fractions", fractions)
        object.__setattr__(self, "sum_tolerance", tolerance)


def load_consumption_configuration(path: str | Path = DEFAULT_CONSUMPTION_CONFIGURATION):
    path = Path(path)
    raw = path.read_bytes()
    payload = json.loads(raw)
    payload["interval_fractions"] = tuple(payload["interval_fractions"])
    return ConsumptionConfiguration(**payload), hashlib.sha256(raw).hexdigest()


@dataclass
class MealLedgerEntry:
    meal_identity: str
    announcement_timestamp: pd.Timestamp
    announced_carbs_g: float
    consumed_carbs_g: float = 0.0

    @property
    def remaining_carbs_g(self) -> float:
        return max(0.0, self.announced_carbs_g - self.consumed_carbs_g)

    def clone(self):
        return MealLedgerEntry(
            self.meal_identity, self.announcement_timestamp,
            self.announced_carbs_g, self.consumed_carbs_g,
        )


@dataclass
class MealLedger:
    episode_id: str
    patient_id: str
    entries: list[MealLedgerEntry] = field(default_factory=list)
    unmatched_consumed_carbs_g: float = 0.0
    last_completed_timestamp: pd.Timestamp | None = None

    def clone(self):
        return MealLedger(
            self.episode_id, self.patient_id, [entry.clone() for entry in self.entries],
            self.unmatched_consumed_carbs_g, self.last_completed_timestamp,
        )

    def meal_identity(self, timestamp: pd.Timestamp) -> str:
        return "|".join((self.episode_id, self.patient_id, pd.Timestamp(timestamp).isoformat()))

    def register(self, timestamp, amount_g, identity: str | None = None) -> None:
        timestamp = _valid_timestamp(timestamp, "announcement timestamp")
        amount = _finite_nonnegative(amount_g, "announced carbohydrates")
        if amount == 0:
            return
        identity = identity or self.meal_identity(timestamp)
        existing = next((item for item in self.entries if item.meal_identity == identity), None)
        if existing is not None:
            if existing.announcement_timestamp != timestamp or not np.isclose(
                existing.announced_carbs_g, amount, rtol=0.0, atol=1e-6
            ):
                raise ValueError("Meal identity was reused with different announcement data")
            return
        self.entries.append(MealLedgerEntry(identity, timestamp, amount))

    def consume(self, amount_g) -> None:
        remaining = _finite_nonnegative(amount_g, "consumed carbohydrates")
        for entry in self.entries:
            if remaining <= 1e-9:
                break
            applied = min(entry.remaining_carbs_g, remaining)
            entry.consumed_carbs_g += applied
            remaining -= applied
        if remaining > 1e-9:
            self.unmatched_consumed_carbs_g += remaining

    def committed_interval(self, current_events: "IntervalEvents") -> "MealLedger":
        timestamp = _valid_timestamp(current_events.timestamp, "interval timestamp")
        expected = (
            timestamp - INTERVAL if self.last_completed_timestamp is None
            else self.last_completed_timestamp
        )
        if expected + INTERVAL != timestamp:
            raise ValueError("Meal ledger completion is not on the next five-minute interval")
        updated = self.clone()
        updated.register(timestamp, current_events.carbs_g)
        updated.consume(current_events.consumed_carbs_g)
        updated.last_completed_timestamp = timestamp
        return updated

    @property
    def outstanding_entries(self) -> tuple[MealLedgerEntry, ...]:
        return tuple(entry.clone() for entry in self.entries if entry.remaining_carbs_g > 1e-9)


def initialize_meal_ledger(frame, episode_id: str, patient_id: str) -> MealLedger:
    required = {"timestamp", "carbs_g", "consumed_carbs_g"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing meal-ledger history columns: {sorted(missing)}")
    ledger = MealLedger(episode_id, patient_id)
    previous = None
    for row in frame.loc[:, ["timestamp", "carbs_g", "consumed_carbs_g"]].itertuples(index=False):
        timestamp = _valid_timestamp(row.timestamp, "history timestamp")
        if previous is not None and timestamp - previous != INTERVAL:
            raise ValueError("Meal-ledger history is not contiguous")
        ledger.register(timestamp, row.carbs_g)
        ledger.consume(row.consumed_carbs_g)
        ledger.last_completed_timestamp = timestamp
        previous = timestamp
    return ledger


@dataclass(frozen=True)
class SnapshotMeal:
    meal_identity: str
    announcement_timestamp: pd.Timestamp
    announced_carbs_g: float
    consumed_carbs_g: float
    remaining_carbs_g: float


@dataclass(frozen=True)
class DecisionSnapshot:
    episode_id: str
    patient_id: str
    arm_name: str
    evaluation_event_id: str
    event_type: str
    decision_timestamp: pd.Timestamp
    physiological_state: torch.Tensor
    parameters: torch.Tensor
    parameter_estimation_timestamp: pd.Timestamp
    current_basal_rate_u_per_hour: float
    current_announced_carbs_g: float
    outstanding_meals: tuple[SnapshotMeal, ...]
    unmatched_historical_consumption_g: float


def validate_decision_snapshot(snapshot: DecisionSnapshot) -> DecisionSnapshot:
    """Validate a snapshot without modifying it, using simulator validity rules."""

    if not isinstance(snapshot, DecisionSnapshot):
        raise TypeError("snapshot must be a DecisionSnapshot")
    for name in ("episode_id", "patient_id", "arm_name", "evaluation_event_id", "event_type"):
        if not isinstance(getattr(snapshot, name), str) or not getattr(snapshot, name):
            raise ValueError(f"Snapshot {name} must be a nonempty string")
    timestamp = _valid_timestamp(snapshot.decision_timestamp, "decision timestamp")
    estimation_timestamp = _valid_timestamp(
        snapshot.parameter_estimation_timestamp, "parameter-estimation timestamp"
    )
    if estimation_timestamp > timestamp:
        raise ValueError("Snapshot parameter estimate is after the decision boundary")
    state = snapshot.physiological_state
    if not isinstance(state, torch.Tensor) or not state.dtype.is_floating_point \
            or state.shape != (len(STATE_NAMES),):
        raise ValueError("Snapshot physiological state must be a floating ten-state vector")
    _, state_reason, _ = _normalize_state(state.detach().clone())
    if state_reason is not None:
        raise ValueError(f"Snapshot physiological state is invalid: {state_reason}")
    parameters = snapshot.parameters
    if not isinstance(parameters, torch.Tensor) or not parameters.dtype.is_floating_point \
            or parameters.shape != (len(PARAMETER_NAMES),):
        raise ValueError("Snapshot parameters must be a floating seven-parameter vector")
    parameter_reason = _parameter_reason(parameters.detach().clone())
    if parameter_reason is not None:
        raise ValueError(f"Snapshot parameters are invalid: {parameter_reason}")
    _finite_nonnegative(snapshot.current_basal_rate_u_per_hour, "snapshot default basal rate")
    _finite_nonnegative(snapshot.current_announced_carbs_g, "snapshot current announcement")
    _finite_nonnegative(
        snapshot.unmatched_historical_consumption_g,
        "snapshot unmatched historical consumption",
    )
    identities = set()
    for index, meal in enumerate(snapshot.outstanding_meals):
        if not isinstance(meal, SnapshotMeal):
            raise ValueError(f"Snapshot meal[{index}] has an invalid record type")
        if not meal.meal_identity:
            raise ValueError(f"Snapshot meal[{index}] has an empty identity")
        if meal.meal_identity in identities:
            raise ValueError("Snapshot contains duplicate meal identities")
        identities.add(meal.meal_identity)
        announcement_timestamp = _valid_timestamp(
            meal.announcement_timestamp, f"snapshot meal[{index}] announcement timestamp"
        )
        if announcement_timestamp > timestamp:
            raise ValueError("Snapshot contains a meal announced after the decision boundary")
        announced = _finite_nonnegative(
            meal.announced_carbs_g, f"snapshot meal[{index}] announced carbohydrates"
        )
        consumed = _finite_nonnegative(
            meal.consumed_carbs_g, f"snapshot meal[{index}] consumed carbohydrates"
        )
        remaining = _finite_nonnegative(
            meal.remaining_carbs_g, f"snapshot meal[{index}] remaining carbohydrates"
        )
        if not np.isclose(
            remaining, announced - consumed, rtol=0.0,
            atol=MEAL_QUANTITY_TOLERANCE_G,
        ):
            raise ValueError(
                "Snapshot meal remaining carbohydrates must equal announced minus consumed"
            )
    return snapshot


def create_decision_snapshot(
    arm: "ArmState",
    current_events: "IntervalEvents",
    event: "EvaluationEvent",
    detector_state: "EventDetectorState",
) -> DecisionSnapshot:
    """Copy authoritative boundary state without refreshing, acknowledging or advancing."""

    if arm.status != "active":
        raise RuntimeError(f"Arm is not active: {arm.status}")
    if arm.detector_state is not detector_state:
        raise ValueError("Detector state is not attached to the supplied arm")
    if detector_state.pending_event_id != event.event_id:
        raise RuntimeError("Snapshot event is not the pending evaluation")
    if detector_state.events.get(event.event_id) != event:
        raise ValueError("Snapshot event does not match detector state")
    timestamp = _valid_timestamp(arm.current_timestamp, "arm boundary")
    if not (
        timestamp == _valid_timestamp(current_events.timestamp, "event interval")
        == _valid_timestamp(event.timestamp, "evaluation event")
        == _valid_timestamp(arm.history.current_timestamp, "history boundary")
    ):
        raise ValueError("Event, arm, interval and history timestamps do not agree")
    if (event.episode_id, event.patient_id, event.arm_name) != (
        detector_state.episode_id, detector_state.patient_id, detector_state.arm_name
    ) or event.arm_name != arm.arm_name:
        raise ValueError("Event identity does not match the arm and detector")
    if arm.parameter_estimation_timestamp is None:
        raise RuntimeError("Arm has no active parameter-estimation timestamp")
    estimation_timestamp = _valid_timestamp(
        arm.parameter_estimation_timestamp, "parameter-estimation timestamp"
    )
    if estimation_timestamp > timestamp or event.parameter_estimation_timestamp != estimation_timestamp:
        raise ValueError("Event does not reference the current causal parameter estimate")
    state = arm.physiological_state.detach().clone()
    parameters = arm.parameters.detach().clone()
    if state.shape != (len(STATE_NAMES),) or not torch.isfinite(state).all():
        raise ValueError("Authoritative physiological state must be a finite ten-state vector")
    if parameters.shape != (len(PARAMETER_NAMES),) or not torch.isfinite(parameters).all():
        raise ValueError("Active parameters must be a finite seven-parameter vector")
    basal = _finite_nonnegative(current_events.basal_rate_u_per_hour, "current basal rate")
    announcement = _finite_nonnegative(current_events.carbs_g, "current announcement")
    if not np.isclose(announcement, event.announced_carbs_g, rtol=0.0, atol=1e-6):
        raise ValueError("Current announcement does not match the pending event")
    has_meal_trigger = "meal_announcement" in event.trigger_reasons
    if has_meal_trigger != (announcement > 0):
        raise ValueError("Meal trigger and current announcement are inconsistent")
    if arm.meal_ledger is None:
        raise RuntimeError("Arm has no initialized meal ledger")
    ledger = arm.meal_ledger.clone()
    if ledger.last_completed_timestamp != arm.history.completed_timestamps[-1]:
        raise RuntimeError("Meal ledger is not aligned with completed arm history")
    if has_meal_trigger:
        ledger.register(timestamp, announcement, event.meal_identity)
    outstanding = tuple(
        SnapshotMeal(
            item.meal_identity, item.announcement_timestamp,
            item.announced_carbs_g, item.consumed_carbs_g, item.remaining_carbs_g,
        )
        for item in ledger.outstanding_entries
    )
    snapshot = DecisionSnapshot(
        event.episode_id, event.patient_id, event.arm_name, event.event_id,
        event.event_type, timestamp, state, parameters, estimation_timestamp,
        basal, announcement, outstanding, ledger.unmatched_consumed_carbs_g,
    )
    return validate_decision_snapshot(snapshot)


@dataclass(frozen=True)
class KnownBasalSchedule:
    interval_timestamps: tuple[pd.Timestamp, ...]
    basal_rates_u_per_hour: tuple[float, ...]
    source: str
    availability_timestamp: pd.Timestamp
    units: str = "U/hour"


@dataclass(frozen=True)
class CandidateBolus:
    candidate_id: str
    bolus_u: float


@dataclass(frozen=True)
class CandidateInput:
    candidate_id: str
    bolus_u: float
    initial_state: torch.Tensor
    fixed_parameters: torch.Tensor
    future_inputs: torch.Tensor


@dataclass(frozen=True)
class CandidateInputBatch:
    snapshot: DecisionSnapshot
    interval_timestamps: tuple[pd.Timestamp, ...]
    output_timestamps: tuple[pd.Timestamp, ...]
    input_names: tuple[str, ...]
    candidates: tuple[CandidateInput, ...]
    assumed_consumed_carbs_g: torch.Tensor
    outstanding_carbs_g: float
    basal_source: str
    basal_availability_timestamp: pd.Timestamp
    consumption_profile_name: str


def _candidate(value, index: int) -> CandidateBolus:
    if isinstance(value, CandidateBolus):
        candidate = value
    elif isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
        candidate = CandidateBolus(value[0], value[1])
    else:
        candidate = CandidateBolus(f"candidate_{index:03d}", value)
    if not candidate.candidate_id:
        raise ValueError("Candidate identifiers must be nonempty")
    return CandidateBolus(candidate.candidate_id, _finite_nonnegative(candidate.bolus_u, "candidate bolus"))


def build_candidate_inputs(
    snapshot: DecisionSnapshot,
    candidate_bolus_values: Iterable[float | CandidateBolus | tuple[str, float]],
    consumption_configuration: ConsumptionConfiguration,
    known_basal_schedule: KnownBasalSchedule | None = None,
) -> CandidateInputBatch:
    validate_decision_snapshot(snapshot)
    timestamp = pd.Timestamp(snapshot.decision_timestamp)
    intervals = tuple(timestamp + index * INTERVAL for index in range(PREDICTION_HORIZON_STEPS))
    outputs = tuple(value + INTERVAL for value in intervals)
    dtype, device = snapshot.physiological_state.dtype, snapshot.physiological_state.device
    if known_basal_schedule is None:
        basal_values = [snapshot.current_basal_rate_u_per_hour] * PREDICTION_HORIZON_STEPS
        basal_source = "constant_current_available_basal"
        basal_available = timestamp
    else:
        schedule_times = tuple(
            _valid_timestamp(value, "known basal schedule timestamp")
            for value in known_basal_schedule.interval_timestamps
        )
        if schedule_times != intervals:
            raise ValueError("Known basal schedule must exactly and uniquely cover all 48 intervals")
        if len(known_basal_schedule.basal_rates_u_per_hour) != PREDICTION_HORIZON_STEPS:
            raise ValueError("Known basal schedule must provide exactly 48 rates")
        if known_basal_schedule.units != "U/hour" or not known_basal_schedule.source:
            raise ValueError("Known basal schedule requires source and U/hour units")
        basal_available = _valid_timestamp(
            known_basal_schedule.availability_timestamp, "basal availability timestamp"
        )
        if basal_available > timestamp:
            raise ValueError("Known basal schedule was not available at the decision boundary")
        basal_values = [
            _finite_nonnegative(value, f"basal schedule rate[{index}]")
            for index, value in enumerate(known_basal_schedule.basal_rates_u_per_hour)
        ]
        basal_source = known_basal_schedule.source
    outstanding = sum(item.remaining_carbs_g for item in snapshot.outstanding_meals)
    profile = consumption_configuration.interval_fractions
    carbohydrates = np.zeros(PREDICTION_HORIZON_STEPS, dtype=np.float64)
    carbohydrates[:len(profile)] = outstanding * np.asarray(profile, dtype=np.float64)
    tolerance = max(consumption_configuration.sum_tolerance, 1e-7 * max(1.0, outstanding))
    if not np.isclose(carbohydrates.sum(), outstanding, rtol=0.0, atol=tolerance):
        raise RuntimeError("Generated assumed consumption does not conserve outstanding meal grams")
    base = torch.zeros(
        (PREDICTION_HORIZON_STEPS, len(PHYSIOLOGICAL_INPUT_NAMES)),
        dtype=dtype, device=device,
    )
    base[:, 0] = torch.as_tensor(basal_values, dtype=dtype, device=device)
    base[:, 2] = torch.as_tensor(carbohydrates, dtype=dtype, device=device)
    normalized = tuple(_candidate(value, index) for index, value in enumerate(candidate_bolus_values))
    if not normalized:
        raise ValueError("At least one caller-supplied candidate bolus is required")
    identifiers = [item.candidate_id for item in normalized]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Candidate identifiers must be unique")
    candidates = []
    for item in normalized:
        inputs = base.clone()
        inputs[0, 1] = item.bolus_u
        if inputs.shape != (PREDICTION_HORIZON_STEPS, len(PHYSIOLOGICAL_INPUT_NAMES)):
            raise RuntimeError("Materialized candidate input tensor has an invalid shape")
        if not torch.isfinite(inputs).all().item() or (inputs < 0).any().item():
            raise ValueError("Materialized candidate inputs must be finite and nonnegative")
        candidates.append(CandidateInput(
            item.candidate_id, item.bolus_u,
            snapshot.physiological_state.detach().clone(),
            snapshot.parameters.detach().clone(), inputs,
        ))
    return CandidateInputBatch(
        snapshot, intervals, outputs, PHYSIOLOGICAL_INPUT_NAMES, tuple(candidates),
        base[:, 2].clone(), float(outstanding), basal_source, basal_available,
        consumption_configuration.profile_name,
    )
