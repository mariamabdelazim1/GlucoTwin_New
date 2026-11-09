"""Step 4 recorded-action replay diagnostic for carbohydrate conventions."""

from __future__ import annotations

import argparse
import json
import importlib.metadata
import math
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import torch

import final_model_adapter as original
from final_model_adapter import sha256

from .checkpoint import load_frozen_gru, predict_parameters
from .configuration import FROZEN_CHECKPOINT_SHA256, MODEL_FEATURES
from .data import read_optimization_data
from .physiology import (
    PHYSIOLOGICAL_INPUT_NAMES,
    initialize_state,
    predict_from_state,
)


HISTORY_STEPS = 288
INITIALIZATION_INTERVALS = 72
FORECAST_STEPS = 48
ORIGIN_STRIDE = 48
ENDPOINTS = (30, 60, 120, 180, 240)
METHODS = (
    "A_original_convention",
    "B_future_consumption",
    "C_intended_consumption",
    "persistence",
)
PHYSIOLOGY_METHODS = METHODS[:3]
EXPECTED_SOURCE_HASHES = {
    "final_model_adapter.py": "22522d4f3cb12169b0a57192844c7126293be13aaedc33085ce8e7566732b154",
    "optimize.py": "7b2dfb7850b846ae8c480cccf58b968ea4e54a8953d5b7a66aaaea808dbe9c28",
    "test.py": "6cc4770aa148247f20fa1ebd06cea7eb8c87cc1da9a9554a80cd4dea89f0bd3c",
}


@dataclass(frozen=True)
class EvaluationWindows:
    origins: pd.DataFrame
    gru_history: np.ndarray
    initialization_cgm: np.ndarray
    initialization_announced_inputs: np.ndarray
    initialization_consumed_inputs: np.ndarray
    future_announced_inputs: np.ndarray
    future_consumed_inputs: np.ndarray
    targets: np.ndarray


def _phys_inputs(values: np.ndarray, carbohydrate_index: int) -> np.ndarray:
    return np.stack((values[:, 1], values[:, 2], values[:, carbohydrate_index]), axis=-1)


def build_evaluation_windows(
    data: pd.DataFrame,
    *,
    splits=("development", "validation"),
    max_windows_per_patient: int = 0,
) -> EvaluationWindows:
    """Build aligned 24-hour histories and four-hour targets.

    Origins are patient-local indexes ``288, 336, ...``. The final eligible
    origin satisfies ``i + 48 < len(patient)`` so all 48 interval inputs and
    all 48 next-boundary CGM targets exist.
    """

    if max_windows_per_patient < 0:
        raise ValueError("max_windows_per_patient must be nonnegative")
    allowed = set(splits)
    if "testing" in allowed:
        raise ValueError("Testing patients are forbidden in Step 4")
    selected = data[data["split"].isin(allowed)]
    records = []
    gru_histories = []
    initialization_cgm = []
    init_announced = []
    init_consumed = []
    future_announced = []
    future_consumed = []
    targets = []
    for (dataset, patient_id), group in selected.groupby(
        ["dataset", "patient_id"], sort=True
    ):
        group = group.reset_index(drop=True)
        if group["split"].nunique() != 1:
            raise ValueError(f"Patient crosses splits: {(dataset, patient_id)}")
        values = group[list(MODEL_FEATURES) + ["consumed_carbs_g"]].to_numpy("float32")
        origins = np.arange(HISTORY_STEPS, len(group) - FORECAST_STEPS, ORIGIN_STRIDE)
        if max_windows_per_patient:
            origins = origins[:max_windows_per_patient]
        for origin in origins:
            gru = values[origin - HISTORY_STEPS : origin + 1, :4]
            cgm = values[origin - INITIALIZATION_INTERVALS : origin + 1, 0]
            hist_values = values[origin - INITIALIZATION_INTERVALS : origin]
            future_values = values[origin : origin + FORECAST_STEPS]
            target = values[origin + 1 : origin + FORECAST_STEPS + 1, 0]
            if (
                gru.shape != (HISTORY_STEPS + 1, 4)
                or cgm.shape != (INITIALIZATION_INTERVALS + 1,)
                or hist_values.shape[0] != INITIALIZATION_INTERVALS
                or future_values.shape[0] != FORECAST_STEPS
                or target.shape != (FORECAST_STEPS,)
            ):
                raise RuntimeError("Window alignment invariant failed")
            window_id = len(records)
            records.append(
                {
                    "window_id": window_id,
                    "dataset": str(dataset),
                    "patient_id": str(patient_id),
                    "split": str(group.loc[origin, "split"]),
                    "origin": group.loc[origin, "timestamp"],
                    "patient_origin_index": int(origin),
                    "current_glucose_mg_dl": float(values[origin, 0]),
                    "announced_carbs_at_origin_g": float(values[origin, 3]),
                    "consumed_carbs_at_origin_g": float(values[origin, 4]),
                    "future_announced_carbs_g": float(future_values[:, 3].sum()),
                    "future_consumed_carbs_g": float(future_values[:, 4].sum()),
                }
            )
            gru_histories.append(gru)
            initialization_cgm.append(cgm)
            init_announced.append(_phys_inputs(hist_values, 3))
            init_consumed.append(_phys_inputs(hist_values, 4))
            future_announced.append(_phys_inputs(future_values, 3))
            future_consumed.append(_phys_inputs(future_values, 4))
            targets.append(target)
    if not records:
        raise ValueError("No eligible Step 4 windows")
    origins_frame = pd.DataFrame(records)
    if not set(origins_frame["split"]).issubset({"development", "validation"}):
        raise RuntimeError("Testing patient entered Step 4 evaluation")
    return EvaluationWindows(
        origins_frame,
        np.stack(gru_histories),
        np.stack(initialization_cgm),
        np.stack(init_announced),
        np.stack(init_consumed),
        np.stack(future_announced),
        np.stack(future_consumed),
        np.stack(targets),
    )


