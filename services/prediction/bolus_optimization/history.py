"""Timestamped, bounded per-arm histories and atomic interval completion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import torch

from final_model_adapter import HISTORY

from .configuration import MODEL_FEATURES, SAMPLE_INTERVAL_MINUTES
from .physiology import MG_DL_PER_MMOL_L, STATE_NAMES, VG_L_PER_KG, advance_state

if TYPE_CHECKING:
    from .episodes import ArmState, IntervalEvents


INTERVAL = pd.Timedelta(minutes=SAMPLE_INTERVAL_MINUTES)


@dataclass
class EvolvingHistory:
    """Exactly 288 completed rows plus one separate current boundary."""

    completed_timestamps: list[pd.Timestamp]
    completed_glucose_mg_dl: torch.Tensor
    completed_basal_u_per_hour: torch.Tensor
    completed_bolus_u: torch.Tensor
    completed_announced_carbs_g: torch.Tensor
    completed_consumed_carbs_g: torch.Tensor
    completed_sources: list[str]
    current_timestamp: pd.Timestamp
    current_glucose_mg_dl: float
    current_source: str
    audit_trajectory: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_recorded_prehistory(
        cls,
        frame: pd.DataFrame,
        *,
        current_timestamp: pd.Timestamp,
        current_glucose_mg_dl: float,
    ) -> "EvolvingHistory":
        required = {
            "timestamp", "cgm_mg_dl", "basal_rate_u_per_hour", "bolus_u",
            "carbs_g", "consumed_carbs_g",
        }
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"Missing history columns: {sorted(missing)}")
        if len(frame) != HISTORY:
            raise ValueError(f"Recorded history must contain exactly {HISTORY} rows")
        timestamps = [pd.Timestamp(value) for value in frame["timestamp"]]
        if timestamps[-1] + INTERVAL != pd.Timestamp(current_timestamp):
            raise ValueError("Recorded history does not end at the current boundary")
        if any(right - left != INTERVAL for left, right in zip(timestamps, timestamps[1:])):
            raise ValueError("Recorded history timestamps are not contiguous")
        tensor = lambda name: torch.as_tensor(
            frame[name].to_numpy(dtype="float32", copy=True), dtype=torch.float32
        )
        trajectory = [
            {
                "timestamp": timestamp,
                "glucose_mg_dl": float(glucose),
                "source": "recorded_prehistory",
            }
            for timestamp, glucose in zip(timestamps, frame["cgm_mg_dl"])
        ]
        trajectory.append({
            "timestamp": pd.Timestamp(current_timestamp),
            "glucose_mg_dl": float(current_glucose_mg_dl),
            "source": "recorded_prehistory",
        })
        return cls(
            timestamps,
            tensor("cgm_mg_dl"), tensor("basal_rate_u_per_hour"),
            tensor("bolus_u"), tensor("carbs_g"), tensor("consumed_carbs_g"),
            ["recorded_prehistory"] * HISTORY,
            pd.Timestamp(current_timestamp), float(current_glucose_mg_dl),
            "recorded_prehistory", trajectory,
        )

    def clone(self) -> "EvolvingHistory":
        return EvolvingHistory(
            list(self.completed_timestamps),
            self.completed_glucose_mg_dl.clone(),
            self.completed_basal_u_per_hour.clone(),
            self.completed_bolus_u.clone(),
            self.completed_announced_carbs_g.clone(),
            self.completed_consumed_carbs_g.clone(),
            list(self.completed_sources), self.current_timestamp,
            self.current_glucose_mg_dl, self.current_source,
            [dict(item) for item in self.audit_trajectory],
        )

    def validate(self) -> None:
        tensors = (
            self.completed_glucose_mg_dl, self.completed_basal_u_per_hour,
            self.completed_bolus_u, self.completed_announced_carbs_g,
            self.completed_consumed_carbs_g,
        )
        if len(self.completed_timestamps) != HISTORY or any(len(value) != HISTORY for value in tensors):
            raise RuntimeError("Rolling history is not exactly 288 completed intervals")
        if len(self.completed_sources) != HISTORY:
            raise RuntimeError("History source labels are misaligned")
        if any(right - left != INTERVAL for left, right in zip(
            self.completed_timestamps, self.completed_timestamps[1:]
        )):
            raise RuntimeError("Completed history timestamps are not contiguous")
        if self.completed_timestamps[-1] + INTERVAL != self.current_timestamp:
            raise RuntimeError("Completed history does not align to the current boundary")
        if not all(torch.isfinite(value).all().item() for value in tensors):
            raise RuntimeError("History contains nonfinite values")

    def gru_input(self, current_events: "IntervalEvents") -> torch.Tensor:
        """Build 288 completed rows plus the prospective current boundary."""

        self.validate()
        if pd.Timestamp(current_events.timestamp) != self.current_timestamp:
            raise ValueError("Current events do not align with the history boundary")
        completed = torch.stack((
            self.completed_glucose_mg_dl,
            self.completed_basal_u_per_hour,
            self.completed_bolus_u,
            self.completed_announced_carbs_g,
        ), dim=1)
        boundary = torch.tensor([[
            self.current_glucose_mg_dl,
            current_events.basal_rate_u_per_hour,
            0.0,
            current_events.carbs_g,
        ]], dtype=completed.dtype, device=completed.device)
        result = torch.cat((completed, boundary), dim=0)
        if result.shape != (HISTORY + 1, len(MODEL_FEATURES)):
            raise RuntimeError("GRU history shape invariant failed")
        return result

    def inference_timestamps(self) -> tuple[pd.Timestamp, ...]:
        return tuple(self.completed_timestamps + [self.current_timestamp])

    def committed_copy(
        self,
        current_events: "IntervalEvents",
        delivered_bolus_u: float,
        next_glucose_mg_dl: float,
    ) -> "EvolvingHistory":
        """Return a new rolling history; the caller swaps it in atomically."""

        if pd.Timestamp(current_events.timestamp) != self.current_timestamp:
            raise ValueError("Interval events do not align with the current boundary")
        if not np.isfinite(delivered_bolus_u) or delivered_bolus_u < 0:
            raise ValueError("Delivered bolus must be finite and nonnegative")
        if not np.isfinite(next_glucose_mg_dl) or next_glucose_mg_dl <= 0:
            raise ValueError("Next glucose must be finite and positive")

        def roll(values: torch.Tensor, value: float) -> torch.Tensor:
            appended = torch.tensor([value], dtype=values.dtype, device=values.device)
            return torch.cat((values[1:], appended), dim=0)

        updated = EvolvingHistory(
            self.completed_timestamps[1:] + [self.current_timestamp],
            roll(self.completed_glucose_mg_dl, self.current_glucose_mg_dl),
            roll(self.completed_basal_u_per_hour, current_events.basal_rate_u_per_hour),
            roll(self.completed_bolus_u, delivered_bolus_u),
            roll(self.completed_announced_carbs_g, current_events.carbs_g),
            roll(self.completed_consumed_carbs_g, current_events.consumed_carbs_g),
            self.completed_sources[1:] + [self.current_source],
            self.current_timestamp + INTERVAL,
            float(next_glucose_mg_dl), "simulated",
            [*self.audit_trajectory, {
                "timestamp": self.current_timestamp + INTERVAL,
                "glucose_mg_dl": float(next_glucose_mg_dl),
                "source": "simulated",
            }],
        )
        updated.validate()
        return updated


@dataclass(frozen=True)
class IntervalCompletion:
    success: bool
    timestamp: pd.Timestamp
    next_timestamp: pd.Timestamp | None
    next_glucose_mg_dl: float | None
    roundoff_corrections: int
    failure_reason: str | None


def complete_interval(
    arm: "ArmState",
    current_events: "IntervalEvents",
    delivered_bolus_u: float,
    *,
    weight_kg: float = 70.0,
    substeps: int = 5,
    delivery_source: str = "externally_supplied_action",
) -> IntervalCompletion:
    """Advance and atomically commit one five-minute interval to one arm."""

    timestamp = pd.Timestamp(current_events.timestamp)
    if arm.status != "active":
        raise RuntimeError(f"Arm is not active: {arm.status}")
    if arm.detector_state is not None and arm.detector_state.pending_event_id is not None:
        raise RuntimeError("Cannot advance with an unresolved pending evaluation")
    if timestamp != arm.current_timestamp or timestamp != arm.history.current_timestamp:
        raise ValueError("Interval timestamp does not match the arm clock")
    if timestamp in arm.event_bookkeeping["applied_events"]:
        raise RuntimeError("Interval has already been applied")
    if not np.isfinite(delivered_bolus_u) or delivered_bolus_u < 0:
        reason = "invalid_delivered_bolus"
        arm.status, arm.failure_reason = "failed_advancement", reason
        arm.event_bookkeeping.setdefault("attempted_intervals", []).append({
            "timestamp": timestamp, "delivered_bolus_u": delivered_bolus_u,
            "status": "failed", "reason": reason,
        })
        return IntervalCompletion(False, timestamp, None, None, 0, reason)
    if not isinstance(delivery_source, str) or not delivery_source:
        raise ValueError("delivery_source must be a nonempty string")
    next_meal_ledger = (
        arm.meal_ledger.committed_interval(current_events)
        if arm.meal_ledger is not None else None
    )
    interval_inputs = torch.tensor([
        current_events.basal_rate_u_per_hour,
        delivered_bolus_u,
        current_events.consumed_carbs_g,
    ], dtype=arm.physiological_state.dtype, device=arm.physiological_state.device)
    result = advance_state(
        arm.physiological_state, arm.parameters, interval_inputs,
        weight_kg=weight_kg, substeps=substeps,
    )
    corrections = result.validity.roundoff_corrections[0]
    if not result.validity.all_valid:
        failure = result.validity.failures[0]
        reason = f"{failure.reason}@substep_{failure.first_failing_substep}"
        arm.status, arm.failure_reason = "failed_advancement", reason
        arm.event_bookkeeping.setdefault("attempted_intervals", []).append({
            "timestamp": timestamp, "delivered_bolus_u": float(delivered_bolus_u),
            "status": "failed", "reason": reason,
        })
        return IntervalCompletion(False, timestamp, None, None, corrections, reason)
    next_state = result.state
    next_glucose = float(
        next_state[0].item() / (VG_L_PER_KG * weight_kg) * MG_DL_PER_MMOL_L
    )
    try:
        next_history = arm.history.committed_copy(
            current_events, float(delivered_bolus_u), next_glucose
        )
    except Exception as error:
        reason = f"history_commit_failed:{type(error).__name__}:{error}"
        arm.status, arm.failure_reason = "failed_advancement", reason
        arm.event_bookkeeping.setdefault("attempted_intervals", []).append({
            "timestamp": timestamp, "delivered_bolus_u": float(delivered_bolus_u),
            "status": "failed", "reason": reason,
        })
        return IntervalCompletion(False, timestamp, None, None, corrections, reason)

    arm.physiological_state = next_state.detach().clone()
    arm.history = next_history
    arm.meal_ledger = next_meal_ledger
    arm.current_timestamp = next_history.current_timestamp
    arm.glucose_history = torch.cat((
        next_history.completed_glucose_mg_dl[-72:],
        torch.tensor(
            [next_glucose], dtype=arm.glucose_history.dtype,
            device=arm.glucose_history.device,
        ),
    ))
    arm.applied_input_history = torch.stack((
        next_history.completed_basal_u_per_hour[-72:],
        next_history.completed_bolus_u[-72:],
        next_history.completed_consumed_carbs_g[-72:],
    ), dim=1)
    arm.event_bookkeeping["applied_events"].append(timestamp)
    arm.event_bookkeeping.setdefault("attempted_intervals", []).append({
        "timestamp": timestamp, "delivered_bolus_u": float(delivered_bolus_u),
        "status": "completed", "reason": None,
    })
    arm.roundoff_corrections += corrections
    if arm.detector_state is not None and delivered_bolus_u > 0:
        from .events import record_successful_delivery
        record_successful_delivery(
            arm.detector_state, timestamp, float(delivered_bolus_u),
            source=delivery_source,
        )
    return IntervalCompletion(
        True, timestamp, arm.current_timestamp, next_glucose, corrections, None
    )


def current_glucose_mg_dl(arm: "ArmState", *, weight_kg: float = 70.0) -> float:
    """Read glucose from physiological Q1 and assert history alignment."""

    value = float(
        arm.physiological_state[STATE_NAMES.index("Q1")].item()
        / (VG_L_PER_KG * weight_kg) * MG_DL_PER_MMOL_L
    )
    if not np.isclose(value, arm.history.current_glucose_mg_dl, rtol=1e-6, atol=1e-5):
        raise RuntimeError("Physiological state and current history glucose disagree")
    return value
