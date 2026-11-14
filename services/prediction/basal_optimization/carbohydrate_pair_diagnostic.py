"""Paired two-hour announced-versus-consumed physiology diagnostic.

This module is retrospective diagnostic code only.  It does not alter the
production initialization, simulator, carbohydrate semantics, reliability
gate, candidate selection, or dosing policy.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd
import torch

from final_model_adapter import HISTORY, simulate as native_simulate
from bolus_optimization.checkpoint import load_frozen_gru, predict_parameters
from bolus_optimization.configuration import FROZEN_CHECKPOINT_SHA256, MODEL_FEATURES
from bolus_optimization.physiology import (
    DEFAULT_SUBSTEPS,
    PARAMETER_NAMES,
    STATE_NAMES,
    initialize_state,
    predict_from_state,
)

from .diagnostics import _dataframe_fingerprint, _json_default, _model_state_unchanged
from .preparation import (
    DEFAULT_CHECKPOINT_PATH,
    DEFAULT_DATASET_PATH,
    EFFECTIVE_WEIGHT_KG,
    INTERVAL,
    REPOSITORY_ROOT,
    PatientIdentity,
    _resolve_repository_path,
)
from .reliability import calculate_glucose_fit_metrics


FORECAST_STEPS = 24
INITIALIZATION_STEPS = 72
TIE_TOLERANCE_MG_DL = 1e-6
TARGET_PATIENT_IDS = (
    "adolescent#001",
    "adolescent#002",
    "adolescent#004",
    "adolescent#005",
    "adult#004",
)
DEFAULT_RESULTS_DIRECTORY = (
    REPOSITORY_ROOT / "services/prediction/results/basal_carbohydrate_pair_diagnostic"
)
CONTINUITY_COLUMNS = ("source_run_id", "source_record_id", "continuous_record_id")


@dataclass(frozen=True, order=True)
class PairedOrigin:
    dataset: str
    patient_id: str
    origin_timestamp: pd.Timestamp
    announced_initialization_total_g: float
    consumed_initialization_total_g: float
    announced_forecast_total_g: float
    consumed_forecast_total_g: float
    announcement_forecast_event_count: int
    consumption_forecast_event_count: int
    difference_during_initialization: bool
    difference_during_forecast: bool

    @property
    def identity(self) -> PatientIdentity:
        return PatientIdentity(self.dataset, self.patient_id)


@dataclass(frozen=True)
class PairedOriginSelection:
    origins: tuple[PairedOrigin, ...]
    requested_patient_ids: tuple[str, ...]
    confirmed_development_patient_ids: tuple[str, ...]
    max_windows_per_patient: int
    exclusions: tuple[str, ...]


@dataclass(frozen=True)
class PairedWindowTensors:
    identity: PatientIdentity
    origin_timestamp: pd.Timestamp
    gru_input: torch.Tensor
    parameters: torch.Tensor
    glucose_initialization: torch.Tensor
    announced_initialization_inputs: torch.Tensor
    consumed_initialization_inputs: torch.Tensor
    announced_forecast_inputs: torch.Tensor
    consumed_forecast_inputs: torch.Tensor
    target_glucose_mg_dl: torch.Tensor
    forecast_input_timestamps: tuple[pd.Timestamp, ...]
    output_timestamps: tuple[pd.Timestamp, ...]
    measurement_timestamps: tuple[pd.Timestamp | None, ...]


def _timestamp_index_equal(left: Iterable[object], right: Iterable[object]) -> bool:
    try:
        return pd.DatetimeIndex(left).as_unit("ns").equals(
            pd.DatetimeIndex(right).as_unit("ns")
        )
    except (TypeError, ValueError, OverflowError):
        return False


def _complete_grid(timestamps: pd.DatetimeIndex) -> bool:
    if not len(timestamps) or timestamps.has_duplicates:
        return False
    expected = pd.date_range(timestamps[0], periods=len(timestamps), freq=INTERVAL)
    return timestamps.as_unit("ns").equals(expected.as_unit("ns"))


def select_paired_origins(
    data: pd.DataFrame,
    *,
    patient_ids: tuple[str, ...] = TARGET_PATIENT_IDS,
    max_windows_per_patient: int = 3,
) -> PairedOriginSelection:
    """Select chronological meal origins without consulting future CGM accuracy."""

    if not 1 <= max_windows_per_patient <= 3:
        raise ValueError("max_windows_per_patient must be between 1 and 3")
    required = {
        "dataset", "patient_id", "split", "timestamp", "cgm_mg_dl",
        "basal_rate_u_per_hour", "bolus_u", "carbs_g", "consumed_carbs_g",
    }
    missing = sorted(required.difference(data.columns))
    if missing:
        raise ValueError(f"Paired diagnostic dataset is missing columns: {missing}")
    origins: list[PairedOrigin] = []
    exclusions: list[str] = []
    confirmed: list[str] = []
    for patient_id in patient_ids:
        matches = data.loc[data["patient_id"].astype(str).eq(patient_id)].copy()
        identities = matches[["dataset", "patient_id"]].drop_duplicates()
        if len(identities) != 1:
            exclusions.append(f"{patient_id}: identity missing or ambiguous")
            continue
        splits = matches["split"].drop_duplicates().astype(str).tolist()
        if splits != ["development"]:
            exclusions.append(f"{patient_id}: split is {splits}, not development")
            continue
        confirmed.append(patient_id)
        dataset = str(identities.iloc[0]["dataset"])
        matches["timestamp"] = pd.to_datetime(matches["timestamp"], errors="coerce")
        if matches["timestamp"].isna().any():
            exclusions.append(f"{dataset}/{patient_id}: invalid timestamps")
            continue
        continuity = [column for column in CONTINUITY_COLUMNS if column in matches.columns]
        if continuity and matches[continuity].isna().any(axis=None):
            exclusions.append(f"{dataset}/{patient_id}: missing continuity identifier")
            continue
        segments = (
            matches.groupby(continuity, sort=True, dropna=False)
            if continuity else ((None, matches),)
        )
        eligible: list[PairedOrigin] = []
        for _, segment in segments:
            ordered = segment.sort_values("timestamp", kind="stable").reset_index(drop=True)
            timestamps = pd.DatetimeIndex(ordered["timestamp"])
            for index in np.flatnonzero(ordered["carbs_g"].to_numpy(np.float64) > 0):
                if index < HISTORY or index + FORECAST_STEPS >= len(ordered):
                    continue
                complete = timestamps[index - HISTORY : index + FORECAST_STEPS + 1]
                if len(complete) != HISTORY + FORECAST_STEPS + 1 or not _complete_grid(complete):
                    continue
                initialization = ordered.iloc[index - INITIALIZATION_STEPS : index]
                forecast = ordered.iloc[index : index + FORECAST_STEPS]
                announced_initialization = initialization["carbs_g"].to_numpy(np.float64)
                consumed_initialization = initialization["consumed_carbs_g"].to_numpy(np.float64)
                announced_forecast = forecast["carbs_g"].to_numpy(np.float64)
                consumed_forecast = forecast["consumed_carbs_g"].to_numpy(np.float64)
                differs_initialization = not np.array_equal(
                    announced_initialization, consumed_initialization
                )
                differs_forecast = not np.array_equal(announced_forecast, consumed_forecast)
                if not (differs_initialization or differs_forecast):
                    continue
                eligible.append(PairedOrigin(
                    dataset,
                    patient_id,
                    pd.Timestamp(timestamps[index]),
                    float(announced_initialization.sum()),
                    float(consumed_initialization.sum()),
                    float(announced_forecast.sum()),
                    float(consumed_forecast.sum()),
                    int((announced_forecast > 0).sum()),
                    int((consumed_forecast > 0).sum()),
                    differs_initialization,
                    differs_forecast,
                ))
        eligible.sort(key=lambda item: item.origin_timestamp)
        if not eligible:
            exclusions.append(f"{dataset}/{patient_id}: no eligible differing meal origin")
        origins.extend(eligible[:max_windows_per_patient])
    return PairedOriginSelection(
        tuple(origins), tuple(patient_ids), tuple(confirmed),
        max_windows_per_patient, tuple(exclusions),
    )


def _physiological_inputs(frame: pd.DataFrame, carbohydrate_column: str) -> torch.Tensor:
    values = np.column_stack((
        frame["basal_rate_u_per_hour"].to_numpy(np.float32, copy=True),
        frame["bolus_u"].to_numpy(np.float32, copy=True),
        frame[carbohydrate_column].to_numpy(np.float32, copy=True),
    ))
    return torch.from_numpy(values)


def assemble_paired_window(
    patient: pd.DataFrame,
    origin: PairedOrigin,
    parameter_estimator: Callable[[torch.Tensor], torch.Tensor],
) -> PairedWindowTensors:
    """Assemble both arms and estimate one shared parameter vector."""

    rows = patient.sort_values("timestamp", kind="stable").reset_index(drop=True).copy()
    rows["timestamp"] = pd.to_datetime(rows["timestamp"], errors="coerce")
    positions = np.flatnonzero(
        pd.DatetimeIndex(rows["timestamp"]).as_unit("ns")
        == pd.DatetimeIndex([origin.origin_timestamp]).as_unit("ns")[0]
    )
    if len(positions) != 1:
        raise ValueError("Paired origin must identify exactly one patient row")
    index = int(positions[0])
    if index < HISTORY or index + FORECAST_STEPS >= len(rows):
        raise ValueError("Paired origin lacks required history, inputs, or outcomes")
    history = rows.iloc[index - HISTORY : index]
    boundary = rows.iloc[index]
    initialization = rows.iloc[index - INITIALIZATION_STEPS : index]
    glucose_initialization = rows.iloc[
        index - INITIALIZATION_STEPS : index + 1
    ]["cgm_mg_dl"].to_numpy(np.float32, copy=True)
    forecast = rows.iloc[index : index + FORECAST_STEPS]
    outcomes = rows.iloc[index + 1 : index + FORECAST_STEPS + 1]
    required_timestamps = pd.DatetimeIndex(
        rows.iloc[index - HISTORY : index + FORECAST_STEPS + 1]["timestamp"]
    )
    if not _complete_grid(required_timestamps):
        raise ValueError("Paired window timestamps are not an exact five-minute grid")
    required_rows = rows.iloc[index - HISTORY : index + FORECAST_STEPS + 1]
    for column in CONTINUITY_COLUMNS:
        if column in required_rows.columns and (
            required_rows[column].isna().any()
            or required_rows[column].nunique(dropna=False) != 1
        ):
            raise ValueError(f"Paired window crosses or misses {column}")
    numeric_columns = (
        "cgm_mg_dl", "basal_rate_u_per_hour", "bolus_u",
        "carbs_g", "consumed_carbs_g",
    )
    numeric = required_rows.loc[:, numeric_columns].to_numpy(np.float64)
    if not np.isfinite(numeric).all() or (numeric < 0).any():
        raise ValueError("Paired window contains missing, nonfinite, or negative values")
    if (required_rows["cgm_mg_dl"].to_numpy(np.float64) <= 0).any():
        raise ValueError("Paired window contains nonpositive CGM")
    completed = history.loc[:, MODEL_FEATURES].to_numpy(np.float32, copy=True)
    boundary_features = np.asarray([[
        boundary["cgm_mg_dl"], boundary["basal_rate_u_per_hour"],
        0.0, boundary["carbs_g"],
    ]], dtype=np.float32)
    gru_input = torch.from_numpy(np.concatenate((completed, boundary_features)))
    with torch.inference_mode():
        estimated = parameter_estimator(gru_input.unsqueeze(0))
    parameters = estimated[0] if tuple(estimated.shape) == (1, 7) else estimated
    if tuple(parameters.shape) != (7,) or not torch.isfinite(parameters).all().item():
        raise ValueError("Parameter estimator must return one finite seven-vector")
    parameters = parameters.to(torch.float32).detach().clone()
    target = torch.from_numpy(outcomes["cgm_mg_dl"].to_numpy(np.float32, copy=True))
    input_timestamps = tuple(pd.Timestamp(value) for value in forecast["timestamp"])
    output_timestamps = tuple(pd.Timestamp(value) for value in outcomes["timestamp"])
    expected_outputs = pd.date_range(
        origin.origin_timestamp + INTERVAL, periods=FORECAST_STEPS, freq=INTERVAL
    )
    if not _timestamp_index_equal(output_timestamps, expected_outputs):
        raise ValueError("Paired output timestamps must cover O + 5 minutes through O + 2 hours")
    measurement_timestamps = tuple(
        None if "cgm_measurement_timestamp" not in outcomes.columns or pd.isna(value)
        else pd.Timestamp(value)
        for value in (
            outcomes["cgm_measurement_timestamp"]
            if "cgm_measurement_timestamp" in outcomes.columns
            else [None] * FORECAST_STEPS
        )
    )
    for availability, measurement in zip(output_timestamps, measurement_timestamps):
        if measurement is not None and measurement > availability:
            raise ValueError("CGM measurement timestamp is later than availability")
    return PairedWindowTensors(
        origin.identity,
        origin.origin_timestamp,
        gru_input,
        parameters,
        torch.from_numpy(glucose_initialization),
        _physiological_inputs(initialization, "carbs_g"),
        _physiological_inputs(initialization, "consumed_carbs_g"),
        _physiological_inputs(forecast, "carbs_g"),
        _physiological_inputs(forecast, "consumed_carbs_g"),
        target,
        input_timestamps,
        output_timestamps,
        measurement_timestamps,
    )


def _arm_result(
    name: str,
    glucose: torch.Tensor,
    initialization_inputs: torch.Tensor,
    forecast_inputs: torch.Tensor,
    parameters: torch.Tensor,
    targets: torch.Tensor,
) -> tuple[dict[str, Any], torch.Tensor | None, torch.Tensor | None]:
    initialized = initialize_state(
        glucose, initialization_inputs, parameters,
        weight_kg=EFFECTIVE_WEIGHT_KG, substeps=DEFAULT_SUBSTEPS,
    )
    if initialized.validity.failures:
        failure = initialized.validity.failures[0]
        return ({
            "arm": name,
            "status": "initialization_failed",
            "failure": asdict(failure),
            "coverage": {"expected": FORECAST_STEPS, "matched": 0},
            "metrics": None,
        }, initialized.state.detach().clone(), None)
    predicted = predict_from_state(
        initialized.state, parameters, forecast_inputs,
        weight_kg=EFFECTIVE_WEIGHT_KG, substeps=DEFAULT_SUBSTEPS,
    )
    if not predicted.validity.all_valid:
        failure = predicted.validity.failures[0]
        matched = int(torch.isfinite(predicted.glucose_mg_dl).sum().item())
        return ({
            "arm": name,
            "status": "forecast_failed",
            "failure": asdict(failure),
            "coverage": {"expected": FORECAST_STEPS, "matched": matched},
            "metrics": None,
        }, initialized.state.detach().clone(), predicted.glucose_mg_dl.detach().clone())
    values = predicted.glucose_mg_dl.detach().cpu().numpy().astype(np.float64)
    observed = targets.detach().cpu().numpy().astype(np.float64)
    metrics = calculate_glucose_fit_metrics(values, observed)
    return ({
        "arm": name,
        "status": "complete",
        "failure": None,
        "coverage": {"expected": FORECAST_STEPS, "matched": FORECAST_STEPS},
        "metrics": {
            **asdict(metrics),
            "endpoint_error_mg_dl": float(values[-1] - observed[-1]),
        },
    }, initialized.state.detach().clone(), predicted.glucose_mg_dl.detach().clone())


def evaluate_paired_window(window: PairedWindowTensors) -> dict[str, Any]:
    """Run both arms with shared parameters and unchanged authoritative solver."""

    arm_a, state_a, prediction_a = _arm_result(
        "announced-carbohydrate physiology",
        window.glucose_initialization,
        window.announced_initialization_inputs,
        window.announced_forecast_inputs,
        window.parameters,
        window.target_glucose_mg_dl,
    )
    arm_c, state_c, prediction_c = _arm_result(
        "consumed-carbohydrate physiology",
        window.glucose_initialization,
        window.consumed_initialization_inputs,
        window.consumed_forecast_inputs,
        window.parameters,
        window.target_glucose_mg_dl,
    )
    initial_state_difference = None
    if state_a is not None and state_c is not None and torch.isfinite(state_a).all() and torch.isfinite(state_c).all():
        difference = (state_a - state_c).detach().cpu().numpy().astype(np.float64)
        initial_state_difference = {
            "component_difference_A_minus_C": dict(zip(STATE_NAMES, difference.tolist())),
            "l2_norm": float(np.linalg.norm(difference)),
            "maximum_absolute_component_difference": float(np.abs(difference).max()),
        }
    native_parity = {"status": "unavailable", "maximum_absolute_difference_mg_dl": None}
    if arm_a["status"] == "complete":
        native_history_inputs = torch.cat((
            window.announced_initialization_inputs,
            window.announced_forecast_inputs[:1],
        ))
        native_history = torch.cat((
            window.glucose_initialization[:, None], native_history_inputs,
        ), dim=1).unsqueeze(0)
        native_future = window.announced_forecast_inputs.unsqueeze(0)
        with torch.inference_mode():
            native_prediction = native_simulate(
                native_history,
                native_future,
                window.parameters.unsqueeze(0),
                EFFECTIVE_WEIGHT_KG,
                DEFAULT_SUBSTEPS,
            )[0]
        difference = torch.abs(native_prediction - prediction_a)
        native_parity = {
            "status": "matched",
            "maximum_absolute_difference_mg_dl": float(difference.max().item()),
            "remaining_differences": (
                "GRU boundary construction is the standard runtime convention; parity check "
                "starts from the shared estimated parameter vector."
            ),
        }
    paired = None
    if arm_a["metrics"] is not None and arm_c["metrics"] is not None:
        paired = {
            field: arm_a["metrics"][field] - arm_c["metrics"][field]
            for field in (
                "mae_mg_dl", "rmse_mg_dl", "mean_signed_error_mg_dl",
                "maximum_absolute_error_mg_dl", "endpoint_error_mg_dl",
            )
        }
    return {
        "identity": asdict(window.identity),
        "origin_timestamp": window.origin_timestamp,
        "output_timestamps": window.output_timestamps,
        "shared_gru_input_shape": list(window.gru_input.shape),
        "shared_parameters": dict(zip(PARAMETER_NAMES, window.parameters.tolist())),
        "arm_a": arm_a,
        "arm_c": arm_c,
        "paired_difference_A_minus_C": paired,
        "initial_state_difference": initial_state_difference,
        "native_announced_simulator_parity": native_parity,
        "predictions": {
            "observed": window.target_glucose_mg_dl.detach().cpu().tolist(),
            "arm_a": None if prediction_a is None else prediction_a.detach().cpu().tolist(),
            "arm_c": None if prediction_c is None else prediction_c.detach().cpu().tolist(),
        },
    }


def _plot_pair(window: PairedWindowTensors, result: dict[str, Any], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    timestamps = pd.DatetimeIndex(window.output_timestamps)
    observed = np.asarray(result["predictions"]["observed"])
    prediction_a = result["predictions"]["arm_a"]
    prediction_c = result["predictions"]["arm_c"]
    figure, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                gridspec_kw={"height_ratios": [2.2, 1.0]})
    axes[0].plot(timestamps, observed, label="Recorded CGM", linewidth=1.5)
    if prediction_a is not None:
        axes[0].plot(timestamps, prediction_a, label="Arm A: announced physiology")
    if prediction_c is not None:
        axes[0].plot(timestamps, prediction_c, label="Arm C: consumed physiology")
    axes[0].set_ylabel("Glucose (mg/dL)")
    axes[0].legend(loc="best")
    axes[0].grid(alpha=0.25)
    input_time = pd.DatetimeIndex(window.forecast_input_timestamps)
    announced = window.announced_forecast_inputs[:, 2].numpy()
    consumed = window.consumed_forecast_inputs[:, 2].numpy()
    axes[1].vlines(input_time[announced > 0], 0, announced[announced > 0],
                   color="tab:orange", linewidth=3, label="Announced carbs")
    axes[1].vlines(input_time[consumed > 0], 0, -consumed[consumed > 0],
                   color="tab:green", linewidth=3, label="Consumed carbs")
    axes[1].axhline(0, color="0.4", linewidth=0.8)
    axes[1].set_ylabel("Carbohydrate (g)\nannounced + / consumed −")
    axes[1].set_xlabel("Forecast time; origin event is interval 0")
    axes[1].legend(loc="best")
    axes[1].grid(alpha=0.2)
    figure.suptitle(
        f"{window.identity.dataset}/{window.identity.patient_id} at {window.origin_timestamp}"
    )
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def _paired_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [item for item in results if item["paired_difference_A_minus_C"] is not None]
    fields = (
        "mae_mg_dl", "rmse_mg_dl", "mean_signed_error_mg_dl",
        "maximum_absolute_error_mg_dl", "endpoint_error_mg_dl",
    )
    patient_rows = []
    for identity in sorted({
        (item["identity"]["dataset"], item["identity"]["patient_id"])
        for item in complete
    }):
        patient = [item for item in complete if (
            item["identity"]["dataset"], item["identity"]["patient_id"]
        ) == identity]
        patient_rows.append({
            "identity": {"dataset": identity[0], "patient_id": identity[1]},
            "completed_pair_count": len(patient),
            "mean_arm_a_metrics": {
                field: float(np.mean([item["arm_a"]["metrics"][field] for item in patient]))
                for field in fields
            },
            "mean_arm_c_metrics": {
                field: float(np.mean([item["arm_c"]["metrics"][field] for item in patient]))
                for field in fields
            },
            "mean_paired_difference_A_minus_C": {
                field: float(np.mean([
                    item["paired_difference_A_minus_C"][field] for item in patient
                ]))
                for field in fields
            },
        })
    equally_weighted = {
        field: {
            "count": len(patient_rows),
            "mean": (
                float(np.mean([
                    row["mean_paired_difference_A_minus_C"][field]
                    for row in patient_rows
                ])) if patient_rows else None
            ),
            "median": (
                float(np.median([
                    row["mean_paired_difference_A_minus_C"][field]
                    for row in patient_rows
                ])) if patient_rows else None
            ),
        }
        for field in fields
    }
    equally_weighted_arm_metrics = {
        arm: {
            field: (
                float(np.mean([row[f"mean_{arm}_metrics"][field] for row in patient_rows]))
                if patient_rows else None
            )
            for field in fields
        }
        for arm in ("arm_a", "arm_c")
    }
    outcomes = {"announced_better": 0, "tie": 0, "consumed_better": 0}
    for item in complete:
        difference = item["paired_difference_A_minus_C"]["mae_mg_dl"]
        if difference < -TIE_TOLERANCE_MG_DL:
            outcomes["announced_better"] += 1
        elif difference > TIE_TOLERANCE_MG_DL:
            outcomes["consumed_better"] += 1
        else:
            outcomes["tie"] += 1
    return {
        "result_count": len(results),
        "complete_pair_count": len(complete),
        "arm_a_failure_count": sum(item["arm_a"]["status"] != "complete" for item in results),
        "arm_c_failure_count": sum(item["arm_c"]["status"] != "complete" for item in results),
        "per_patient": patient_rows,
        "equally_weighted_patient_arm_metrics": equally_weighted_arm_metrics,
        "equally_weighted_patient_summary": equally_weighted,
        "mae_win_tie_loss": outcomes,
        "tie_tolerance_mg_dl": TIE_TOLERANCE_MG_DL,
        "difference_direction": "Arm A minus Arm C; negative MAE/RMSE favors announced physiology",
    }


def _markdown(payload: dict[str, Any]) -> str:
    def value(item: float | None) -> str:
        return "unavailable" if item is None else f"{item:.4f}"

    summary = payload["summary"]
    lines = [
        "# Paired two-hour carbohydrate-physiology diagnostic",
        "",
        "Development-only retrospective diagnostic. Selection authorization remains false.",
        "",
        "## Configuration",
        "",
        "- Arm A: announced-carbohydrate physiology for six-hour initialization and two-hour forecast.",
        "- Arm C: consumed-carbohydrate physiology for both phases.",
        "- GRU input, estimated parameters, basal, bolus, CGM targets, weight, solver, and timestamps are paired and identical.",
        "- This is the combined initialization-plus-forecast convention effect; it does not separate the phases.",
        f"- Tie tolerance: {TIE_TOLERANCE_MG_DL:g} mg/dL.",
        "",
        "## Coverage",
        "",
        f"- Selected origins: {len(payload['origins'])}",
        f"- Completed pairs: {summary['complete_pair_count']}",
        f"- Arm A failures: {summary['arm_a_failure_count']}",
        f"- Arm C failures: {summary['arm_c_failure_count']}",
        f"- Selection exclusions: {len(payload['selection']['exclusions'])}",
        f"- Execution failures: {len(payload['execution_failures'])}",
        "",
    ]
    if payload["selection"]["exclusions"] or payload["execution_failures"]:
        lines.extend(["## Exclusions and failures", ""])
        lines.extend(f"- {reason}" for reason in payload["selection"]["exclusions"])
        lines.extend(f"- {reason}" for reason in payload["execution_failures"])
        lines.append("")
    lines.extend([
        "## Selected-origin audit",
        "",
        "| Patient | Origin | Difference phase | Init A/C (g) | Forecast A/C (g) | Forecast event intervals A/C |",
        "|---|---|---|---:|---:|---:|",
    ])
    for origin in payload["origins"]:
        phases = []
        if origin["difference_during_initialization"]:
            phases.append("initialization")
        if origin["difference_during_forecast"]:
            phases.append("forecast")
        lines.append(
            f"| {origin['dataset']}/{origin['patient_id']} | {origin['origin_timestamp']} | "
            f"{'+'.join(phases) or 'none'} | "
            f"{origin['announced_initialization_total_g']:.1f}/"
            f"{origin['consumed_initialization_total_g']:.1f} | "
            f"{origin['announced_forecast_total_g']:.1f}/"
            f"{origin['consumed_forecast_total_g']:.1f} | "
            f"{origin['announcement_forecast_event_count']}/"
            f"{origin['consumption_forecast_event_count']} |"
        )
    lines.extend([
        "",
        "## Per-window paired results",
        "",
        "| Patient | Origin | A MAE | C MAE | A−C MAE | A−C RMSE | A status | C status |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ])
    for result in payload["results"]:
        a = result["arm_a"]["metrics"]
        c = result["arm_c"]["metrics"]
        paired = result["paired_difference_A_minus_C"]
        lines.append(
            f"| {result['identity']['dataset']}/{result['identity']['patient_id']} | "
            f"{result['origin_timestamp']} | "
            f"{value(None if a is None else a['mae_mg_dl'])} | "
            f"{value(None if c is None else c['mae_mg_dl'])} | "
            f"{value(None if paired is None else paired['mae_mg_dl'])} | "
            f"{value(None if paired is None else paired['rmse_mg_dl'])} | "
            f"{result['arm_a']['status']} | {result['arm_c']['status']} |"
        )
    lines.extend(["", "## Patient-equal summary", ""])
    arm_metrics = summary["equally_weighted_patient_arm_metrics"]
    lines.append(
        f"- Arm A mean MAE/RMSE: {value(arm_metrics['arm_a']['mae_mg_dl'])}/"
        f"{value(arm_metrics['arm_a']['rmse_mg_dl'])} mg/dL."
    )
    lines.append(
        f"- Arm C mean MAE/RMSE: {value(arm_metrics['arm_c']['mae_mg_dl'])}/"
        f"{value(arm_metrics['arm_c']['rmse_mg_dl'])} mg/dL."
    )
    for field, distribution in summary["equally_weighted_patient_summary"].items():
        lines.append(
            f"- {field}: mean A−C {value(distribution['mean'])}, "
            f"median {value(distribution['median'])}, patients={distribution['count']}"
        )
    lines.extend([
        "",
        "| Patient | Completed pairs | Mean A−C MAE | Mean A−C RMSE |",
        "|---|---:|---:|---:|",
    ])
    for patient in summary["per_patient"]:
        difference = patient["mean_paired_difference_A_minus_C"]
        lines.append(
            f"| {patient['identity']['dataset']}/{patient['identity']['patient_id']} | "
            f"{patient['completed_pair_count']} | {value(difference['mae_mg_dl'])} | "
            f"{value(difference['rmse_mg_dl'])} |"
        )
    outcomes = summary["mae_win_tie_loss"]
    parity_values = [
        result["native_announced_simulator_parity"].get(
            "maximum_absolute_difference_mg_dl"
        )
        for result in payload["results"]
        if result["native_announced_simulator_parity"].get(
            "maximum_absolute_difference_mg_dl"
        ) is not None
    ]
    initialization_difference_count = sum(
        bool(origin["difference_during_initialization"])
        for origin in payload["origins"]
    )
    forecast_difference_count = sum(
        bool(origin["difference_during_forecast"])
        for origin in payload["origins"]
    )
    lines.extend([
        "",
        f"MAE win/tie/loss: announced better={outcomes['announced_better']}, "
        f"tie={outcomes['tie']}, consumed better={outcomes['consumed_better']}.",
        "",
        "## Parity and interpretation",
        "",
        f"- Announced-arm native-simulator parity was available for {len(parity_values)} windows; "
        f"maximum absolute difference was {value(max(parity_values) if parity_values else None)} mg/dL.",
        f"- Carbohydrate inputs differed during initialization in {initialization_difference_count} "
        f"origins and during forecast in {forecast_difference_count} origins.",
        f"- Source dataframe unchanged: {payload['source_immutability']['dataframe_unchanged']}; "
        f"frozen model unchanged: {payload['source_immutability']['frozen_model_state_unchanged']}.",
        f"- The patient-equal A−C MAE was {value(summary['equally_weighted_patient_summary']['mae_mg_dl']['mean'])} mg/dL, "
        f"with {outcomes['announced_better']} announced wins and {outcomes['consumed_better']} consumed wins. "
        "This supports heterogeneous, near-zero average short-horizon effect in this selected pilot, not equivalence.",
        "- This comparison combines initialization and forecast convention changes and cannot attribute their effects separately.",
        "- This small selected pilot provides descriptive evidence only. It does not establish statistical significance, clinical superiority, deployable future-meal knowledge, or reliable 48-hour prediction.",
        "- Smallest next diagnostic: repeat paired arms while changing only initialization carbohydrate, then only forecast carbohydrate, on the same fixed origins and parameters.",
    ])
    return "\n".join(lines) + "\n"


def run_paired_carbohydrate_diagnostic(
    *,
    output_directory: str | Path = DEFAULT_RESULTS_DIRECTORY,
    max_windows_per_patient: int = 3,
    write_plots: bool = True,
) -> dict[str, Any]:
    resolved = _resolve_repository_path(DEFAULT_DATASET_PATH)
    mandated = (REPOSITORY_ROOT / DEFAULT_DATASET_PATH).resolve()
    if resolved.resolve() != mandated:
        raise ValueError("Paired diagnostic requires the mandated repository dataset")
    data = pd.read_parquet(resolved)
    data_fingerprint = _dataframe_fingerprint(data)
    frozen = load_frozen_gru(DEFAULT_CHECKPOINT_PATH, expected_sha256=FROZEN_CHECKPOINT_SHA256)
    model_before = {
        name: value.detach().clone() for name, value in frozen.model.state_dict().items()
    }
    selection = select_paired_origins(
        data, max_windows_per_patient=max_windows_per_patient
    )
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for origin in selection.origins:
        try:
            patient = data.loc[
                data["dataset"].astype(str).eq(origin.dataset)
                & data["patient_id"].astype(str).eq(origin.patient_id)
            ]
            window = assemble_paired_window(
                patient,
                origin,
                lambda history: predict_parameters(frozen, history),
            )
            result = evaluate_paired_window(window)
            result["origin_audit"] = asdict(origin)
            slug = (
                f"{origin.dataset}-{origin.patient_id}-{origin.origin_timestamp:%Y%m%d%H%M}"
                .replace("#", "-").replace("/", "-")
            )
            plot_name = f"{slug}.png"
            if write_plots:
                _plot_pair(window, result, output / plot_name)
            result["plot"] = plot_name if write_plots else None
            results.append(result)
        except (ValueError, RuntimeError) as exc:
            failures.append(
                f"{origin.dataset}/{origin.patient_id} at {origin.origin_timestamp}: {exc}"
            )
    unchanged_data = _dataframe_fingerprint(data) == data_fingerprint
    unchanged_model = _model_state_unchanged(frozen.model, model_before)
    if not unchanged_data or not unchanged_model:
        raise RuntimeError("Paired diagnostic mutated source data or frozen model")
    payload = {
        "configuration": {
            "scope": "bounded paired development-only two-hour diagnostic",
            "dataset_path": str(resolved.resolve()),
            "checkpoint_sha256": frozen.checkpoint_sha256,
            "target_patient_ids": TARGET_PATIENT_IDS,
            "max_windows_per_patient": max_windows_per_patient,
            "forecast_steps": FORECAST_STEPS,
            "forecast_minutes": FORECAST_STEPS * 5,
            "initialization_steps": INITIALIZATION_STEPS,
            "weight_kg": EFFECTIVE_WEIGHT_KG,
            "substeps": DEFAULT_SUBSTEPS,
            "future_recorded_events_used": True,
            "future_use_scope": "retrospective diagnostic only",
            "selection_authorized": False,
        },
        "selection": asdict(selection),
        "origins": [asdict(origin) for origin in selection.origins],
        "results": results,
        "execution_failures": failures,
        "source_immutability": {
            "dataframe_unchanged": unchanged_data,
            "frozen_model_state_unchanged": unchanged_model,
        },
        "summary": _paired_summary(results),
    }
    documents = {
        "configuration.json": payload["configuration"],
        "origins.json": {"selection": payload["selection"], "origins": payload["origins"]},
        "window_results.json": {"results": results, "execution_failures": failures},
        "summary.json": {
            "summary": payload["summary"],
            "source_immutability": payload["source_immutability"],
            "selection_authorized": False,
        },
    }
    for filename, content in documents.items():
        (output / filename).write_text(
            json.dumps(content, indent=2, default=_json_default) + "\n"
        )
    (output / "REPORT.md").write_text(_markdown(payload))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_RESULTS_DIRECTORY)
    parser.add_argument("--max-windows-per-patient", type=int, default=3)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    result = run_paired_carbohydrate_diagnostic(
        output_directory=args.out,
        max_windows_per_patient=args.max_windows_per_patient,
        write_plots=not args.no_plots,
    )
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