def configuration_inputs(windows: EvaluationWindows, method: str):
    """Select history/future carbohydrate conventions independently."""

    if method == "A_original_convention":
        return windows.initialization_announced_inputs, windows.future_announced_inputs
    if method == "B_future_consumption":
        return windows.initialization_announced_inputs, windows.future_consumed_inputs
    if method == "C_intended_consumption":
        return windows.initialization_consumed_inputs, windows.future_consumed_inputs
    raise ValueError(f"Unknown physiology method: {method}")


def _metric(prediction: np.ndarray, target: np.ndarray) -> dict:
    available = np.isfinite(prediction) & np.isfinite(target)
    count = int(available.sum())
    if not count:
        return {
            "n": 0,
            "mae_mg_dl": None,
            "rmse_mg_dl": None,
            "mean_signed_error_mg_dl": None,
            "max_absolute_error_mg_dl": None,
        }
    error = prediction[available] - target[available]
    return {
        "n": count,
        "mae_mg_dl": float(np.abs(error).mean()),
        "rmse_mg_dl": float(np.sqrt(np.square(error).mean())),
        "mean_signed_error_mg_dl": float(error.mean()),
        "max_absolute_error_mg_dl": float(np.abs(error).max()),
    }


def paired_error_difference(
    first: np.ndarray, second: np.ndarray, target: np.ndarray
) -> dict:
    """Compare methods on exactly matching finite observations.

    Positive MAE/RMSE differences mean the second method is worse.
    """

    mask = np.isfinite(first) & np.isfinite(second) & np.isfinite(target)
    n = int(mask.sum())
    if not n:
        return {"n": 0, "mae_difference_second_minus_first": None,
                "rmse_difference_second_minus_first": None,
                "second_better_fraction": None}
    first_error = first[mask] - target[mask]
    second_error = second[mask] - target[mask]
    return {
        "n": n,
        "mae_difference_second_minus_first": float(
            np.abs(second_error).mean() - np.abs(first_error).mean()
        ),
        "rmse_difference_second_minus_first": float(
            np.sqrt(np.square(second_error).mean())
            - np.sqrt(np.square(first_error).mean())
        ),
        "second_better_fraction": float(
            (np.abs(second_error) < np.abs(first_error)).mean()
        ),
    }


def _estimate_parameters(windows, frozen, batch_size):
    parameters = []
    for start in range(0, len(windows.origins), batch_size):
        history = torch.from_numpy(windows.gru_history[start : start + batch_size])
        parameters.append(predict_parameters(frozen, history).cpu().numpy())
    return np.concatenate(parameters).astype("float32", copy=False)


def _evaluate_method(
    windows: EvaluationWindows,
    parameters: np.ndarray,
    method: str,
    weight_kg: float,
    substeps: int,
    batch_size: int,
):
    history_inputs, future_inputs = configuration_inputs(windows, method)
    count = len(windows.origins)
    predictions = np.full((count, FORECAST_STEPS), np.nan, dtype="float32")
    full_valid = np.zeros(count, dtype=bool)
    init_failed = np.zeros(count, dtype=bool)
    forecast_failed = np.zeros(count, dtype=bool)
    roundoff = np.zeros(count, dtype="int64")
    failure_rows = []
    for start in range(0, count, batch_size):
        stop = min(start + batch_size, count)
        glucose = torch.from_numpy(windows.initialization_cgm[start:stop])
        history = torch.from_numpy(history_inputs[start:stop])
        theta = torch.from_numpy(parameters[start:stop])
        initialized = initialize_state(glucose, history, theta, weight_kg, substeps)
        roundoff[start:stop] += np.asarray(initialized.validity.roundoff_corrections)
        init_valid = initialized.validity.valid_mask.cpu().numpy()
        init_failed[start:stop] = ~init_valid
        for failure in initialized.validity.failures:
            global_index = start + failure.candidate_index
            origin = windows.origins.iloc[global_index]
            failure_rows.append(
                {
                    "method": method,
                    "window_id": int(origin.window_id),
                    "dataset": origin.dataset,
                    "patient_id": origin.patient_id,
                    "split": origin.split,
                    "origin": origin.origin,
                    "phase": "initialization",
                    "first_failing_interval": failure.first_failing_interval,
                    "first_failing_substep": failure.first_failing_substep,
                    "reason": failure.reason,
                }
            )
        valid_local = np.flatnonzero(init_valid)
        if not len(valid_local):
            continue
        predicted = predict_from_state(
            initialized.state[torch.as_tensor(valid_local)],
            theta[torch.as_tensor(valid_local)],
            torch.from_numpy(future_inputs[start:stop][valid_local]),
            weight_kg,
            substeps,
        )
        predictions[start + valid_local] = predicted.glucose_mg_dl.cpu().numpy()
        roundoff[start + valid_local] += np.asarray(predicted.validity.roundoff_corrections)
        forecast_valid = predicted.validity.valid_mask.cpu().numpy()
        forecast_failed[start + valid_local] = ~forecast_valid
        full_valid[start + valid_local] = forecast_valid
        for failure in predicted.validity.failures:
            local_index = valid_local[failure.candidate_index]
            global_index = start + local_index
            origin = windows.origins.iloc[global_index]
            failure_rows.append(
                {
                    "method": method,
                    "window_id": int(origin.window_id),
                    "dataset": origin.dataset,
                    "patient_id": origin.patient_id,
                    "split": origin.split,
                    "origin": origin.origin,
                    "phase": "forecast",
                    "first_failing_interval": failure.first_failing_interval,
                    "first_failing_substep": failure.first_failing_substep,
                    "reason": failure.reason,
                }
            )
    return {
        "predictions": predictions,
        "full_valid": full_valid,
        "initialization_failed": init_failed,
        "forecast_failed": forecast_failed,
        "roundoff_corrections": roundoff,
        "failures": failure_rows,
    }


