"""Stateful ten-state Hovorka simulation for bolus candidate evaluation.

State order and units
---------------------
``Q1`` [mmol] accessible glucose mass; ``Q2`` [mmol] non-accessible glucose
mass; ``S1`` and ``S2`` [mU] subcutaneous insulin compartments; ``I`` [mU/L]
plasma insulin; ``X1`` [1/min] glucose-distribution action; ``X2`` [1/min]
glucose-disposal action; ``X3`` [dimensionless] EGP-suppression action; and
``D1`` and ``D2`` [mmol] gut carbohydrate compartments.

Parameter order is ``si1, si2, si3, tmax_i, tmax_g, egp0, f01``. Each input
interval is ``basal_rate_u_per_hour, bolus_u, consumed_carbs_g``. Announced
``carbs_g`` is deliberately absent: it remains a GRU/decision feature and is
never an additional physiological ingestion event.

Shape contract
--------------
Single items use state ``(10,)``, parameters ``(7,)`` and inputs ``(3,)``.
Batched items use ``(B, 10)``, ``(B, 7)`` and ``(B, 3)``. A single state or
parameter vector broadcasts across the batch. Forecast inputs are ``(T, 3)``
for one candidate or ``(B, T, 3)`` for multiple candidates. Single-candidate
results are squeezed back to ``(T,)`` glucose and ``(10,)`` final state.

Values in ``[-1e-7, 0)`` for nonnegative state compartments are explicitly
treated as floating-point roundoff and set to zero; correction counts are
reported. More negative values are candidate failures, never silently clipped.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import torch

from final_model_adapter import LOWER, UPPER


STATE_NAMES = ("Q1", "Q2", "S1", "S2", "I", "X1", "X2", "X3", "D1", "D2")
PARAMETER_NAMES = ("si1", "si2", "si3", "tmax_i", "tmax_g", "egp0", "f01")
PHYSIOLOGICAL_INPUT_NAMES = (
    "basal_rate_u_per_hour",
    "bolus_u",
    "consumed_carbs_g",
)

STATE_SIZE = len(STATE_NAMES)
PARAMETER_SIZE = len(PARAMETER_NAMES)
INPUT_SIZE = len(PHYSIOLOGICAL_INPUT_NAMES)
INTERVAL_MINUTES = 5.0
DEFAULT_SUBSTEPS = 5
NEGATIVE_ROUNDOFF_TOLERANCE = 1e-7
MG_DL_PER_MMOL_L = 18.01559

# Fixed constants preserved from optimize.py.
VG_L_PER_KG = 0.16
VI_L_PER_KG = 0.12
K12_PER_MIN = 0.066
KA1_PER_MIN = 0.006
KA2_PER_MIN = 0.06
KA3_PER_MIN = 0.03
KE_PER_MIN = 0.138
AG = 0.8
CARB_G_PER_MOL = 180.1559


@dataclass(frozen=True)
class CandidateFailure:
    """Candidate-local failure; indexes are zero-based, with -1 meaning pre-forecast."""

    candidate_index: int
    first_failing_interval: int
    first_failing_substep: int
    reason: str


@dataclass(frozen=True)
class ValidityInfo:
    valid_mask: torch.Tensor
    failures: tuple[CandidateFailure, ...]
    roundoff_corrections: tuple[int, ...]

    @property
    def all_valid(self) -> bool:
        return bool(self.valid_mask.all().item())


@dataclass(frozen=True)
class StateResult:
    state: torch.Tensor
    validity: ValidityInfo


@dataclass(frozen=True)
class PredictionResult:
    glucose_mg_dl: torch.Tensor
    final_state: torch.Tensor
    horizon_minutes: torch.Tensor
    validity: ValidityInfo
    state_trajectory: torch.Tensor | None = None


def physiological_inputs_from_frame(frame, *, dtype=torch.float32) -> torch.Tensor:
    """Extract simulator inputs; ``carbs_g`` is intentionally ignored."""

    missing = set(PHYSIOLOGICAL_INPUT_NAMES).difference(frame.columns)
    if missing:
        raise ValueError(f"Missing physiological input columns: {sorted(missing)}")
    values = frame.loc[:, PHYSIOLOGICAL_INPUT_NAMES].to_numpy(dtype=np.float32, copy=True)
    return torch.as_tensor(values, dtype=dtype)


def _tensor(value, name: str) -> torch.Tensor:
    if not isinstance(value, torch.Tensor):
        raise TypeError(f"{name} must be a torch.Tensor")
    if not value.dtype.is_floating_point:
        raise TypeError(f"{name} must have a floating-point dtype")
    return value


def _validate_settings(weight_kg: float, substeps: int) -> None:
    if not np.isfinite(weight_kg) or weight_kg <= 0:
        raise ValueError("weight_kg must be finite and positive")
    if isinstance(substeps, bool) or not isinstance(substeps, int) or substeps <= 0:
        raise ValueError("substeps must be a positive integer")


def _as_batch(tensor: torch.Tensor, width: int, name: str) -> tuple[torch.Tensor, bool]:
    tensor = _tensor(tensor, name)
    if tensor.ndim == 1 and tensor.shape[0] == width:
        return tensor.unsqueeze(0), True
    if tensor.ndim == 2 and tensor.shape[1] == width:
        return tensor, False
    raise ValueError(f"{name} must have shape ({width},) or (batch, {width}); got {tuple(tensor.shape)}")


def _broadcast_rows(tensor: torch.Tensor, batch: int, name: str) -> torch.Tensor:
    if tensor.shape[0] == batch:
        return tensor
    if tensor.shape[0] == 1:
        return tensor.expand(batch, -1)
    raise ValueError(f"{name} batch {tensor.shape[0]} cannot broadcast to batch {batch}")


def _parameter_reason(theta: torch.Tensor) -> str | None:
    if not torch.isfinite(theta).all():
        return "nonfinite_parameters"
    lower = torch.as_tensor(LOWER, dtype=theta.dtype, device=theta.device)
    upper = torch.as_tensor(UPPER, dtype=theta.dtype, device=theta.device)
    if bool(((theta < lower) | (theta > upper)).any().item()):
        return "parameters_outside_valid_bounds"
    return None


def _normalize_state(state: torch.Tensor) -> tuple[torch.Tensor | None, str | None, int]:
    if not torch.isfinite(state).all():
        return None, "nonfinite_state", 0
    too_negative = state < -NEGATIVE_ROUNDOFF_TOLERANCE
    if bool(too_negative.any().item()):
        names = [STATE_NAMES[index] for index in too_negative.nonzero().flatten().tolist()]
        return None, "negative_state_compartments:" + ",".join(names), 0
    tiny = (state < 0) & ~too_negative
    corrections = int(tiny.sum().item())
    normalized = torch.where(tiny, torch.zeros_like(state), state)
    if normalized[0].item() <= 0:
        return None, "invalid_glucose", corrections
    return normalized, None, corrections


def _input_reason(interval_inputs: torch.Tensor) -> str | None:
    if not torch.isfinite(interval_inputs).all():
        return "nonfinite_interval_inputs"
    if bool((interval_inputs < 0).any().item()):
        return "negative_interval_inputs"
    return None


def _derivatives(
    state: torch.Tensor,
    theta: torch.Tensor,
    basal_rate_u_per_hour: torch.Tensor,
    weight_kg: float,
) -> torch.Tensor:
    q1, q2, s1, s2, insulin, x1, x2, x3, d1, d2 = state.unbind(-1)
    si1, si2, si3, tmax_i, tmax_g, egp0, f01 = theta.unbind(-1)
    vg = VG_L_PER_KG * weight_kg
    vi = VI_L_PER_KG * weight_kg
    glucose_mmol_l = q1 / vg
    f01c = f01 * weight_kg * torch.minimum(
        glucose_mmol_l / 4.5, torch.ones_like(glucose_mmol_l)
    )
    renal = 0.003 * torch.relu(glucose_mmol_l - 9.0) * vg
    return torch.stack(
        (
            -f01c - x1 * q1 + K12_PER_MIN * q2 - renal + d2 / tmax_g
            + egp0 * weight_kg * (1 - x3),
            x1 * q1 - (K12_PER_MIN + x2) * q2,
            basal_rate_u_per_hour * 1000 / 60 - s1 / tmax_i,
            (s1 - s2) / tmax_i,
            s2 / (tmax_i * vi) - KE_PER_MIN * insulin,
            -KA1_PER_MIN * x1 + KA1_PER_MIN * si1 * insulin,
            -KA2_PER_MIN * x2 + KA2_PER_MIN * si2 * insulin,
            -KA3_PER_MIN * x3 + KA3_PER_MIN * si3 * insulin,
            -d1 / tmax_g,
            (d1 - d2) / tmax_g,
        ),
        dim=-1,
    )


def _advance_one(
    state: torch.Tensor,
    theta: torch.Tensor,
    interval_inputs: torch.Tensor,
    weight_kg: float,
    substeps: int,
    candidate_index: int,
    interval_index: int,
) -> tuple[torch.Tensor, CandidateFailure | None, int]:
    parameter_reason = _parameter_reason(theta)
    if parameter_reason is not None:
        return torch.full_like(state, torch.nan), CandidateFailure(
            candidate_index, interval_index, 0, parameter_reason
        ), 0
    normalized, state_reason, corrections = _normalize_state(state.clone())
    if state_reason is not None:
        return torch.full_like(state, torch.nan), CandidateFailure(
            candidate_index, interval_index, 0, state_reason
        ), corrections
    input_reason = _input_reason(interval_inputs)
    if input_reason is not None:
        return torch.full_like(state, torch.nan), CandidateFailure(
            candidate_index, interval_index, 0, input_reason
        ), corrections

    current = normalized.clone()
    basal, bolus, consumed_carbs = interval_inputs
    event = torch.zeros_like(current)
    event[2] = bolus * 1000
    event[8] = consumed_carbs * AG * (1000 / CARB_G_PER_MOL)
    current = current + event
    dt = INTERVAL_MINUTES / substeps
    for substep in range(1, substeps + 1):
        k1 = _derivatives(current, theta, basal, weight_kg)
        k2 = _derivatives(current + dt * k1 / 2, theta, basal, weight_kg)
        k3 = _derivatives(current + dt * k2 / 2, theta, basal, weight_kg)
        k4 = _derivatives(current + dt * k3, theta, basal, weight_kg)
        updated = current + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6
        if not all(torch.isfinite(item).all().item() for item in (k1, k2, k3, k4, updated)):
            return torch.full_like(state, torch.nan), CandidateFailure(
                candidate_index, interval_index, substep, "nonfinite_integration"
            ), corrections
        normalized, state_reason, added = _normalize_state(updated)
        corrections += added
        if state_reason is not None:
            return torch.full_like(state, torch.nan), CandidateFailure(
                candidate_index, interval_index, substep, state_reason
            ), corrections
        current = normalized
    return current, None, corrections


def _advance_batch_core(
    states: torch.Tensor,
    parameters: torch.Tensor,
    interval_inputs: torch.Tensor,
    weight_kg: float,
    substeps: int,
    candidate_indices: torch.Tensor,
    interval_index: int,
) -> tuple[torch.Tensor, torch.Tensor, list[CandidateFailure], torch.Tensor]:
    """Vectorized advancement with candidate-local validation and failures."""

    current = states.clone()
    batch = len(current)
    active = torch.ones(batch, dtype=torch.bool, device=current.device)
    corrections = torch.zeros(batch, dtype=torch.int64, device=current.device)
    failures: list[CandidateFailure] = []

    def fail(mask: torch.Tensor, substep: int, reason) -> None:
        nonlocal active, current
        newly_failed = active & mask
        for local_index in newly_failed.nonzero().flatten().tolist():
            description = reason(local_index) if callable(reason) else reason
            failures.append(
                CandidateFailure(
                    int(candidate_indices[local_index].item()),
                    interval_index,
                    substep,
                    description,
                )
            )
        active = active & ~newly_failed
        current[newly_failed] = torch.nan

    fail(~torch.isfinite(parameters).all(dim=1), 0, "nonfinite_parameters")
    lower = torch.as_tensor(LOWER, dtype=parameters.dtype, device=parameters.device)
    upper = torch.as_tensor(UPPER, dtype=parameters.dtype, device=parameters.device)
    fail(((parameters < lower) | (parameters > upper)).any(dim=1), 0,
         "parameters_outside_valid_bounds")
    fail(~torch.isfinite(current).all(dim=1), 0, "nonfinite_state")
    too_negative = current < -NEGATIVE_ROUNDOFF_TOLERANCE
    fail(
        too_negative.any(dim=1),
        0,
        lambda row: "negative_state_compartments:" + ",".join(
            STATE_NAMES[index] for index in too_negative[row].nonzero().flatten().tolist()
        ),
    )
    tiny = active[:, None] & (current < 0) & ~too_negative
    corrections += tiny.sum(dim=1)
    current = torch.where(tiny, torch.zeros_like(current), current)
    fail(current[:, 0] <= 0, 0, "invalid_glucose")
    fail(~torch.isfinite(interval_inputs).all(dim=1), 0, "nonfinite_interval_inputs")
    fail((interval_inputs < 0).any(dim=1), 0, "negative_interval_inputs")

    basal, bolus, consumed_carbs = interval_inputs.unbind(-1)
    event = torch.zeros_like(current)
    event[:, 2] = bolus * 1000
    event[:, 8] = consumed_carbs * AG * (1000 / CARB_G_PER_MOL)
    current = current + event
    current[~active] = torch.nan
    dt = INTERVAL_MINUTES / substeps
    for substep in range(1, substeps + 1):
        k1 = _derivatives(current, parameters, basal, weight_kg)
        k2 = _derivatives(current + dt * k1 / 2, parameters, basal, weight_kg)
        k3 = _derivatives(current + dt * k2 / 2, parameters, basal, weight_kg)
        k4 = _derivatives(current + dt * k3, parameters, basal, weight_kg)
        updated = current + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6
        finite = (
            torch.isfinite(k1).all(dim=1)
            & torch.isfinite(k2).all(dim=1)
            & torch.isfinite(k3).all(dim=1)
            & torch.isfinite(k4).all(dim=1)
            & torch.isfinite(updated).all(dim=1)
        )
        fail(~finite, substep, "nonfinite_integration")
        too_negative = updated < -NEGATIVE_ROUNDOFF_TOLERANCE
        fail(
            too_negative.any(dim=1),
            substep,
            lambda row: "negative_state_compartments:" + ",".join(
                STATE_NAMES[index] for index in too_negative[row].nonzero().flatten().tolist()
            ),
        )
        tiny = active[:, None] & (updated < 0) & ~too_negative
        corrections += tiny.sum(dim=1)
        updated = torch.where(tiny, torch.zeros_like(updated), updated)
        current = updated
        current[~active] = torch.nan
        fail(current[:, 0] <= 0, substep, "invalid_glucose")
    return current, active, failures, corrections


def advance_state(
    state: torch.Tensor,
    parameters: torch.Tensor,
    interval_inputs: torch.Tensor,
    weight_kg: float = 70.0,
    substeps: int = DEFAULT_SUBSTEPS,
) -> StateResult:
    """Advance exactly one five-minute interval without mutating arguments."""

    _validate_settings(weight_kg, substeps)
    states, state_single = _as_batch(state, STATE_SIZE, "state")
    params, _ = _as_batch(parameters, PARAMETER_SIZE, "parameters")
    inputs, _ = _as_batch(interval_inputs, INPUT_SIZE, "interval_inputs")
    batch = max(states.shape[0], params.shape[0], inputs.shape[0])
    states = _broadcast_rows(states, batch, "state")
    params = _broadcast_rows(params, batch, "parameters")
    inputs = _broadcast_rows(inputs, batch, "interval_inputs")
    if len({states.device, params.device, inputs.device}) != 1:
        raise ValueError("state, parameters and interval_inputs must use the same device")
    if len({states.dtype, params.dtype, inputs.dtype}) != 1:
        raise ValueError("state, parameters and interval_inputs must use the same dtype")

    output, valid, failures, corrections = _advance_batch_core(
        states, params, inputs, weight_kg, substeps,
        torch.arange(batch, device=states.device), 0,
    )
    validity = ValidityInfo(
        valid, tuple(failures), tuple(int(value) for value in corrections.tolist()),
    )
    return StateResult(output[0] if state_single and batch == 1 else output, validity)


def _history_batches(
    glucose_history: torch.Tensor,
    physiological_input_history: torch.Tensor,
    parameters: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, bool]:
    glucose = _tensor(glucose_history, "glucose_history")
    inputs = _tensor(physiological_input_history, "physiological_input_history")
    if glucose.ndim == 1 and glucose.shape[0] == 73:
        glucose, single = glucose.unsqueeze(0), True
    elif glucose.ndim == 2 and glucose.shape[1] == 73:
        single = False
    else:
        raise ValueError("glucose_history must have shape (73,) or (batch, 73)")
    if inputs.ndim == 2 and tuple(inputs.shape) == (72, INPUT_SIZE):
        inputs = inputs.unsqueeze(0)
    elif inputs.ndim != 3 or tuple(inputs.shape[1:]) != (72, INPUT_SIZE):
        raise ValueError("physiological_input_history must have shape (72, 3) or (batch, 72, 3)")
    params, _ = _as_batch(parameters, PARAMETER_SIZE, "parameters")
    batch = max(glucose.shape[0], inputs.shape[0], params.shape[0])
    if glucose.shape[0] not in (1, batch) or inputs.shape[0] not in (1, batch):
        raise ValueError("history batches cannot be broadcast together")
    glucose = glucose.expand(batch, -1) if glucose.shape[0] == 1 else glucose
    inputs = inputs.expand(batch, -1, -1) if inputs.shape[0] == 1 else inputs
    params = _broadcast_rows(params, batch, "parameters")
    if len({glucose.device, inputs.device, params.device}) != 1:
        raise ValueError("histories and parameters must use the same device")
    if len({glucose.dtype, inputs.dtype, params.dtype}) != 1:
        raise ValueError("histories and parameters must use the same dtype")
    return glucose, inputs, params, single and batch == 1


def initialize_state(
    glucose_history: torch.Tensor,
    physiological_input_history: torch.Tensor,
    parameters: torch.Tensor,
    weight_kg: float = 70.0,
    substeps: int = DEFAULT_SUBSTEPS,
) -> StateResult:
    """Initialize at a decision boundary from 73 CGMs and 72 prior intervals.

    The first state assumes empty gut compartments and insulin equilibrium with
    the first historical basal rate. Seventy-two intervals are replayed, using
    consumed carbohydrate, and Q1 is corrected to each next CGM boundary while
    every other state carries forward. The returned state is before any new
    decision-time interval input is applied.
    """

    _validate_settings(weight_kg, substeps)
    glucose, inputs, params, single = _history_batches(
        glucose_history, physiological_input_history, parameters
    )
    batch = glucose.shape[0]
    states = torch.full((batch, STATE_SIZE), torch.nan, dtype=glucose.dtype, device=glucose.device)
    valid = [True] * batch
    failures: list[CandidateFailure] = []
    corrections = [0] * batch
    vg = VG_L_PER_KG * weight_kg
    vi = VI_L_PER_KG * weight_kg

    for candidate in range(batch):
        theta = params[candidate]
        reason = _parameter_reason(theta)
        if reason is None and not torch.isfinite(glucose[candidate]).all():
            reason = "nonfinite_glucose_history"
        if reason is None and bool((glucose[candidate] <= 0).any().item()):
            reason = "invalid_glucose_history"
        if reason is None and _input_reason(inputs[candidate]) is not None:
            reason = _input_reason(inputs[candidate])
        if reason is not None:
            valid[candidate] = False
            failures.append(CandidateFailure(candidate, -1, -1, reason))
            continue
        si1, si2, si3, tmax_i, _, _, _ = theta
        basal_m_u_min = inputs[candidate, 0, 0] * 1000 / 60
        insulin = basal_m_u_min / (KE_PER_MIN * vi)
        x1, x2, x3 = si1 * insulin, si2 * insulin, si3 * insulin
        q1 = glucose[candidate, 0] / MG_DL_PER_MMOL_L * vg
        zero = torch.zeros_like(q1)
        state = torch.stack(
            (
                q1,
                x1 * q1 / (K12_PER_MIN + x2),
                basal_m_u_min * tmax_i,
                basal_m_u_min * tmax_i,
                insulin,
                x1,
                x2,
                x3,
                zero,
                zero,
            )
        )
        states[candidate] = state

    active = torch.tensor(valid, dtype=torch.bool, device=states.device)
    for interval in range(72):
        indexes = active.nonzero().flatten()
        if not len(indexes):
            break
        updated, local_valid, local_failures, local_corrections = _advance_batch_core(
            states[indexes], params[indexes], inputs[indexes, interval], weight_kg,
            substeps, indexes, interval,
        )
        states[indexes] = updated
        for local, global_index in enumerate(indexes.tolist()):
            corrections[global_index] += int(local_corrections[local].item())
        failures.extend(local_failures)
        failed_global = indexes[~local_valid]
        active[failed_global] = False
        surviving = indexes[local_valid]
        if len(surviving):
            states[surviving, 0] = (
                glucose[surviving, interval + 1] / MG_DL_PER_MMOL_L * vg
            )

    valid = active.tolist()

    validity = ValidityInfo(
        torch.tensor(valid, dtype=torch.bool, device=states.device),
        tuple(failures), tuple(corrections),
    )
    return StateResult(states[0] if single else states, validity)


def predict_from_state(
    initial_state: torch.Tensor,
    parameters: torch.Tensor,
    future_inputs: torch.Tensor,
    weight_kg: float = 70.0,
    substeps: int = DEFAULT_SUBSTEPS,
    *,
    return_state_trajectory: bool = False,
) -> PredictionResult:
    """Simulate supplied candidate inputs with no future-CGM correction.

    ``future_inputs`` may have any positive sequence length; the optimization
    horizon is 48 rows. Parameters remain fixed throughout the call. A failed
    candidate receives NaN predictions/state from its first failure onward,
    while unrelated candidates continue.
    """

    _validate_settings(weight_kg, substeps)
    states, state_single = _as_batch(initial_state, STATE_SIZE, "initial_state")
    params, _ = _as_batch(parameters, PARAMETER_SIZE, "parameters")
    inputs = _tensor(future_inputs, "future_inputs")
    if inputs.ndim == 2 and inputs.shape[1] == INPUT_SIZE:
        inputs, input_single = inputs.unsqueeze(0), True
    elif inputs.ndim == 3 and inputs.shape[2] == INPUT_SIZE:
        input_single = False
    else:
        raise ValueError("future_inputs must have shape (intervals, 3) or (batch, intervals, 3)")
    if inputs.shape[1] <= 0:
        raise ValueError("future_inputs must contain at least one interval")
    batch = max(states.shape[0], params.shape[0], inputs.shape[0])
    states = _broadcast_rows(states, batch, "initial_state").clone()
    params = _broadcast_rows(params, batch, "parameters")
    if inputs.shape[0] == 1:
        inputs = inputs.expand(batch, -1, -1)
    elif inputs.shape[0] != batch:
        raise ValueError(f"future_inputs batch {inputs.shape[0]} cannot broadcast to batch {batch}")
    if len({states.device, params.device, inputs.device}) != 1:
        raise ValueError("initial_state, parameters and future_inputs must use the same device")
    if len({states.dtype, params.dtype, inputs.dtype}) != 1:
        raise ValueError("initial_state, parameters and future_inputs must use the same dtype")

    intervals = inputs.shape[1]
    glucose = torch.full((batch, intervals), torch.nan, dtype=states.dtype, device=states.device)
    trajectory = (
        torch.full((batch, intervals, STATE_SIZE), torch.nan, dtype=states.dtype, device=states.device)
        if return_state_trajectory else None
    )
    active = torch.ones(batch, dtype=torch.bool, device=states.device)
    failures: list[CandidateFailure] = []
    corrections = [0] * batch

    # Candidate-level state/parameter failures precede interval zero.
    for candidate in range(batch):
        reason = _parameter_reason(params[candidate])
        normalized, state_reason, corrected = _normalize_state(states[candidate])
        corrections[candidate] += corrected
        reason = reason or state_reason
        if reason is not None:
            active[candidate] = False
            states[candidate] = torch.nan
            failures.append(CandidateFailure(candidate, -1, -1, reason))
        else:
            states[candidate] = normalized

    for interval in range(intervals):
        indexes = active.nonzero().flatten()
        if not len(indexes):
            break
        updated, local_valid, local_failures, local_corrections = _advance_batch_core(
            states[indexes], params[indexes], inputs[indexes, interval], weight_kg,
            substeps, indexes, interval,
        )
        states[indexes] = updated
        for local, global_index in enumerate(indexes.tolist()):
            corrections[global_index] += int(local_corrections[local].item())
        failures.extend(local_failures)
        failed_global = indexes[~local_valid]
        active[failed_global] = False
        surviving = indexes[local_valid]
        if len(surviving):
            glucose[surviving, interval] = (
                states[surviving, 0] / (VG_L_PER_KG * weight_kg) * MG_DL_PER_MMOL_L
            )
            if trajectory is not None:
                trajectory[surviving, interval] = states[surviving]

    validity = ValidityInfo(active.clone(), tuple(failures), tuple(corrections))
    horizons = torch.arange(
        1, intervals + 1, device=states.device, dtype=torch.int64
    ) * int(INTERVAL_MINUTES)
    single = state_single and input_single and batch == 1
    return PredictionResult(
        glucose[0] if single else glucose,
        states[0] if single else states,
        horizons,
        validity,
        trajectory[0] if single and trajectory is not None else trajectory,
    )
