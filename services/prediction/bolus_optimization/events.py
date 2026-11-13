"""Meal and persistent-high-glucose evaluation detection without dose selection."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import torch

from .configuration import SAMPLE_INTERVAL_MINUTES
from .configuration_loading import (
    DEFAULT_RESEARCH_CONFIGURATION, load_component_payload,
)
from .history import current_glucose_mg_dl

if TYPE_CHECKING:
    from .episodes import ArmState, EpisodeDefinition, IntervalEvents


DEFAULT_TRIGGER_CONFIGURATION = DEFAULT_RESEARCH_CONFIGURATION
ACKNOWLEDGEMENT_STATUSES = {"completed", "cancelled", "failed"}
RETRY_POLICIES = {"no_retry_until_glucose_resets", "caller_managed_retry"}


@dataclass(frozen=True)
class TriggerConfiguration:
    configuration_version: str
    high_glucose_threshold_mg_dl: float
    high_glucose_persistence_minutes: int
    high_glucose_reassessment_minutes: int
    intended_use: str = "Experimental simulation diagnostic only."

    def __post_init__(self):
        threshold = self.high_glucose_threshold_mg_dl
        if isinstance(threshold, (bool, np.bool_)) or not isinstance(
            threshold, (int, float, np.integer, np.floating)
        ) or not np.isfinite(threshold) or threshold <= 0:
            raise ValueError("high_glucose_threshold_mg_dl must be finite and positive")
        for name, value, allow_zero in (
            ("high_glucose_persistence_minutes", self.high_glucose_persistence_minutes, True),
            ("high_glucose_reassessment_minutes", self.high_glucose_reassessment_minutes, False),
        ):
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
                raise ValueError(f"{name} must be an integer")
            if value < 0 or (not allow_zero and value == 0) or value % SAMPLE_INTERVAL_MINUTES:
                qualifier = "nonnegative" if allow_zero else "positive"
                raise ValueError(f"{name} must be a {qualifier} multiple of five minutes")
        if not self.configuration_version:
            raise ValueError("configuration_version is required")


def load_trigger_configuration(path: str | Path = DEFAULT_TRIGGER_CONFIGURATION):
    _, _, payload, content_hash = load_component_payload(path, "trigger")
    configuration = TriggerConfiguration(**payload)
    return configuration, content_hash


@dataclass(frozen=True)
class EvaluationEvent:
    event_id: str
    episode_id: str
    patient_id: str
    arm_name: str
    timestamp: pd.Timestamp
    event_type: str
    trigger_reasons: tuple[str, ...]
    meal_identity: str | None
    announced_carbs_g: float
    glucose_mg_dl: float
    high_persistence_minutes: int
    parameter_estimation_timestamp: pd.Timestamp


@dataclass(frozen=True)
class EventDetectionResult:
    timestamp: pd.Timestamp
    evaluation_eligible: bool
    event: EvaluationEvent | None
    trigger_reasons: tuple[str, ...]
    suppression_reasons: tuple[str, ...]
    current_glucose_mg_dl: float
    high_persistence_start_timestamp: pd.Timestamp | None
    high_persistence_minutes: int
    announced_carbs_g: float
    latest_parameter_estimation_timestamp: pd.Timestamp
    previous_evaluation_timestamp: pd.Timestamp | None
    previous_delivery_timestamp: pd.Timestamp | None
    pending_event_id: str | None
    already_emitted: bool = False


@dataclass(frozen=True)
class EvaluationOutcome:
    event_id: str
    acknowledgement_timestamp: pd.Timestamp
    status: str
    outcome: str
    selected_dose_u: float | None
    retry_policy: str | None


@dataclass(frozen=True)
class DeliveryRecord:
    timestamp: pd.Timestamp
    delivered_bolus_u: float
    source: str


@dataclass
class EventDetectorState:
    episode_id: str
    patient_id: str
    arm_name: str
    episode_start_timestamp: pd.Timestamp
    episode_end_timestamp: pd.Timestamp
    pending_event_id: str | None = None
    processed_meal_identities: set[str] = field(default_factory=set)
    boundary_results: dict[pd.Timestamp, EventDetectionResult] = field(default_factory=dict)
    events: dict[str, EvaluationEvent] = field(default_factory=dict)
    outcomes: dict[str, EvaluationOutcome] = field(default_factory=dict)
    deliveries: list[DeliveryRecord] = field(default_factory=list)
    last_evaluation_timestamp: pd.Timestamp | None = None
    last_completed_high_glucose_evaluation_timestamp: pd.Timestamp | None = None
    high_glucose_retry_blocked: bool = False
    high_glucose_retry_policy: str | None = None


def create_detector_state(arm: "ArmState", definition: "EpisodeDefinition") -> EventDetectorState:
    deliveries = [
        DeliveryRecord(timestamp, float(dose), "recorded_prehistory")
        for timestamp, dose in zip(
            arm.history.completed_timestamps, arm.history.completed_bolus_u.tolist()
        )
        if dose > 0
    ]
    return EventDetectorState(
        definition.episode_id, definition.patient_id, arm.arm_name,
        definition.start_timestamp, definition.end_timestamp,
        deliveries=deliveries,
    )


def _continuous_high(history, threshold: float):
    observations = history.audit_trajectory
    if not observations:
        return None, 0
    current_timestamp = history.current_timestamp
    current = observations[-1]
    if pd.Timestamp(current["timestamp"]) != current_timestamp:
        return None, 0
    try:
        glucose = float(current["glucose_mg_dl"])
    except (TypeError, ValueError):
        return None, 0
    if not math.isfinite(glucose) or glucose < threshold:
        return None, 0
    earliest = current_timestamp
    previous = current_timestamp
    for observation in reversed(observations[:-1]):
        timestamp = pd.Timestamp(observation["timestamp"])
        if previous - timestamp != pd.Timedelta(minutes=SAMPLE_INTERVAL_MINUTES):
            break
        try:
            value = float(observation["glucose_mg_dl"])
        except (TypeError, ValueError):
            break
        if not math.isfinite(value) or value < threshold:
            break
        earliest = timestamp
        previous = timestamp
    return earliest, int((current_timestamp - earliest).total_seconds() // 60)


def _event_id(state: EventDetectorState, timestamp: pd.Timestamp, event_type: str) -> str:
    identity = "|".join((
        state.episode_id, state.patient_id, state.arm_name,
        pd.Timestamp(timestamp).isoformat(), event_type,
    ))
    return "evaluation_" + hashlib.sha256(identity.encode()).hexdigest()[:20]


def detect_evaluation_event(
    arm: "ArmState",
    current_events: "IntervalEvents",
    configuration: TriggerConfiguration,
    detector_state: EventDetectorState,
    *,
    weight_kg: float = 70.0,
) -> EventDetectionResult:
    """Detect one actionable evaluation at the current boundary, idempotently."""

    timestamp = pd.Timestamp(arm.current_timestamp)
    if detector_state.arm_name != arm.arm_name:
        raise ValueError("Detector state belongs to a different arm")
    if timestamp != pd.Timestamp(current_events.timestamp) or timestamp != arm.history.current_timestamp:
        raise ValueError("Detection inputs do not align with the arm boundary")
    if timestamp in detector_state.boundary_results:
        return replace(detector_state.boundary_results[timestamp], already_emitted=True)

    # Validate the boundary observation against physiological Q1, then use the
    # stored observation value so exact configured thresholds are not changed
    # by a second mmol/L-to-mg/dL floating-point round trip.
    current_glucose_mg_dl(arm, weight_kg=weight_kg)
    glucose = float(arm.history.current_glucose_mg_dl)
    state_before = arm.physiological_state.detach().clone()
    parameters_before = arm.parameters.detach().clone()
    history_before = arm.history.clone()
    previous_evaluation = detector_state.last_evaluation_timestamp
    previous_delivery = (
        detector_state.deliveries[-1].timestamp if detector_state.deliveries else None
    )
    persistence_start, persistence_minutes = _continuous_high(
        arm.history, configuration.high_glucose_threshold_mg_dl
    )
    suppression = []
    reasons = []
    meal_identity = None

    if timestamp >= detector_state.episode_end_timestamp:
        suppression.append("terminal_boundary")
    else:
        if current_events.carbs_g > 0:
            meal_identity = "|".join((
                detector_state.episode_id, detector_state.patient_id,
                timestamp.isoformat(),
            ))
            if meal_identity not in detector_state.processed_meal_identities:
                reasons.append("meal_announcement")
                detector_state.processed_meal_identities.add(meal_identity)
            else:
                suppression.append("meal_announcement_already_processed")

        high_now = glucose >= configuration.high_glucose_threshold_mg_dl
        persistent = high_now and persistence_minutes >= configuration.high_glucose_persistence_minutes
        high_eligible = persistent
        if high_now and not persistent:
            suppression.append("high_glucose_persistence_not_met")
        if not high_now:
            detector_state.high_glucose_retry_blocked = False
            detector_state.high_glucose_retry_policy = None
        if high_eligible and detector_state.high_glucose_retry_blocked:
            high_eligible = False
            suppression.append("high_glucose_retry_requires_explicit_policy_action")
        last_high = detector_state.last_completed_high_glucose_evaluation_timestamp
        if high_eligible and last_high is not None:
            elapsed = int((timestamp - last_high).total_seconds() // 60)
            if elapsed < configuration.high_glucose_reassessment_minutes:
                high_eligible = False
                suppression.append("high_glucose_reassessment_not_elapsed")
        if high_eligible:
            reasons.append("persistent_high_glucose")

        if detector_state.pending_event_id is not None:
            suppression.append("pending_evaluation_unresolved")
            reasons = []

    event = None
    if reasons:
        event_type = (
            "meal_and_high_glucose" if len(reasons) == 2
            else "meal" if reasons[0] == "meal_announcement"
            else "high_glucose"
        )
        event = EvaluationEvent(
            _event_id(detector_state, timestamp, event_type),
            detector_state.episode_id, detector_state.patient_id,
            detector_state.arm_name, timestamp, event_type, tuple(reasons),
            meal_identity, float(current_events.carbs_g), glucose,
            persistence_minutes, pd.Timestamp(arm.parameter_estimation_timestamp),
        )
        detector_state.events[event.event_id] = event
        detector_state.pending_event_id = event.event_id
        detector_state.last_evaluation_timestamp = timestamp

    result = EventDetectionResult(
        timestamp, event is not None, event, tuple(reasons), tuple(suppression),
        glucose, persistence_start, persistence_minutes,
        float(current_events.carbs_g), pd.Timestamp(arm.parameter_estimation_timestamp),
        previous_evaluation, previous_delivery, detector_state.pending_event_id, False,
    )
    if not torch_equal_state(arm, state_before, parameters_before, history_before):
        raise RuntimeError("Event detection mutated physiological state, parameters or history")
    detector_state.boundary_results[timestamp] = result
    return result


def torch_equal_state(arm, state, parameters, history) -> bool:
    return bool(
        torch.equal(arm.physiological_state, state)
        and torch.equal(arm.parameters, parameters)
        and all(torch.equal(getattr(arm.history, name), getattr(history, name)) for name in (
            "completed_glucose_mg_dl", "completed_basal_u_per_hour",
            "completed_bolus_u", "completed_announced_carbs_g",
            "completed_consumed_carbs_g",
        ))
        and arm.history.completed_timestamps == history.completed_timestamps
        and arm.history.completed_sources == history.completed_sources
        and arm.history.current_timestamp == history.current_timestamp
        and arm.history.current_glucose_mg_dl == history.current_glucose_mg_dl
        and arm.history.current_source == history.current_source
        and arm.history.audit_trajectory == history.audit_trajectory
    )


def acknowledge_evaluation(
    detector_state: EventDetectorState,
    event_id: str,
    *,
    status: str,
    outcome: str,
    acknowledgement_timestamp: pd.Timestamp,
    selected_dose_u: float | None = None,
    retry_policy: str | None = None,
) -> EvaluationOutcome:
    if status not in ACKNOWLEDGEMENT_STATUSES:
        raise ValueError(f"Invalid acknowledgement status: {status}")
    if event_id in detector_state.outcomes:
        raise RuntimeError("Evaluation has already been acknowledged")
    if detector_state.pending_event_id != event_id or event_id not in detector_state.events:
        raise RuntimeError("Acknowledgement does not match the pending evaluation")
    if not outcome:
        raise ValueError("An explicit evaluation outcome is required")
    if selected_dose_u is not None:
        if isinstance(selected_dose_u, bool) or not np.isfinite(selected_dose_u) or selected_dose_u < 0:
            raise ValueError("selected_dose_u must be finite and nonnegative")
    if status in {"cancelled", "failed"}:
        if retry_policy not in RETRY_POLICIES:
            raise ValueError("Cancelled/failed evaluations require an explicit retry policy")
    elif retry_policy is not None:
        raise ValueError("Completed evaluations must not specify a retry policy")
    event = detector_state.events[event_id]
    try:
        timestamp = pd.Timestamp(acknowledgement_timestamp)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Acknowledgement timestamp must be valid") from None
    if pd.isna(timestamp):
        raise ValueError("Acknowledgement timestamp must not be NaT")
    if timestamp != event.timestamp:
        raise ValueError(
            "Acknowledgement timestamp must equal the pending event decision boundary"
        )
    record = EvaluationOutcome(
        event_id, timestamp, status, outcome,
        None if selected_dose_u is None else float(selected_dose_u), retry_policy,
    )
    detector_state.outcomes[event_id] = record
    detector_state.pending_event_id = None
    if status == "completed" and "persistent_high_glucose" in event.trigger_reasons:
        detector_state.last_completed_high_glucose_evaluation_timestamp = timestamp
    if status in {"cancelled", "failed"} and "persistent_high_glucose" in event.trigger_reasons:
        detector_state.high_glucose_retry_blocked = True
        detector_state.high_glucose_retry_policy = retry_policy
    return record


def authorize_high_glucose_retry(detector_state: EventDetectorState) -> None:
    if detector_state.high_glucose_retry_policy != "caller_managed_retry":
        raise RuntimeError("No caller-managed high-glucose retry is awaiting authorization")
    detector_state.high_glucose_retry_blocked = False
    detector_state.high_glucose_retry_policy = None


def record_successful_delivery(
    detector_state: EventDetectorState,
    timestamp: pd.Timestamp,
    delivered_bolus_u: float,
    *,
    source: str,
) -> DeliveryRecord | None:
    if isinstance(delivered_bolus_u, bool) or not np.isfinite(delivered_bolus_u) or delivered_bolus_u < 0:
        raise ValueError("Delivered bolus must be finite and nonnegative")
    if delivered_bolus_u == 0:
        return None
    timestamp = pd.Timestamp(timestamp)
    if detector_state.deliveries and timestamp <= detector_state.deliveries[-1].timestamp:
        raise RuntimeError("Delivery timestamps must be strictly increasing")
    record = DeliveryRecord(timestamp, float(delivered_bolus_u), source)
    detector_state.deliveries.append(record)
    return record