def _original_agreement(windows, parameters, evaluated, weight_kg, substeps, batch_size):
    stateful = evaluated["A_original_convention"]["predictions"]
    original_predictions = np.full_like(stateful, np.nan)
    for start in range(0, len(windows.origins), batch_size):
        stop = min(start + batch_size, len(windows.origins))
        history = torch.from_numpy(windows.gru_history[start:stop, -73:])
        future = torch.from_numpy(windows.future_announced_inputs[start:stop])
        theta = torch.from_numpy(parameters[start:stop])
        original_predictions[start:stop] = original.simulate(
            history, future, theta, weight_kg, substeps
        ).detach().cpu().numpy()
    both = np.isfinite(stateful) & np.isfinite(original_predictions)
    dev = windows.origins["split"].eq("development").to_numpy()
    representative = np.flatnonzero(
        dev & evaluated["A_original_convention"]["full_valid"]
        & np.isfinite(original_predictions).all(axis=1)
    )[:32]
    representative_difference = (
        float(np.max(np.abs(stateful[representative] - original_predictions[representative])))
        if len(representative) else None
    )
    strict_failure_original_finite = int(
        ((~evaluated["A_original_convention"]["full_valid"])
         & np.isfinite(original_predictions).all(axis=1)).sum()
    )
    return {
        "all_matching_finite_points": int(both.sum()),
        "all_matching_finite_max_abs_difference_mg_dl": (
            float(np.max(np.abs(stateful[both] - original_predictions[both]))) if both.any() else None
        ),
        "representative_rule": "first 32 development windows fully valid in both implementations",
        "representative_windows": int(len(representative)),
        "representative_max_abs_difference_mg_dl": representative_difference,
        "stateful_strict_failures_with_finite_original_trajectory": strict_failure_original_finite,
    }


def _build_metrics(windows, evaluated):
    origins = windows.origins
    targets = windows.targets
    horizon_rows = []
    patient_rows = []
    window_rows = []
    for method in METHODS:
        prediction = evaluated[method]["predictions"]
        status = evaluated[method]
        for index, origin in origins.iterrows():
            first24 = _metric(prediction[index, :24], targets[index, :24])
            full48 = _metric(prediction[index], targets[index])
            window_rows.append(
                {
                    "window_id": int(origin.window_id),
                    "dataset": origin.dataset,
                    "patient_id": origin.patient_id,
                    "split": origin.split,
                    "origin": origin.origin,
                    "method": method,
                    "initialization_failed": bool(status["initialization_failed"][index]),
                    "forecast_failed": bool(status["forecast_failed"][index]),
                    "fully_valid_240min": bool(status["full_valid"][index]),
                    "available_points_120min": first24["n"],
                    "available_points_240min": full48["n"],
                    "mae_120min": first24["mae_mg_dl"],
                    "rmse_120min": first24["rmse_mg_dl"],
                    "mean_signed_error_120min": first24["mean_signed_error_mg_dl"],
                    "mae_240min": full48["mae_mg_dl"],
                    "rmse_240min": full48["rmse_mg_dl"],
                    "mean_signed_error_240min": full48["mean_signed_error_mg_dl"],
                    "roundoff_corrections": int(status["roundoff_corrections"][index]),
                }
            )
        for split in ("development", "validation"):
            split_mask = origins["split"].eq(split).to_numpy()
            for horizon_index in range(FORECAST_STEPS):
                metrics = _metric(
                    prediction[split_mask, horizon_index], targets[split_mask, horizon_index]
                )
                horizon_rows.append(
                    {"split": split, "method": method,
                     "horizon_min": (horizon_index + 1) * 5, **metrics}
                )
        for (dataset, patient_id, split), indexes in origins.groupby(
            ["dataset", "patient_id", "split"], sort=True
        ).groups.items():
            indexes = np.asarray(list(indexes), dtype=int)
            row = {
                "dataset": dataset,
                "patient_id": patient_id,
                "split": split,
                "method": method,
                "attempted_windows": len(indexes),
                "fully_valid_windows": int(status["full_valid"][indexes].sum()),
            }
            for minutes, width in ((120, 24), (240, 48)):
                values = _metric(prediction[indexes, :width], targets[indexes, :width])
                for key, value in values.items():
                    row[f"trajectory_{minutes}_{key}"] = value
            for minute in ENDPOINTS:
                endpoint = minute // 5 - 1
                values = _metric(prediction[indexes, endpoint], targets[indexes, endpoint])
                row[f"endpoint_{minute}_n"] = values["n"]
                row[f"endpoint_{minute}_mae_mg_dl"] = values["mae_mg_dl"]
                row[f"endpoint_{minute}_rmse_mg_dl"] = values["rmse_mg_dl"]
            patient_rows.append(row)
    return pd.DataFrame(horizon_rows), pd.DataFrame(patient_rows), pd.DataFrame(window_rows)


