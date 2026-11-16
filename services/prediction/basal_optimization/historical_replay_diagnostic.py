"""Compare continuous and independently reinitialized historical basal replays.

This is a development-only retrospective diagnostic. Short-window outputs are
aligned predictions from independent historical replays, not a continuous
counterfactual trajectory, and never authorize basal selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd
import torch

from bolus_optimization.checkpoint import load_frozen_gru, predict_parameters
from bolus_optimization.configuration import FROZEN_CHECKPOINT_SHA256, MODEL_FEATURES
from bolus_optimization.physiology import (
    DEFAULT_SUBSTEPS, PARAMETER_NAMES, initialize_state,
    physiological_inputs_from_frame, predict_from_state,
)
from .preparation import (
    DEFAULT_CHECKPOINT_PATH, DEFAULT_DATASET_PATH, EFFECTIVE_WEIGHT_KG, INTERVAL,
    PHYSIOLOGICAL_INITIALIZATION_INTERVALS, REPOSITORY_ROOT, BasalPreparationError,
    PatientIdentity, PreparedBasalSnapshot, _resolve_repository_path,
    prepare_basal_snapshot,
)
from .reliability import calculate_glucose_fit_metrics


DECISION_TIMESTAMP = pd.Timestamp("2027-01-04 00:00:00")
EVALUATION_STEPS = 576
HISTORY_STEPS = 288
HORIZON_HOURS = (2, 4, 6)
TARGET_PATIENTS = (
    PatientIdentity("PadovaBaseline", "adolescent#001"),
    PatientIdentity("PadovaBaseline", "adolescent#002"),
    PatientIdentity("PadovaBaseline", "adolescent#004"),
    PatientIdentity("PadovaBaseline", "adolescent#005"),
    PatientIdentity("PadovaBaseline", "adult#004"),
)
CONTINUITY_COLUMNS = ("source_run_id", "source_record_id", "continuous_record_id")
TIE_TOLERANCE_MG_DL = 1e-6
METRIC_FIELDS = ("mae_mg_dl", "rmse_mg_dl", "mean_signed_error_mg_dl",
                 "maximum_absolute_error_mg_dl")
DEFAULT_RESULTS_DIRECTORY = (
    REPOSITORY_ROOT / "services/prediction/results/basal_historical_replay_diagnostic"
)


@dataclass(frozen=True)
class SegmentPlan:
    horizon_hours: int
    steps_per_segment: int
    origins: tuple[pd.Timestamp, ...]


@dataclass(frozen=True)
class SegmentInputs:
    identity: PatientIdentity
    origin: pd.Timestamp
    horizon_hours: int
    gru_input: torch.Tensor
    initialization_glucose: torch.Tensor
    initialization_inputs: torch.Tensor
    forecast_inputs: torch.Tensor
    targets: torch.Tensor
    input_timestamps: tuple[pd.Timestamp, ...]
    output_timestamps: tuple[pd.Timestamp, ...]


def timestamp_index_equal(left: Iterable[object], right: Iterable[object]) -> bool:
    """Compare exact values after precision upcasting while retaining timezone."""
    try:
        return pd.DatetimeIndex(left).as_unit("ns").equals(
            pd.DatetimeIndex(right).as_unit("ns"))
    except (TypeError, ValueError, OverflowError):
        return False


def build_segment_plan(start: pd.Timestamp, horizon_hours: int) -> SegmentPlan:
    if horizon_hours not in HORIZON_HOURS:
        raise ValueError(f"horizon_hours must be one of {HORIZON_HOURS}")
    steps = horizon_hours * 12
    origins = tuple(start + index * INTERVAL
                    for index in range(0, EVALUATION_STEPS, steps))
    return SegmentPlan(horizon_hours, steps, origins)


def _patient_rows(data: pd.DataFrame, identity: PatientIdentity) -> pd.DataFrame:
    rows = data.loc[
        data["dataset"].astype(str).eq(identity.dataset)
        & data["patient_id"].astype(str).eq(identity.patient_id)
    ].copy(deep=True)
    if rows.empty:
        raise ValueError(f"patient not found: {identity.dataset}/{identity.patient_id}")
    rows["timestamp"] = pd.to_datetime(rows["timestamp"], errors="raise")
    return rows.sort_values("timestamp", kind="stable").reset_index(drop=True)


def _validate_rows(rows: pd.DataFrame, expected: pd.DatetimeIndex, label: str) -> None:
    if len(rows) != len(expected) or not timestamp_index_equal(rows["timestamp"], expected):
        raise ValueError(f"{label} requires {len(expected)} exact five-minute rows; found {len(rows)}")
    columns = ("cgm_mg_dl", "basal_rate_u_per_hour", "bolus_u", "carbs_g",
               "consumed_carbs_g")
    values64 = rows.loc[:, columns].apply(pd.to_numeric, errors="coerce").to_numpy(np.float64)
    if not np.isfinite(values64).all() or (values64 < 0).any():
        raise ValueError(f"{label} contains missing, nonfinite, or negative values")
    with np.errstate(over="ignore", invalid="ignore"):
        values32 = values64.astype(np.float32)
    if not np.isfinite(values32).all():
        raise ValueError(f"{label} contains values nonfinite after float32 conversion")
    if (values64[:, 0] <= 0).any():
        raise ValueError(f"{label} contains nonpositive CGM")
    for column in CONTINUITY_COLUMNS:
        if column in rows and (rows[column].isna().any()
                               or rows[column].nunique(dropna=False) != 1):
            raise ValueError(f"{label} crosses or misses {column}")


def assemble_segment_inputs(data: pd.DataFrame, identity: PatientIdentity,
                            origin: pd.Timestamp, horizon_hours: int) -> SegmentInputs:
    """Use history through O only; forecast inputs start at O and outcomes at O+5m."""
    rows = _patient_rows(data, identity)
    steps = horizon_hours * 12
    history_start = origin - HISTORY_STEPS * INTERVAL
    end = origin + steps * INTERVAL
    required = rows.loc[rows["timestamp"].ge(history_start)
                        & rows["timestamp"].le(end)].copy(deep=True)
    expected = pd.date_range(history_start, periods=HISTORY_STEPS + steps + 1,
                             freq=INTERVAL)
    _validate_rows(required, expected, "segment history/boundary/forecast")
    history = required.iloc[:HISTORY_STEPS]
    boundary = required.iloc[HISTORY_STEPS]
    forecast = required.iloc[HISTORY_STEPS:HISTORY_STEPS + steps]
    outcomes = required.iloc[HISTORY_STEPS + 1:]
    boundary_features = np.asarray([[
        boundary["cgm_mg_dl"], boundary["basal_rate_u_per_hour"], 0.0,
        boundary["carbs_g"],
    ]], np.float32)
    gru = torch.from_numpy(np.concatenate((
        history.loc[:, MODEL_FEATURES].to_numpy(np.float32, copy=True),
        boundary_features,
    )))
    init = history.iloc[-PHYSIOLOGICAL_INITIALIZATION_INTERVALS:]
    init_glucose = torch.from_numpy(np.concatenate((
        init["cgm_mg_dl"].to_numpy(np.float32, copy=True),
        np.asarray([boundary["cgm_mg_dl"]], np.float32),
    )))
    tensors = (gru, init_glucose, physiological_inputs_from_frame(init),
               physiological_inputs_from_frame(forecast))
    if not all(torch.isfinite(tensor).all().item() for tensor in tensors):
        raise ValueError("segment contains nonfinite float32 tensors")
    outputs = tuple(pd.Timestamp(value) for value in outcomes["timestamp"])
    if not timestamp_index_equal(outputs, pd.date_range(origin + INTERVAL,
                                                         periods=steps, freq=INTERVAL)):
        raise ValueError("segment output alignment is not O+5 minutes through O+H")
    return SegmentInputs(identity, origin, horizon_hours, tensors[0], tensors[1],
                         tensors[2], tensors[3],
                         torch.from_numpy(outcomes["cgm_mg_dl"].to_numpy(np.float32, copy=True)),
                         tuple(pd.Timestamp(value) for value in forecast["timestamp"]), outputs)


def estimate_parameters(segment: SegmentInputs,
                        estimator: Callable[[torch.Tensor], torch.Tensor]) -> torch.Tensor:
    with torch.inference_mode():
        result = estimator(segment.gru_input.unsqueeze(0))
    parameters = result[0] if tuple(result.shape) == (1, 7) else result
    if tuple(parameters.shape) != (7,):
        raise ValueError(f"parameter estimator returned {tuple(parameters.shape)}")
    parameters = parameters.to(torch.float32).detach().clone()
    if not torch.isfinite(parameters).all().item():
        raise ValueError("parameter estimator returned nonfinite values")
    return parameters


def metric_values(predicted: Iterable[float], observed: Iterable[float]) -> dict[str, Any]:
    prediction = np.asarray(list(predicted), np.float64)
    target = np.asarray(list(observed), np.float64)
    metric = calculate_glucose_fit_metrics(prediction, target)
    return {**asdict(metric), "endpoint_error_mg_dl": float(prediction[-1] - target[-1])}


def simulate_segment(segment: SegmentInputs, parameters: torch.Tensor,
                     initial_state: torch.Tensor | None = None, *,
                     return_state_trajectory: bool = False) -> tuple[dict[str, Any], torch.Tensor | None]:
    started = time.perf_counter()
    if initial_state is None:
        initialized = initialize_state(segment.initialization_glucose,
                                       segment.initialization_inputs, parameters,
                                       weight_kg=EFFECTIVE_WEIGHT_KG,
                                       substeps=DEFAULT_SUBSTEPS)
        if initialized.validity.failures:
            return ({"status": "initialization_failed",
                     "failure": asdict(initialized.validity.failures[0]),
                     "runtime_seconds": time.perf_counter() - started,
                     "coverage": {"expected": len(segment.targets), "matched": 0},
                     "metrics": None, "predictions": None}, initialized.state.detach().clone())
        state = initialized.state
    else:
        state = initial_state.detach().clone()
    result = predict_from_state(state, parameters, segment.forecast_inputs,
                                weight_kg=EFFECTIVE_WEIGHT_KG,
                                substeps=DEFAULT_SUBSTEPS,
                                return_state_trajectory=return_state_trajectory)
    prediction = result.glucose_mg_dl.detach().cpu().numpy().astype(np.float64)
    if not result.validity.all_valid or not np.isfinite(prediction).all():
        failure = result.validity.failures[0] if result.validity.failures else None
        return ({"status": "forecast_failed",
                 "failure": None if failure is None else asdict(failure),
                 "runtime_seconds": time.perf_counter() - started,
                 "coverage": {"expected": len(segment.targets),
                              "matched": int(np.isfinite(prediction).sum())},
                 "metrics": None, "predictions": prediction.tolist()}, state.detach().clone())
    observed = segment.targets.detach().cpu().numpy().astype(np.float64)
    return ({"status": "complete", "failure": None,
             "runtime_seconds": time.perf_counter() - started,
             "coverage": {"expected": len(observed), "matched": len(observed)},
             "metrics": metric_values(prediction, observed),
             "predictions": prediction.tolist(),
             "_state_trajectory": (
                 None if result.state_trajectory is None
                 else result.state_trajectory.detach().clone()
             )}, state.detach().clone())


def complete_protocol(segments: list[dict[str, Any]],
                      expected_outputs: pd.DatetimeIndex) -> dict[str, Any]:
    timestamps = [pd.Timestamp(value) for item in segments
                  for value in item["output_timestamps"]]
    predictions = [value for item in segments for value in (item["predictions"] or [])]
    observed = [value for item in segments for value in item["observed"]]
    keys = [(str(value.tz), value.as_unit("ns").value) for value in timestamps]
    exact = (len(timestamps) == EVALUATION_STEPS
             and len(set(keys)) == EVALUATION_STEPS
             and timestamp_index_equal(timestamps, expected_outputs))
    complete = exact and all(item["status"] == "complete" for item in segments)
    full = day0 = day1 = None
    if complete and len(predictions) == EVALUATION_STEPS:
        full = metric_values(predictions, observed)
        day0 = metric_values(predictions[:288], observed[:288])
        day1 = metric_values(predictions[288:], observed[288:])
    return {
        "status": "complete" if full is not None else "incomplete",
        "coverage": {"expected": EVALUATION_STEPS, "matched": len(predictions),
                     "missing": EVALUATION_STEPS - len(predictions),
                     "timestamps_exact_unique": exact},
        "full_metrics": full, "day0_metrics": day0, "day1_metrics": day1,
        "runtime_seconds": float(sum(item["runtime_seconds"] for item in segments)),
        "segments": segments, "output_timestamps": timestamps,
        "predictions": predictions, "observed": observed,
    }


def paired_difference(left: dict[str, Any], right: dict[str, Any]) -> dict[str, float] | None:
    """Compare only complete protocols already validated on the same 576 timestamps."""
    if left.get("full_metrics") is None or right.get("full_metrics") is None:
        return None
    if not timestamp_index_equal(left["output_timestamps"], right["output_timestamps"]):
        raise ValueError("paired comparison timestamps differ")
    return {field: float(left["full_metrics"][field] - right["full_metrics"][field])
            for field in METRIC_FIELDS}


def _segment_record(segment: SegmentInputs, result: dict[str, Any],
                    parameters: torch.Tensor, state: torch.Tensor | None,
                    correction: dict[str, float | None],
                    parameter_change: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        **result, "origin": segment.origin, "horizon_hours": segment.horizon_hours,
        "input_timestamps": segment.input_timestamps,
        "output_timestamps": segment.output_timestamps,
        "observed": segment.targets.detach().cpu().tolist(),
        "parameters": parameters.detach().cpu().tolist(),
        "initialized_state": None if state is None else state.detach().cpu().tolist(),
        "state_glucose_correction": correction,
        "parameter_change_from_A": parameter_change,
    }


def evaluate_patient(data: pd.DataFrame, snapshot: PreparedBasalSnapshot,
                     estimator: Callable[[torch.Tensor], torch.Tensor]) -> dict[str, Any]:
    identity, start = snapshot.identity, snapshot.simulation_start
    expected_outputs = pd.date_range(start + INTERVAL, periods=576, freq=INTERVAL)
    rows = _patient_rows(data, identity)
    inputs = rows.loc[rows["timestamp"].ge(start)
                      & rows["timestamp"].lt(snapshot.decision_timestamp)].copy()
    targets = rows.loc[rows["timestamp"].gt(start)
                       & rows["timestamp"].le(snapshot.decision_timestamp)].copy()
    _validate_rows(inputs, pd.date_range(start, periods=576, freq=INTERVAL),
                   "Protocol A inputs")
    _validate_rows(targets, expected_outputs, "Protocol A targets")
    a_input = SegmentInputs(
        identity, start, 48, snapshot.gru_input,
        snapshot.physiological_initialization_glucose,
        snapshot.physiological_initialization_inputs,
        physiological_inputs_from_frame(inputs),
        torch.from_numpy(targets["cgm_mg_dl"].to_numpy(np.float32, copy=True)),
        tuple(pd.Timestamp(value) for value in inputs["timestamp"]),
        tuple(pd.Timestamp(value) for value in targets["timestamp"]),
    )
    a_result, a_state = simulate_segment(
        a_input, snapshot.parameters, snapshot.physiological_state,
        return_state_trajectory=True,
    )
    a_state_trajectory = a_result.pop("_state_trajectory", None)
    zero_correction = {
        "observed_origin_glucose_mg_dl": float(snapshot.boundary_row["cgm_mg_dl"]),
        "continuous_A_glucose_at_origin_mg_dl": float(snapshot.boundary_row["cgm_mg_dl"]),
        "observed_minus_continuous_A_mg_dl": 0.0,
    }
    protocol_a = complete_protocol([
        _segment_record(a_input, a_result, snapshot.parameters, a_state, zero_correction)
    ], expected_outputs)
    protocols: dict[str, Any] = {"A": protocol_a}
    comparisons: dict[str, Any] = {}
    for horizon in HORIZON_HOURS:
        b_segments: list[dict[str, Any]] = []
        c_segments: list[dict[str, Any]] = []
        for index, origin in enumerate(build_segment_plan(start, horizon).origins):
            segment = assemble_segment_inputs(data, identity, origin, horizon)
            if index == 0:
                b_parameters = c_parameters = snapshot.parameters.detach().clone()
                b_result, b_state = simulate_segment(segment, b_parameters,
                                                     snapshot.physiological_state)
                c_result, c_state = simulate_segment(segment, c_parameters,
                                                     snapshot.physiological_state)
            else:
                b_parameters = snapshot.parameters.detach().clone()
                parameter_started = time.perf_counter()
                c_parameters = estimate_parameters(segment, estimator)
                parameter_runtime = time.perf_counter() - parameter_started
                b_result, b_state = simulate_segment(segment, b_parameters)
                c_result, c_state = simulate_segment(segment, c_parameters)
                c_result["runtime_seconds"] += parameter_runtime
            a_index = int((origin - start) / INTERVAL)
            a_at_origin = (float(snapshot.boundary_row["cgm_mg_dl"])
                           if a_index == 0 else
                           (protocol_a["predictions"][a_index - 1]
                            if len(protocol_a["predictions"]) == 576 else None))
            observed_origin = float(segment.initialization_glucose[-1].item())
            carried_a_state = (
                snapshot.physiological_state if a_index == 0
                else (None if a_state_trajectory is None else a_state_trajectory[a_index - 1])
            )
            def correction_for(initialized_state: torch.Tensor | None) -> dict[str, float | None]:
                state_delta = None
                if carried_a_state is not None and initialized_state is not None:
                    state_delta = (initialized_state - carried_a_state).detach().cpu().numpy().astype(np.float64)
                return {
                "observed_origin_glucose_mg_dl": observed_origin,
                "continuous_A_glucose_at_origin_mg_dl": a_at_origin,
                "observed_minus_continuous_A_mg_dl": (
                    None if a_at_origin is None else observed_origin - a_at_origin),
                    "initialized_state_minus_continuous_A_l2": (
                        None if state_delta is None else float(np.linalg.norm(state_delta))),
                    "initialized_state_minus_continuous_A_maximum_absolute": (
                        None if state_delta is None else float(np.abs(state_delta).max())),
                }
            b_segments.append(_segment_record(segment, b_result, b_parameters,
                                              b_state, correction_for(b_state)))
            delta = (c_parameters - snapshot.parameters).detach().cpu().numpy().astype(np.float64)
            change = {
                "l2_norm": float(np.linalg.norm(delta)),
                "maximum_absolute_component_change": float(np.abs(delta).max()),
                "components": dict(zip(PARAMETER_NAMES, delta.tolist())),
                "history_latest_timestamp": origin,
                "future_rows_used": 0,
            }
            c_segments.append(_segment_record(segment, c_result, c_parameters,
                                              c_state, correction_for(c_state), change))
        b = complete_protocol(b_segments, expected_outputs)
        c = complete_protocol(c_segments, expected_outputs)
        protocols[f"B_{horizon}h"], protocols[f"C_{horizon}h"] = b, c
        comparisons[f"{horizon}h"] = {
            "B_minus_A": paired_difference(b, protocol_a),
            "C_minus_A": paired_difference(c, protocol_a),
            "C_minus_B": paired_difference(c, b),
            "day1_mae_differences": {
                "B_minus_A": None if b["day1_metrics"] is None or protocol_a["day1_metrics"] is None
                else b["day1_metrics"]["mae_mg_dl"] - protocol_a["day1_metrics"]["mae_mg_dl"],
                "C_minus_A": None if c["day1_metrics"] is None or protocol_a["day1_metrics"] is None
                else c["day1_metrics"]["mae_mg_dl"] - protocol_a["day1_metrics"]["mae_mg_dl"],
            },
        }
    return {"identity": asdict(identity), "decision_timestamp": snapshot.decision_timestamp,
            "evaluation_start": start, "protocols": protocols,
            "comparisons": comparisons}


def _distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "median": None,
                "minimum": None, "maximum": None}
    array = np.asarray(values, np.float64)
    return {"count": len(values), "mean": float(array.mean()),
            "median": float(np.median(array)), "minimum": float(array.min()),
            "maximum": float(array.max())}


def aggregate_results(patients: list[dict[str, Any]]) -> dict[str, Any]:
    names = ("A", *(f"{arm}_{h}h" for h in HORIZON_HOURS for arm in ("B", "C")))
    protocols: dict[str, Any] = {}
    for name in names:
        complete = [p["protocols"][name] for p in patients
                    if p["protocols"][name]["full_metrics"] is not None]
        protocols[name] = {
            "complete_patient_count": len(complete),
            "failure_or_incomplete_count": len(patients) - len(complete),
            "patient_equal_metrics": {
                field: _distribution([item["full_metrics"][field] for item in complete])
                for field in METRIC_FIELDS},
            "patient_equal_day0_metrics": {
                field: _distribution([item["day0_metrics"][field] for item in complete])
                for field in METRIC_FIELDS},
            "patient_equal_day1_metrics": {
                field: _distribution([item["day1_metrics"][field] for item in complete])
                for field in METRIC_FIELDS},
            "runtime_seconds": float(sum(p["protocols"][name]["runtime_seconds"]
                                         for p in patients)),
        }
        segments = [segment for patient in patients
                    for segment in patient["protocols"][name]["segments"]]
        corrections = [abs(segment["state_glucose_correction"]["observed_minus_continuous_A_mg_dl"])
                       for segment in segments
                       if segment["state_glucose_correction"]["observed_minus_continuous_A_mg_dl"] is not None]
        parameter_changes = [segment["parameter_change_from_A"]["l2_norm"]
                             for segment in segments
                             if segment["parameter_change_from_A"] is not None]
        protocols[name]["absolute_state_glucose_correction_mg_dl"] = _distribution(corrections)
        state_corrections = [segment["state_glucose_correction"].get(
            "initialized_state_minus_continuous_A_l2") for segment in segments]
        protocols[name]["initialized_state_correction_l2"] = _distribution(
            [value for value in state_corrections if value is not None]
        )
        protocols[name]["parameter_change_l2"] = _distribution(parameter_changes)
    comparisons: dict[str, Any] = {}
    for horizon in HORIZON_HOURS:
        comparisons[f"{horizon}h"] = {}
        for label in ("B_minus_A", "C_minus_A", "C_minus_B"):
            available = [p["comparisons"][f"{horizon}h"][label] for p in patients
                         if p["comparisons"][f"{horizon}h"][label] is not None]
            mae = [item["mae_mg_dl"] for item in available]
            comparisons[f"{horizon}h"][label] = {
                "patient_equal_metrics": {
                    field: _distribution([item[field] for item in available])
                    for field in METRIC_FIELDS},
                "mae_win_tie_loss": {
                    "left_better": sum(value < -TIE_TOLERANCE_MG_DL for value in mae),
                    "tie": sum(abs(value) <= TIE_TOLERANCE_MG_DL for value in mae),
                    "right_better": sum(value > TIE_TOLERANCE_MG_DL for value in mae),
                    "tolerance_mg_dl": TIE_TOLERANCE_MG_DL,
                },
            }
            day1_values = []
            for patient in patients:
                left_name, right_name = {
                    "B_minus_A": (f"B_{horizon}h", "A"),
                    "C_minus_A": (f"C_{horizon}h", "A"),
                    "C_minus_B": (f"C_{horizon}h", f"B_{horizon}h"),
                }[label]
                left = patient["protocols"][left_name]["day1_metrics"]
                right = patient["protocols"][right_name]["day1_metrics"]
                if left is not None and right is not None:
                    day1_values.append(left["mae_mg_dl"] - right["mae_mg_dl"])
            comparisons[f"{horizon}h"][label]["day1_mae_difference"] = _distribution(day1_values)
            comparisons[f"{horizon}h"][label]["day1_mae_win_tie_loss"] = {
                "left_better": sum(value < -TIE_TOLERANCE_MG_DL for value in day1_values),
                "tie": sum(abs(value) <= TIE_TOLERANCE_MG_DL for value in day1_values),
                "right_better": sum(value > TIE_TOLERANCE_MG_DL for value in day1_values),
            }
    return {"protocols": protocols, "comparisons": comparisons}


def _json_default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _fingerprint(frame: pd.DataFrame) -> str:
    values = pd.util.hash_pandas_object(frame, index=True).values.tobytes()
    return hashlib.sha256(values).hexdigest()


def _model_unchanged(model: torch.nn.Module,
                     before: dict[str, torch.Tensor]) -> bool:
    after = model.state_dict()
    return (after.keys() == before.keys()
            and all(torch.equal(after[key], value) for key, value in before.items()))


def _plot_patient(patient: dict[str, Any], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(3, 1, figsize=(13, 11), sharex=True)
    for axis, horizon in zip(axes, HORIZON_HOURS):
        a, b, c = (patient["protocols"][name]
                   for name in ("A", f"B_{horizon}h", f"C_{horizon}h"))
        timestamps = pd.DatetimeIndex(a["output_timestamps"])
        axis.plot(timestamps, a["observed"], label="Recorded CGM", color="black")
        for label, protocol in (("A continuous", a),
                                (f"B {horizon}h independent", b),
                                (f"C {horizon}h independent", c)):
            if len(protocol["predictions"]) == 576:
                axis.plot(timestamps, protocol["predictions"], label=label, alpha=.8)
        for origin in build_segment_plan(pd.Timestamp(patient["evaluation_start"]), horizon).origins[1:]:
            axis.axvline(origin, color="grey", linewidth=.5, alpha=.35)
        axis.set_ylabel("CGM mg/dL")
        axis.set_title(f"{horizon}h aligned predictions from independent historical replays")
        axis.legend(ncol=4, fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def markdown_report(payload: dict[str, Any]) -> str:
    patients, failures = payload.get("patients", []), payload.get("failures", [])
    aggregate = payload.get("aggregate", {})
    lines = ["# Historical replay-length diagnostic", "",
             "Development-only retrospective diagnostic. Selection authorization is false.", "",
             "Short outputs are aligned predictions from independent historical replays, not continuous physiological trajectories.", "",
             "## Coverage", "",
             f"- Requested patients: {len(payload.get('configuration', {}).get('patients', []))}",
             f"- Completed patient evaluations: {len(patients)}",
             f"- Preparation/execution failures: {len(failures)}", ""]
    if failures:
        lines.extend(["## Failures", "", *(f"- {item}" for item in failures), ""])
    if not patients:
        lines.extend(["No patient evaluation completed; all metrics are unavailable.", ""])
        return "\n".join(lines)
    lines.extend(["## Per-patient full-period MAE", "",
                  "| Patient | A | B 2h | C 2h | B 4h | C 4h | B 6h | C 6h |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"])
    def mae(protocol: dict[str, Any]) -> str:
        metric = protocol.get("full_metrics")
        return "unavailable" if metric is None else f"{metric['mae_mg_dl']:.4f}"
    for patient in patients:
        p, identity = patient["protocols"], patient["identity"]
        lines.append(f"| {identity['dataset']}/{identity['patient_id']} | {mae(p['A'])} | "
                     f"{mae(p['B_2h'])} | {mae(p['C_2h'])} | {mae(p['B_4h'])} | "
                     f"{mae(p['C_4h'])} | {mae(p['B_6h'])} | {mae(p['C_6h'])} |")
    lines.extend(["", "## Patient-equal paired differences", ""])
    for horizon in HORIZON_HOURS:
        for label in ("B_minus_A", "C_minus_A", "C_minus_B"):
            item = aggregate.get("comparisons", {}).get(f"{horizon}h", {}).get(label, {})
            dist = item.get("patient_equal_metrics", {}).get("mae_mg_dl", {})
            wtl = item.get("mae_win_tie_loss", {})
            mean = dist.get("mean")
            lines.append(f"- {horizon}h {label.replace('_', ' ')} MAE: "
                         f"{'unavailable' if mean is None else f'{mean:.4f} mg/dL'}; "
                         f"win/tie/loss={wtl.get('left_better', 0)}/"
                         f"{wtl.get('tie', 0)}/{wtl.get('right_better', 0)}.")
            day1 = item.get("day1_mae_difference", {})
            day1_wtl = item.get("day1_mae_win_tie_loss", {})
            if day1.get("mean") is not None:
                lines.append(
                    f"  - Day 1 mean difference: {day1['mean']:.4f} mg/dL; "
                    f"win/tie/loss={day1_wtl.get('left_better', 0)}/"
                    f"{day1_wtl.get('tie', 0)}/{day1_wtl.get('right_better', 0)}."
                )
    lines.extend(["", "## Runtime and interpretation", ""])
    for name, item in aggregate.get("protocols", {}).items():
        lines.append(f"- {name}: {item.get('runtime_seconds', 0):.3f} seconds; "
                     f"complete patients={item.get('complete_patient_count', 0)}; "
                     f"incomplete={item.get('failure_or_incomplete_count', 0)}.")
        correction = item.get("absolute_state_glucose_correction_mg_dl", {})
        if correction.get("count"):
            lines.append(
                f"  - Absolute observed-vs-continuous-A origin correction: "
                f"mean {correction['mean']:.4f}, maximum {correction['maximum']:.4f} mg/dL."
            )
        changes = item.get("parameter_change_l2", {})
        if changes.get("count"):
            lines.append(
                f"  - Refreshed parameter-vector L2 change from A: "
                f"mean {changes['mean']:.6f}, maximum {changes['maximum']:.6f}."
            )
        state_changes = item.get("initialized_state_correction_l2", {})
        if state_changes.get("count"):
            lines.append(
                f"  - Initialized-vs-continuous-A state L2 correction: "
                f"mean {state_changes['mean']:.4f}, maximum {state_changes['maximum']:.4f}."
            )
    lines.extend([
        "- Negative MAE differences favor the left-hand protocol.",
        "- Day-specific metrics, parameter changes, state/glucose corrections, segment metrics, and failures are retained in results.json.",
        "- Later windows use observed histories under recorded treatment; they do not preserve hypothetical earlier basal interventions.",
        "- Parameter changes may reflect estimator variability and do not prove physiological variation.",
        "- This small development pilot is descriptive, not a significance test, clinical validation, or selection authorization.",
    ])
    return "\n".join(lines) + "\n"


def run_historical_replay_diagnostic(
    *, output_directory: str | Path = DEFAULT_RESULTS_DIRECTORY,
    write_plots: bool = True,
) -> dict[str, Any]:
    resolved = _resolve_repository_path(DEFAULT_DATASET_PATH)
    mandated = (REPOSITORY_ROOT / DEFAULT_DATASET_PATH).resolve()
    if resolved.resolve() != mandated:
        raise BasalPreparationError("diagnostic dataset differs from mandated file")
    data = pd.read_parquet(resolved)
    frozen = load_frozen_gru(DEFAULT_CHECKPOINT_PATH,
                             expected_sha256=FROZEN_CHECKPOINT_SHA256)
    data_before = _fingerprint(data)
    model_before = {name: value.detach().clone()
                    for name, value in frozen.model.state_dict().items()}
    actual_splits = {
        str((str(dataset), str(patient))): str(group["split"].iloc[0])
        for (dataset, patient), group in data.groupby(["dataset", "patient_id"], sort=False)
    }
    if actual_splits != frozen.checkpoint["patient_splits"]:
        raise BasalPreparationError("patient split metadata differs from frozen checkpoint")
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    patients: list[dict[str, Any]] = []
    failures: list[str] = []
    for identity in TARGET_PATIENTS:
        if actual_splits.get(str((identity.dataset, identity.patient_id))) != "development":
            failures.append(f"{identity.dataset}/{identity.patient_id}: not development")
            continue
        try:
            estimator = lambda history: predict_parameters(frozen, history)
            snapshot = prepare_basal_snapshot(
                data, identity, DECISION_TIMESTAMP, estimator,
                dataset_path=str(resolved.resolve()),
                checkpoint_sha256=frozen.checkpoint_sha256,
                checkpoint_metadata=frozen.checkpoint,
            )
            patient = evaluate_patient(data, snapshot, estimator)
            patients.append(patient)
            if write_plots:
                slug = f"{identity.dataset}-{identity.patient_id}".replace("#", "-")
                _plot_patient(patient, output / f"{slug}.png")
        except (ValueError, RuntimeError) as exc:
            failures.append(f"{identity.dataset}/{identity.patient_id}: {exc}")
    data_unchanged = data_before == _fingerprint(data)
    model_unchanged = _model_unchanged(frozen.model, model_before)
    if not data_unchanged or not model_unchanged:
        raise RuntimeError("diagnostic mutated source data or frozen model")
    payload = {
        "scope": "development-only historical replay-length diagnostic",
        "selection_authorization": False,
        "dataset_path": str(resolved.resolve()),
        "checkpoint_sha256": frozen.checkpoint_sha256,
        "configuration": {
            "decision_timestamp": DECISION_TIMESTAMP,
            "evaluation_interval": "[2027-01-02 00:00:00, 2027-01-04 00:00:00)",
            "patients": [asdict(identity) for identity in TARGET_PATIENTS],
            "horizon_hours": HORIZON_HOURS,
            "segment_counts": {str(h): 576 // (h * 12) for h in HORIZON_HOURS},
            "weight_kg": EFFECTIVE_WEIGHT_KG, "substeps": DEFAULT_SUBSTEPS,
            "physiological_carbohydrate": "consumed_carbs_g",
            "tie_tolerance_mg_dl": TIE_TOLERANCE_MG_DL,
            "protocol_interpretation": "aligned predictions from independent historical replays",
        },
        "source_immutability": {"dataframe_unchanged": data_unchanged,
                                "frozen_model_state_unchanged": model_unchanged},
        "patients": patients, "failures": failures,
        "aggregate": aggregate_results(patients),
    }
    (output / "results.json").write_text(
        json.dumps(payload, indent=2, default=_json_default) + "\n")
    (output / "REPORT.md").write_text(markdown_report(payload))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_RESULTS_DIRECTORY)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    result = run_historical_replay_diagnostic(
        output_directory=args.out, write_plots=not args.no_plots)
    print(json.dumps(result["aggregate"], indent=2, default=_json_default))


if __name__ == "__main__":
    main()
