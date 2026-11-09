"""Shared simulated-time schedule for frozen-GRU parameter replacement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import torch

from final_model_adapter import LOWER, UPPER

from .checkpoint import FrozenGRU, predict_parameters
from .configuration import SAMPLE_INTERVAL_MINUTES
from .physiology import PARAMETER_NAMES

if TYPE_CHECKING:
    from .episodes import ArmState, IntervalEvents


class SchedulingError(RuntimeError):
    pass


@dataclass(frozen=True)
class RefreshConfiguration:
    parameter_refresh_minutes: int = 120
    episode_minutes: int = 24 * 60

    def __post_init__(self):
        for name, value in (
            ("parameter_refresh_minutes", self.parameter_refresh_minutes),
            ("episode_minutes", self.episode_minutes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
            if value % SAMPLE_INTERVAL_MINUTES:
                raise ValueError(f"{name} must be a multiple of five minutes")

    @property
    def scheduled_offsets(self) -> tuple[int, ...]:
        return tuple(range(
            self.parameter_refresh_minutes,
            self.episode_minutes,
            self.parameter_refresh_minutes,
        ))


@dataclass(frozen=True)
class ActiveParameters:
    values: torch.Tensor
    estimation_timestamp: pd.Timestamp


@dataclass(frozen=True)
class RefreshResult:
    performed: bool
    timestamp: pd.Timestamp
    scheduled_offset_minutes: int | None
    status: str
    failure_reason: str | None = None


def latest_active_parameters(arm: "ArmState") -> ActiveParameters:
    """Return a defensive parameter copy and its estimation timestamp."""

    if arm.parameter_estimation_timestamp is None:
        raise RuntimeError("Arm has no parameter estimation timestamp")
    return ActiveParameters(
        arm.parameters.detach().clone(), pd.Timestamp(arm.parameter_estimation_timestamp)
    )


def _elapsed_minutes(arm: "ArmState") -> int:
    if arm.episode_start_timestamp is None:
        raise RuntimeError("Arm has no episode-start timestamp")
    seconds = (arm.current_timestamp - arm.episode_start_timestamp).total_seconds()
    if seconds < 0 or seconds % (SAMPLE_INTERVAL_MINUTES * 60):
        raise SchedulingError("Arm clock is not on the episode five-minute grid")
    return int(seconds // 60)


def _valid_parameters(values: torch.Tensor) -> tuple[bool, str | None]:
    if values.shape != (len(PARAMETER_NAMES),):
        return False, f"invalid_parameter_shape:{tuple(values.shape)}"
    if not torch.isfinite(values).all():
        return False, "nonfinite_parameters"
    lower = torch.tensor(LOWER, dtype=values.dtype, device=values.device)
    upper = torch.tensor(UPPER, dtype=values.dtype, device=values.device)
    if bool(((values < lower) | (values > upper)).any().item()):
        return False, "parameters_outside_valid_bounds"
    return True, None


def _histories_equal(first, second) -> bool:
    return bool(
        first.completed_timestamps == second.completed_timestamps
        and first.completed_sources == second.completed_sources
        and first.current_timestamp == second.current_timestamp
        and first.current_glucose_mg_dl == second.current_glucose_mg_dl
        and first.current_source == second.current_source
        and all(torch.equal(getattr(first, name), getattr(second, name)) for name in (
            "completed_glucose_mg_dl", "completed_basal_u_per_hour",
            "completed_bolus_u", "completed_announced_carbs_g",
            "completed_consumed_carbs_g",
        ))
    )


def refresh_parameters_if_due(
    arm: "ArmState",
    frozen_gru: FrozenGRU,
    current_events: "IntervalEvents",
    refresh_configuration: RefreshConfiguration,
) -> RefreshResult:
    """Replace active parameters at an exact scheduled boundary, without state reset."""

    timestamp = pd.Timestamp(arm.current_timestamp)
    if arm.status != "active":
        raise RuntimeError(f"Arm is not active: {arm.status}")
    if pd.Timestamp(current_events.timestamp) != timestamp:
        raise ValueError("Refresh events do not align with the arm clock")
    elapsed = _elapsed_minutes(arm)
    performed_offsets = [int(item["scheduled_offset_minutes"]) for item in arm.refresh_log]
    offsets = refresh_configuration.scheduled_offsets
    next_index = len(performed_offsets)
    if next_index >= len(offsets):
        return RefreshResult(False, timestamp, None, "no_remaining_refresh")
    expected = offsets[next_index]
    if elapsed < expected:
        return RefreshResult(False, timestamp, expected, "not_due")
    if elapsed > expected:
        reason = f"missed_parameter_refresh:{expected}_minutes"
        arm.status, arm.failure_reason = "failed_schedule", reason
        raise SchedulingError(reason)
    if any(pd.Timestamp(item["refresh_timestamp"]) == timestamp for item in arm.refresh_log):
        return RefreshResult(False, timestamp, expected, "already_refreshed")

    state_before = arm.physiological_state.detach().clone()
    history_before = arm.history.clone()
    old = arm.parameters.detach().clone()
    proposed = None
    try:
        inference = arm.history.gru_input(current_events)
        proposed = predict_parameters(frozen_gru, inference.unsqueeze(0))[0]
        valid, reason = _valid_parameters(proposed)
    except Exception as error:
        valid = False
        reason = f"parameter_inference_failed:{type(error).__name__}:{error}"

    if proposed is None or proposed.shape != old.shape:
        new_values = [None] * len(PARAMETER_NAMES)
        absolute = [None] * len(PARAMETER_NAMES)
        relative = [None] * len(PARAMETER_NAMES)
    else:
        new_values = [float(value) for value in proposed]
        absolute_tensor = torch.abs(proposed - old)
        relative_tensor = absolute_tensor / torch.clamp(torch.abs(old), min=1e-12)
        absolute = [float(value) for value in absolute_tensor]
        relative = [float(value) for value in relative_tensor]
    entry = {
        "refresh_timestamp": timestamp,
        "scheduled_offset_minutes": expected,
        "history_start_timestamp": history_before.completed_timestamps[0],
        "history_end_timestamp": history_before.current_timestamp,
        "old_parameters": {name: float(value) for name, value in zip(PARAMETER_NAMES, old)},
        "new_parameters": dict(zip(PARAMETER_NAMES, new_values)),
        "absolute_changes": dict(zip(PARAMETER_NAMES, absolute)),
        "relative_changes": dict(zip(PARAMETER_NAMES, relative)),
        "parameter_validation_passed": bool(valid),
        "validation_failure_reason": reason,
        "state_valid_before": bool(
            torch.isfinite(state_before).all().item()
            and (state_before >= 0).all().item()
            and state_before[0].item() > 0
        ),
        "state_preserved_exactly": bool(torch.equal(arm.physiological_state, state_before)),
        "history_preserved_exactly": _histories_equal(history_before, arm.history),
        "roundoff_corrections_before_refresh": int(arm.roundoff_corrections),
        "status": "refreshed" if valid else "failed",
    }
    if not valid:
        arm.status, arm.failure_reason = "failed_refresh", reason
        arm.refresh_log.append(entry)
        return RefreshResult(False, timestamp, expected, "failed", reason)

    arm.parameters = proposed.detach().clone()
    arm.parameter_estimation_timestamp = timestamp
    arm.gru_history = inference.detach().clone()
    entry["state_preserved_exactly"] = bool(torch.equal(arm.physiological_state, state_before))
    entry["history_preserved_exactly"] = _histories_equal(history_before, arm.history)
    arm.refresh_log.append(entry)
    return RefreshResult(True, timestamp, expected, "refreshed")