def _method_summary(windows, evaluated, patient_metrics):
    summary = {}
    for split in ("development", "validation"):
        split_mask = windows.origins["split"].eq(split).to_numpy()
        split_summary = {}
        for method in METHODS:
            status = evaluated[method]
            prediction = status["predictions"]
            method_summary = {
                "attempted_windows": int(split_mask.sum()),
                "initialization_failures": int((status["initialization_failed"] & split_mask).sum()),
                "forecast_failures": int((status["forecast_failed"] & split_mask).sum()),
                "fully_valid_240min_windows": int((status["full_valid"] & split_mask).sum()),
                "fully_valid_240min_rate": float(status["full_valid"][split_mask].mean()),
                "roundoff_corrections": int(status["roundoff_corrections"][split_mask].sum()),
                "trajectory_5_to_120_min": _metric(
                    prediction[split_mask, :24], windows.targets[split_mask, :24]
                ),
                "trajectory_5_to_240_min": _metric(
                    prediction[split_mask], windows.targets[split_mask]
                ),
                "endpoints": {},
                "available_prediction_counts_by_horizon": {},
            }
            for minute in ENDPOINTS:
                index = minute // 5 - 1
                method_summary["endpoints"][str(minute)] = _metric(
                    prediction[split_mask, index], windows.targets[split_mask, index]
                )
            for index in range(FORECAST_STEPS):
                method_summary["available_prediction_counts_by_horizon"][str((index + 1) * 5)] = int(
                    np.isfinite(prediction[split_mask, index]).sum()
                )
            patients = patient_metrics[
                (patient_metrics["split"] == split) & (patient_metrics["method"] == method)
            ]
            method_summary["patient_average"] = {
                "trajectory_120_mae_mg_dl": float(patients["trajectory_120_mae_mg_dl"].mean()),
                "trajectory_240_mae_mg_dl": float(patients["trajectory_240_mae_mg_dl"].mean()),
            }
            split_summary[method] = method_summary
        summary[split] = split_summary
    return summary


def _paired_summaries(windows, evaluated):
    pairs = (
        ("A_original_convention", "B_future_consumption"),
        ("B_future_consumption", "C_intended_consumption"),
        ("A_original_convention", "C_intended_consumption"),
    )
    output = {}
    for split in ("development", "validation"):
        split_mask = windows.origins["split"].eq(split).to_numpy()
        output[split] = {}
        for first, second in pairs:
            name = f"{second}_minus_{first}"
            output[split][name] = {
                "trajectory_5_to_120_min": paired_error_difference(
                    evaluated[first]["predictions"][split_mask, :24],
                    evaluated[second]["predictions"][split_mask, :24],
                    windows.targets[split_mask, :24],
                ),
                "trajectory_5_to_240_min": paired_error_difference(
                    evaluated[first]["predictions"][split_mask],
                    evaluated[second]["predictions"][split_mask],
                    windows.targets[split_mask],
                ),
                "endpoints": {
                    str(minute): paired_error_difference(
                        evaluated[first]["predictions"][split_mask, minute // 5 - 1],
                        evaluated[second]["predictions"][split_mask, minute // 5 - 1],
                        windows.targets[split_mask, minute // 5 - 1],
                    )
                    for minute in ENDPOINTS
                },
            }
    return output


def _shared_valid_summary(windows, evaluated):
    shared = np.logical_and.reduce([evaluated[name]["full_valid"] for name in PHYSIOLOGY_METHODS])
    output = {"overall_shared_windows": int(shared.sum()), "splits": {}}
    for split in ("development", "validation"):
        mask = shared & windows.origins["split"].eq(split).to_numpy()
        output["splits"][split] = {
            "windows": int(mask.sum()),
            "methods": {
                method: {
                    "trajectory_5_to_120_min": _metric(
                        evaluated[method]["predictions"][mask, :24], windows.targets[mask, :24]
                    ),
                    "trajectory_5_to_240_min": _metric(
                        evaluated[method]["predictions"][mask], windows.targets[mask]
                    ),
                }
                for method in PHYSIOLOGY_METHODS
            },
        }
    return output


def _evidence_conclusions(summary, patient_metrics):
    conclusions = {}
    for split in ("development", "validation"):
        methods = summary["results_by_split"][split]
        pairs = summary["paired_differences_on_matching_observations"][split]
        patient = patient_metrics[patient_metrics["split"] == split]
        pivot = patient.pivot(
            index=["dataset", "patient_id"], columns="method",
            values="trajectory_240_mae_mg_dl",
        )
        future_delta = pivot["B_future_consumption"] - pivot["A_original_convention"]
        initialization_delta = pivot["C_intended_consumption"] - pivot["B_future_consumption"]
        intended_delta = pivot["C_intended_consumption"] - pivot["A_original_convention"]

        def patient_extreme(series, kind):
            key = series.idxmax() if kind == "max" else series.idxmin()
            return {
                "dataset": str(key[0]), "patient_id": str(key[1]),
                "mae_difference_mg_dl": float(series.loc[key]),
            }

        conclusions[split] = {
            "future_consumption_timing_effect_B_minus_A": {
                "trajectory_120_mae_difference_mg_dl": pairs[
                    "B_future_consumption_minus_A_original_convention"
                ]["trajectory_5_to_120_min"]["mae_difference_second_minus_first"],
                "trajectory_240_mae_difference_mg_dl": pairs[
                    "B_future_consumption_minus_A_original_convention"
                ]["trajectory_5_to_240_min"]["mae_difference_second_minus_first"],
            },
            "consumed_initialization_effect_C_minus_B": {
                "trajectory_120_mae_difference_mg_dl": pairs[
                    "C_intended_consumption_minus_B_future_consumption"
                ]["trajectory_5_to_120_min"]["mae_difference_second_minus_first"],
                "trajectory_240_mae_difference_mg_dl": pairs[
                    "C_intended_consumption_minus_B_future_consumption"
                ]["trajectory_5_to_240_min"]["mae_difference_second_minus_first"],
            },
            "net_intended_effect_C_minus_A": {
                "trajectory_120_mae_difference_mg_dl": pairs[
                    "C_intended_consumption_minus_A_original_convention"
                ]["trajectory_5_to_120_min"]["mae_difference_second_minus_first"],
                "trajectory_240_mae_difference_mg_dl": pairs[
                    "C_intended_consumption_minus_A_original_convention"
                ]["trajectory_5_to_240_min"]["mae_difference_second_minus_first"],
            },
            "two_to_four_hour_deterioration": {
                method: {
                    "trajectory_mae_240_minus_120_mg_dl": float(
                        values["trajectory_5_to_240_min"]["mae_mg_dl"]
                        - values["trajectory_5_to_120_min"]["mae_mg_dl"]
                    ),
                    "endpoint_mae_240_minus_120_mg_dl": float(
                        values["endpoints"]["240"]["mae_mg_dl"]
                        - values["endpoints"]["120"]["mae_mg_dl"]
                    ),
                }
                for method, values in methods.items()
            },
            "patient_heterogeneity": {
                "patients": int(len(pivot)),
                "patients_B_better_than_A": int((future_delta < 0).sum()),
                "patients_C_better_than_B": int((initialization_delta < 0).sum()),
                "patients_C_better_than_A": int((intended_delta < 0).sum()),
                "largest_C_minus_A_worsening": patient_extreme(intended_delta, "max"),
                "largest_C_minus_A_improvement": patient_extreme(intended_delta, "min"),
            },
        }
    conclusions["failures"] = {
        "reason_groups": len(summary["failure_reason_counts"]),
        "failed_windows": int(sum(item["count"] for item in summary["failure_reason_counts"])),
        "interpretation": (
            "No initialization or forecast failures occurred in the full run."
            if not summary["failure_reason_counts"] else
            "See failure_reason_counts and failures.csv for affected patients and situations."
        ),
    }
    conclusions["limitations_before_bolus_optimization"] = [
        "Recorded future basal, boluses and carbohydrate events were supplied; this is not unknown-future forecasting.",
        "No changed doses or counterfactual bolus recommendations were evaluated.",
        "The GRU remains trained on historical announced carbohydrates, not consumed carbohydrates.",
        "The checkpoint/dataset hash discrepancy remains unresolved.",
        "Five-minute aggregated events retain the interval-start timing assumption.",
        "All patients use the common checkpoint weight fallback unless separately known.",
        "Testing patients were intentionally untouched; results do not estimate held-out optimizer performance.",
        "Four-hour errors are materially larger than two-hour errors and must be included in safety design.",
    ]
    return conclusions


def _largest_errors(windows, evaluated, limit=20):
    examples = []
    for method in METHODS:
        prediction = evaluated[method]["predictions"]
        error = np.abs(prediction - windows.targets)
        finite = np.isfinite(error)
        candidates = np.argwhere(finite)
        if not len(candidates):
            continue
        values = error[finite]
        order = np.argsort(-values, kind="stable")[:limit]
        for rank in order:
            window_index, horizon_index = candidates[rank]
            origin = windows.origins.iloc[window_index]
            examples.append(
                {
                    "method": method,
                    "window_id": int(origin.window_id),
                    "dataset": origin.dataset,
                    "patient_id": origin.patient_id,
                    "split": origin.split,
                    "origin": str(origin.origin),
                    "horizon_min": int((horizon_index + 1) * 5),
                    "observed_mg_dl": float(windows.targets[window_index, horizon_index]),
                    "predicted_mg_dl": float(prediction[window_index, horizon_index]),
                    "absolute_error_mg_dl": float(error[window_index, horizon_index]),
                }
            )
    return sorted(examples, key=lambda row: (-row["absolute_error_mg_dl"], row["method"]))[:limit]


def _write_predictions(path, windows, evaluated, chunk_size=2000):
    writer = None
    horizons = np.arange(1, FORECAST_STEPS + 1, dtype="int16") * 5
    try:
        for method in METHODS:
            prediction = evaluated[method]["predictions"]
            for start in range(0, len(windows.origins), chunk_size):
                stop = min(start + chunk_size, len(windows.origins))
                origin = windows.origins.iloc[start:stop]
                rows = stop - start
                frame = pd.DataFrame(
                    {
                        "window_id": np.repeat(origin["window_id"].to_numpy("int64"), FORECAST_STEPS),
                        "dataset": np.repeat(origin["dataset"].to_numpy(), FORECAST_STEPS),
                        "patient_id": np.repeat(origin["patient_id"].to_numpy(), FORECAST_STEPS),
                        "split": np.repeat(origin["split"].to_numpy(), FORECAST_STEPS),
                        "origin": np.repeat(origin["origin"].to_numpy(), FORECAST_STEPS),
                        "horizon_min": np.tile(horizons, rows),
                        "observed_mg_dl": windows.targets[start:stop].reshape(-1),
                        "predicted_mg_dl": prediction[start:stop].reshape(-1),
                        "method": method,
                        "fully_valid_240min": np.repeat(
                            evaluated[method]["full_valid"][start:stop], FORECAST_STEPS
                        ),
                    }
                )
                table = pa.Table.from_pandas(frame, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(path, table.schema, compression="zstd")
                writer.write_table(table)
    finally:
        if writer is not None:
            writer.close()


def _make_plots(out, windows, evaluated, horizon_metrics, patient_metrics, failures, largest):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = dict(zip(METHODS, ("#1f77b4", "#ff7f0e", "#2ca02c", "#777777")))
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for axis, split in zip(axes, ("development", "validation")):
        for method in METHODS:
            rows = horizon_metrics[(horizon_metrics.split == split) & (horizon_metrics.method == method)]
            axis.plot(rows.horizon_min, rows.mae_mg_dl, label=method, color=colors[method])
        axis.set(title=split, xlabel="Horizon (minutes)", ylabel="MAE (mg/dL)")
        axis.grid(alpha=0.25)
    axes[1].legend(fontsize=8)
    fig.suptitle("MAE versus horizon on identical four-hour origins")
    fig.tight_layout()
    fig.savefig(out / "mae_vs_horizon.png", dpi=160)
    plt.close(fig)

    patients = patient_metrics[patient_metrics.method.isin(PHYSIOLOGY_METHODS)].copy()
    patients["label"] = patients["split"] + ":" + patients["patient_id"]
    labels = sorted(patients.label.unique())
    fig, axes = plt.subplots(2, 1, figsize=(15, 9), sharex=True)
    for axis, minutes in zip(axes, (120, 240)):
        for method in PHYSIOLOGY_METHODS:
            rows = patients[patients.method == method].set_index("label").reindex(labels)
            axis.plot(range(len(labels)), rows[f"trajectory_{minutes}_mae_mg_dl"],
                      marker="o", markersize=3, label=method, color=colors[method])
        axis.set(ylabel=f"{minutes}-min trajectory MAE", title=f"Per-patient {minutes}-minute comparison")
        axis.grid(alpha=0.25)
    axes[-1].set_xticks(range(len(labels)), labels, rotation=90, fontsize=7)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "per_patient_120_240_comparison.png", dpi=160)
    plt.close(fig)

    validation = windows.origins[windows.origins.split == "validation"]
    representative_index = int(
        validation.sort_values(
            ["future_announced_carbs_g", "dataset", "patient_id", "origin"],
            ascending=[False, True, True, True], kind="stable"
        ).index[0]
    )
    representative = windows.origins.iloc[representative_index]
    horizon = np.arange(1, FORECAST_STEPS + 1) * 5
    fig, axis = plt.subplots(figsize=(11, 5))
    axis.plot(horizon, windows.targets[representative_index], color="black", linewidth=2, label="observed")
    for method in METHODS:
        axis.plot(horizon, evaluated[method]["predictions"][representative_index],
                  label=method, color=colors[method])
    axis.set(title=(f"Deterministic meal example: {representative.patient_id}, {representative.origin}; "
                    f"future announced={representative.future_announced_carbs_g:.1f} g"),
             xlabel="Horizon (minutes)", ylabel="Glucose (mg/dL)")
    axis.grid(alpha=0.25); axis.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out / "representative_meal_trajectory.png", dpi=160); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    if largest:
        example = largest[0]
        index = int(example["window_id"])
        method = example["method"]
        axes[0].plot(horizon, windows.targets[index], color="black", label="observed")
        axes[0].plot(horizon, evaluated[method]["predictions"][index], color=colors[method], label=method)
        axes[0].set_title(f"Largest absolute error: {example['absolute_error_mg_dl']:.1f} mg/dL")
        axes[0].legend(fontsize=8)
    if len(failures):
        failure = failures.sort_values(["method", "window_id", "first_failing_interval"], kind="stable").iloc[0]
        index = int(failure.window_id); method = failure.method
        axes[1].plot(horizon, windows.targets[index], color="black", label="observed")
        axes[1].plot(horizon, evaluated[method]["predictions"][index], color=colors[method], label=method)
        axes[1].set_title(f"First failure: {failure.reason}")
        axes[1].legend(fontsize=8)
    else:
        axes[1].text(0.5, 0.5, "No failed windows", ha="center", va="center")
        axes[1].set_title("Failure example")
    for axis in axes:
        axis.set(xlabel="Horizon (minutes)", ylabel="Glucose (mg/dL)")
        axis.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(out / "largest_error_and_failure_examples.png", dpi=160); plt.close(fig)
    return {
        "representative_meal_window_rule": (
            "validation window with greatest four-hour announced-carbohydrate total; "
            "ties by dataset, patient, origin"
        ),
        "representative_meal_window_id": representative_index,
        "largest_error_rule": "largest finite absolute point error; deterministic stable ordering",
        "failure_example_rule": "first row sorted by method, window_id, failing interval",
    }


def _summary_markdown(summary):
    lines = [
        "# Step 4 — Carbohydrate convention and four-hour replay diagnostic",
        "",
        f"Overall result: **{'PASS' if summary['overall_pass'] else 'FAIL'}**",
        "",
        "This is a recorded-action replay diagnostic. Future recorded basal, boluses and carbohydrate events are supplied intentionally. It is not an unknown-future-meal forecast and does not evaluate changed doses.",
        "",
    ]
    for split in ("development", "validation"):
        lines.extend([f"## {split.title()}", "", "| Method | Valid windows | MAE 5–120 | MAE 5–240 | 240-min endpoint MAE |", "|---|---:|---:|---:|---:|"])
        for method in METHODS:
            row = summary["results_by_split"][split][method]
            lines.append(
                f"| {method} | {row['fully_valid_240min_windows']}/{row['attempted_windows']} | "
                f"{row['trajectory_5_to_120_min']['mae_mg_dl']:.3f} | "
                f"{row['trajectory_5_to_240_min']['mae_mg_dl']:.3f} | "
                f"{row['endpoints']['240']['mae_mg_dl']:.3f} |"
            )
        lines.append("")
    lines.extend(["## Evidence for the Step 4 questions", ""])
    for split in ("development", "validation"):
        evidence = summary["evidence_conclusions"][split]
        timing = evidence["future_consumption_timing_effect_B_minus_A"]
        initialization = evidence["consumed_initialization_effect_C_minus_B"]
        net = evidence["net_intended_effect_C_minus_A"]
        deterioration = evidence["two_to_four_hour_deterioration"]["C_intended_consumption"]
        heterogeneity = evidence["patient_heterogeneity"]
        lines.extend([
            f"### {split.title()}", "",
            f"- Future consumption timing (B−A) changed trajectory MAE by {timing['trajectory_120_mae_difference_mg_dl']:+.3f} mg/dL at 120 minutes and {timing['trajectory_240_mae_difference_mg_dl']:+.3f} mg/dL over four hours.",
            f"- Consumed-carbohydrate initialization (C−B) changed trajectory MAE by {initialization['trajectory_120_mae_difference_mg_dl']:+.3f} mg/dL at 120 minutes and {initialization['trajectory_240_mae_difference_mg_dl']:+.3f} mg/dL over four hours.",
            f"- Net intended convention (C−A) changed four-hour trajectory MAE by {net['trajectory_240_mae_difference_mg_dl']:+.3f} mg/dL.",
            f"- Intended-convention trajectory MAE increased by {deterioration['trajectory_mae_240_minus_120_mg_dl']:.3f} mg/dL from the 120-minute to 240-minute aggregation.",
            f"- C improved over A for {heterogeneity['patients_C_better_than_A']}/{heterogeneity['patients']} patients; pooled change is not universal.",
            "",
        ])
    lines.extend([
        "## Failures and limitations", "",
        summary["evidence_conclusions"]["failures"]["interpretation"], "",
    ])
    for limitation in summary["evidence_conclusions"]["limitations_before_bolus_optimization"]:
        lines.append(f"- {limitation}")
    lines.append("")
    lines.extend([
        "## Interpretation constraints", "",
        "Pooled improvements need not hold for every patient; see `patient_metrics.csv`. Accuracy and failure rates are reported together, and shared-valid comparisons restrict A/B/C to the same fully valid windows. The unresolved checkpoint/dataset hash discrepancy remains documented. Passing this diagnostic does not make the simulator ready for bolus optimization.",
    ])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data")
    parser.add_argument("--checkpoint", default="baseline/model.pt")
    parser.add_argument("--out", default="results/bolus_optimization_migrated_final/step4_assumptions")
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--max-windows-per-patient", type=int, default=0,
                        help="0 evaluates every eligible origin; positive values are smoke runs")
    args = parser.parse_args()
    if args.batch_size <= 0 or args.threads <= 0 or args.max_windows_per_patient < 0:
        parser.error("batch size/threads must be positive and window cap nonnegative")
    torch.set_num_threads(args.threads)
    data_path = Path(args.data)
    checkpoint_path = Path(args.checkpoint)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    data, patient_splits, loader_audit = read_optimization_data(data_path)
    frozen = load_frozen_gru(checkpoint_path, expected_sha256=FROZEN_CHECKPOINT_SHA256)
    checkpoint = frozen.checkpoint
    if patient_splits != checkpoint["patient_splits"]:
        raise ValueError("Patient splits differ from the frozen checkpoint")
    windows = build_evaluation_windows(
        data, max_windows_per_patient=args.max_windows_per_patient
    )
    if (windows.origins["split"] == "testing").any():
        raise RuntimeError("Testing patient entered evaluation")
    windows.origins.to_csv(out / "evaluation_origins.csv", index=False)

    config = {
        "run_scope": "full_all_eligible_windows" if args.max_windows_per_patient == 0 else "limited_smoke_run",
        "arguments": vars(args),
        "dataset_sha256": sha256(data_path),
        "checkpoint_sha256": sha256(checkpoint_path),
        "checkpoint_dataset_sha256": checkpoint["data_sha256"],
        "checkpoint_dataset_hash_discrepancy": "unresolved",
        "loader_audit": loader_audit,
        "splits": ["development", "validation"],
        "testing_patients_excluded": True,
        "evaluated_origin_count": int(len(windows.origins)),
        "evaluated_origins_by_split": {
            str(k): int(v) for k, v in windows.origins["split"].value_counts().items()
        },
        "origin_stride_minutes": 240,
        "history_steps_for_gru": HISTORY_STEPS,
        "initialization_boundary_observations": 73,
        "initialization_intervals": 72,
        "forecast_intervals": FORECAST_STEPS,
        "weight_kg": checkpoint["config"]["weight_kg"],
        "substeps": checkpoint["config"]["substeps"],
        "future_input_knowledge": "recorded-action replay with known recorded future actions",
        "methods": {
            "A_original_convention": {"history_carbs": "carbs_g", "future_carbs": "carbs_g"},
            "B_future_consumption": {"history_carbs": "carbs_g", "future_carbs": "consumed_carbs_g"},
            "C_intended_consumption": {"history_carbs": "consumed_carbs_g", "future_carbs": "consumed_carbs_g"},
            "persistence": {"prediction": "origin CGM at every horizon"},
        },
        "software": {
            "python": platform.python_version(), "torch": torch.__version__,
            "pandas": pd.__version__, "numpy": np.__version__,
            "pyarrow": pa.__version__,
            "matplotlib": importlib.metadata.version("matplotlib"),
        },
        "source_hashes": {name: sha256(name) for name in EXPECTED_SOURCE_HASHES},
    }
    (out / "evaluation_config.json").write_text(json.dumps(config, indent=2, default=str) + "\n")

    parameters = _estimate_parameters(windows, frozen, args.batch_size)
    evaluated = {}
    for method in PHYSIOLOGY_METHODS:
        evaluated[method] = _evaluate_method(
            windows, parameters, method, config["weight_kg"], config["substeps"], args.batch_size
        )
    persistence = np.repeat(windows.origins["current_glucose_mg_dl"].to_numpy("float32")[:, None], FORECAST_STEPS, axis=1)
    count = len(windows.origins)
    evaluated["persistence"] = {
        "predictions": persistence,
        "full_valid": np.ones(count, dtype=bool),
        "initialization_failed": np.zeros(count, dtype=bool),
        "forecast_failed": np.zeros(count, dtype=bool),
        "roundoff_corrections": np.zeros(count, dtype="int64"),
        "failures": [],
    }

    agreement = _original_agreement(
        windows, parameters, evaluated, config["weight_kg"], config["substeps"], args.batch_size
    )
    horizon_metrics, patient_metrics, window_metrics = _build_metrics(windows, evaluated)
    failures = pd.DataFrame(
        [row for method in PHYSIOLOGY_METHODS for row in evaluated[method]["failures"]],
        columns=["method", "window_id", "dataset", "patient_id", "split", "origin", "phase",
                 "first_failing_interval", "first_failing_substep", "reason"],
    )
    horizon_metrics.to_csv(out / "horizon_metrics.csv", index=False)
    patient_metrics.to_csv(out / "patient_metrics.csv", index=False)
    window_metrics.to_csv(out / "window_metrics.csv", index=False)
    failures.to_csv(out / "failures.csv", index=False)
    _write_predictions(out / "predictions.parquet", windows, evaluated)

    largest = _largest_errors(windows, evaluated)
    plot_rules = _make_plots(out, windows, evaluated, horizon_metrics, patient_metrics, failures, largest)
    failure_reasons = (
        failures.groupby(["method", "phase", "reason"]).size().rename("count").reset_index().to_dict("records")
        if len(failures) else []
    )
    summary = {
        "scope": config["run_scope"],
        "recorded_action_replay_diagnostic": True,
        "unknown_future_meal_forecast": False,
        "changed_dose_effectiveness_evaluation": False,
        "attempted_windows": int(count),
        "windows_by_split": {str(k): int(v) for k, v in windows.origins["split"].value_counts().items()},
        "results_by_split": _method_summary(windows, evaluated, patient_metrics),
        "paired_differences_on_matching_observations": _paired_summaries(windows, evaluated),
        "shared_fully_valid_A_B_C": _shared_valid_summary(windows, evaluated),
        "original_solver_A_agreement": agreement,
        "failure_reason_counts": failure_reasons,
        "negative_state_failures": int(failures["reason"].str.contains("negative_state", na=False).sum()) if len(failures) else 0,
        "nonfinite_state_or_integration_failures": int(failures["reason"].str.contains("nonfinite", na=False).sum()) if len(failures) else 0,
        "largest_error_examples": largest,
        "plot_selection_rules": plot_rules,
        "patient_average_warning": "A lower pooled error does not imply improvement for every patient.",
        "checkpoint_dataset_hash_discrepancy": "unresolved",
        "preservation": {
            "checkpoint_sha256_matches": sha256(checkpoint_path) == FROZEN_CHECKPOINT_SHA256,
            "source_files_match": {
                name: sha256(name) == expected for name, expected in EXPECTED_SOURCE_HASHES.items()
            },
            "gru_retrained_or_scalers_refit": False,
        },
    }
    summary["evidence_conclusions"] = _evidence_conclusions(summary, patient_metrics)
    summary["overall_pass"] = bool(
        summary["preservation"]["checkpoint_sha256_matches"]
        and all(summary["preservation"]["source_files_match"].values())
        and config["testing_patients_excluded"]
        and agreement["representative_max_abs_difference_mg_dl"] is not None
        and agreement["representative_max_abs_difference_mg_dl"] <= 3e-5
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    (out / "summary.md").write_text(_summary_markdown(summary))
    print(out / "summary.json")
    if not summary["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
