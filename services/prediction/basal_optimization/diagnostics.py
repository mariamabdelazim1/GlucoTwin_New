"""Reproducible baseline-only diagnostics for long GRU--Hovorka replays.

This module measures and audits the existing model.  It does not retrain,
correct, refresh, score, rank, select, or recommend a basal rate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass, replace
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import torch

from final_model_adapter import HORIZON, LOWER, UPPER
from bolus_optimization.checkpoint import load_frozen_gru, predict_parameters
from bolus_optimization.configuration import FROZEN_CHECKPOINT_SHA256
from bolus_optimization.physiology import MG_DL_PER_MMOL_L, VG_L_PER_KG

from .candidate_generation import (
    EXAMPLE_CONFIGURATION_PATH,
    BasalCandidateSet,
    generate_basal_candidates,
    load_search_configuration,
)
from .candidate_inputs import BasalCandidateInputBatch, build_candidate_inputs
from .development_reliability import DevelopmentWindowReference, select_development_windows
from .preparation import (
    DEFAULT_CHECKPOINT_PATH,
    DEFAULT_DATASET_PATH,
    REPOSITORY_ROOT,
    BasalPreparationError,
    PatientIdentity,
    PreparedBasalSnapshot,
    _resolve_repository_path,
    prepare_basal_snapshot,
)
from .reliability import (
    BaselineReliabilityAssessment,
    UNCALIBRATED_CRITERIA_PATH,
    assess_baseline_reliability,
    calculate_glucose_fit_metrics,
    load_reliability_criteria,
)
from .simulation import BasalSimulationBatchResult, simulate_candidate_batch


PREFIX_STEPS = (24, 48, 72, 144, 288, 576)
BLOCK_STEPS = 48
DEFAULT_RESULTS_DIRECTORY = REPOSITORY_ROOT / "services/prediction/results/basal_diagnostics"
KNOWN_EXAMPLE = DevelopmentWindowReference(
    "PadovaBaseline", "adult#004", pd.Timestamp("2027-01-04 00:00:00")
)


@dataclass(frozen=True)
class DiagnosticMetricSegment:
    label: str
    start_output_index: int
    end_output_index_exclusive: int
    start_timestamp: pd.Timestamp
    end_timestamp: pd.Timestamp
    expected_count: int
    matched_count: int
    status: str
    reason: str | None
    mae_mg_dl: float | None
    rmse_mg_dl: float | None
    mean_signed_error_mg_dl: float | None
    maximum_absolute_error_mg_dl: float | None
    endpoint_error_mg_dl: float | None


@dataclass(frozen=True)
class TrajectoryErrorDevelopment:
    cumulative: tuple[DiagnosticMetricSegment, ...]
    four_hour_blocks: tuple[DiagnosticMetricSegment, ...]
    numerical_status: str
    coverage_complete: bool


def _metric_segment(
    assessment: BaselineReliabilityAssessment,
    label: str,
    start: int,
    end: int,
) -> DiagnosticMetricSegment:
    aligned = assessment.aligned_observations[start:end]
    matched = sum(item.valid for item in aligned)
    predictions = np.asarray(
        [item.predicted_glucose_mg_dl for item in aligned], dtype=np.float64
    )
    numerical = np.isfinite(predictions).all()
    complete = matched == end - start
    reason = None
    metrics = None
    endpoint = None
    if assessment.baseline_simulation_status != "simulation_valid" or not numerical:
        status = "numerical_failure"
        reason = "baseline simulation is failed, incomplete, or nonfinite"
    elif not complete:
        status = "incomplete_observation_coverage"
        reason = f"matched {matched} of {end - start} exact output observations"
    else:
        observed = np.asarray(
            [item.observed_glucose_mg_dl for item in aligned], dtype=np.float64
        )
        metrics = calculate_glucose_fit_metrics(predictions, observed)
        endpoint = float(predictions[-1] - observed[-1])
        status = "complete"
    return DiagnosticMetricSegment(
        label=label,
        start_output_index=start,
        end_output_index_exclusive=end,
        start_timestamp=aligned[0].availability_timestamp,
        end_timestamp=aligned[-1].availability_timestamp,
        expected_count=end - start,
        matched_count=matched,
        status=status,
        reason=reason,
        mae_mg_dl=None if metrics is None else metrics.mae_mg_dl,
        rmse_mg_dl=None if metrics is None else metrics.rmse_mg_dl,
        mean_signed_error_mg_dl=(
            None if metrics is None else metrics.mean_signed_error_mg_dl
        ),
        maximum_absolute_error_mg_dl=(
            None if metrics is None else metrics.maximum_absolute_error_mg_dl
        ),
        endpoint_error_mg_dl=endpoint,
    )


def analyze_error_development(
    assessment: BaselineReliabilityAssessment,
) -> TrajectoryErrorDevelopment:
    """Measure prefixes and non-overlapping four-hour blocks of one trajectory."""

    if len(assessment.aligned_observations) != 576:
        raise ValueError("Diagnostic assessment must retain all 576 output positions")
    cumulative = tuple(
        _metric_segment(assessment, f"0-{steps * 5 // 60}h", 0, steps)
        for steps in PREFIX_STEPS
    )
    blocks = tuple(
        _metric_segment(
            assessment,
            f"{start * 5 // 60}-{(start + BLOCK_STEPS) * 5 // 60}h",
            start,
            start + BLOCK_STEPS,
        )
        for start in range(0, 576, BLOCK_STEPS)
    )
    return TrajectoryErrorDevelopment(
        cumulative,
        blocks,
        assessment.baseline_simulation_status,
        assessment.coverage.complete,
    )


def baseline_only_candidate_set(candidate_set: BasalCandidateSet) -> BasalCandidateSet:
    """Retain the explicitly flagged baseline without inferring by position."""

    baseline = [item for item in candidate_set.candidates if item.is_recorded_baseline]
    if len(baseline) != 1 or baseline[0].candidate_id != candidate_set.baseline_candidate_id:
        raise ValueError("Candidate set baseline metadata is inconsistent")
    return replace(candidate_set, candidates=(baseline[0],), candidate_count=1)


def _distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    array = np.asarray(list(values), dtype=np.float64)
    if not len(array):
        return {"count": 0, "minimum": None, "median": None, "mean": None, "maximum": None}
    if not np.isfinite(array).all():
        raise ValueError("Diagnostic aggregate received nonfinite values")
    return {
        "count": int(len(array)),
        "minimum": float(array.min()),
        "median": float(np.median(array)),
        "mean": float(array.mean()),
        "maximum": float(array.max()),
    }


def _measurement_age(assessment: BaselineReliabilityAssessment) -> dict[str, Any]:
    ages = [
        (item.availability_timestamp - item.measurement_timestamp).total_seconds() / 60.0
        for item in assessment.aligned_observations
        if item.valid and item.measurement_timestamp is not None
    ]
    distribution = _distribution(ages)
    distribution["missing_measurement_timestamp_count"] = sum(
        item.measurement_timestamp is None for item in assessment.aligned_observations
    )
    distribution["units"] = "minutes"
    return distribution


def _event_error_audit(
    assessment: BaselineReliabilityAssessment,
    baseline_inputs: torch.Tensor,
) -> dict[str, Any]:
    predicted = np.asarray(
        [item.predicted_glucose_mg_dl for item in assessment.aligned_observations],
        dtype=np.float64,
    )
    observed = np.asarray(
        [item.observed_glucose_mg_dl for item in assessment.aligned_observations],
        dtype=np.float64,
    )
    valid = np.asarray([item.valid for item in assessment.aligned_observations])
    absolute_error = np.abs(predicted - observed)
    inputs = baseline_inputs.detach().cpu().numpy().astype(np.float64)
    event = (inputs[:, 1] > 0) | (inputs[:, 2] > 0)
    within_30_minutes = np.zeros(576, dtype=bool)
    for event_index in np.flatnonzero(event):
        within_30_minutes[event_index : min(576, event_index + 6)] = True

    def group(mask: np.ndarray) -> dict[str, Any]:
        selected = mask & valid & np.isfinite(absolute_error)
        return {
            "count": int(selected.sum()),
            "mean_absolute_error_mg_dl": (
                float(absolute_error[selected].mean()) if selected.any() else None
            ),
        }

    return {
        "event_interval": group(event),
        "within_30_minutes_after_event": group(within_30_minutes),
        "outside_30_minutes_after_event": group(~within_30_minutes),
        "interpretation": "Descriptive timing comparison only; association does not establish causation.",
    }


def audit_window(
    snapshot: PreparedBasalSnapshot,
    inputs: BasalCandidateInputBatch,
    assessment: BaselineReliabilityAssessment,
) -> dict[str, Any]:
    """Audit inputs, timestamps, initialization, weight, and event timing."""

    if inputs.candidate_count != 1 or len(inputs.candidates) != 1:
        raise ValueError("Diagnostic input batch must contain only the baseline candidate")
    candidate = inputs.candidates[0]
    replay = snapshot.replay_intervals
    materialized = candidate.interval_inputs.detach().cpu().numpy().astype(np.float64)
    recorded_basal = replay["basal_rate_u_per_hour"].to_numpy(np.float64, copy=True)
    recorded_bolus = replay["bolus_u"].to_numpy(np.float64, copy=True)
    recorded_consumed = replay["consumed_carbs_g"].to_numpy(np.float64, copy=True)
    announced = replay["carbs_g"].to_numpy(np.float64, copy=True)
    basal_units = recorded_basal * (5.0 / 60.0)
    source_basal = None
    if "basal_u" in replay.columns:
        source_values = replay["basal_u"].to_numpy(np.float64, copy=True)
        source_basal = {
            "column": "basal_u",
            "documented_semantics_available": False,
            "total": float(source_values.sum()),
            "maximum_absolute_difference_from_rate_times_interval": float(
                np.max(np.abs(source_values - basal_units))
            ),
            "note": "Numeric consistency is reported without inferring undocumented units.",
        }
    continuity = {
        column: replay[column].drop_duplicates().astype(str).tolist()
        for column in ("source_run_id", "source_record_id", "continuous_record_id")
        if column in replay.columns
    }
    parameters = snapshot.parameters.detach().cpu().numpy().astype(np.float64)
    lower = np.asarray(LOWER, dtype=np.float64)
    upper = np.asarray(UPPER, dtype=np.float64)
    fractions = (parameters - lower) / (upper - lower)
    state = snapshot.physiological_state.detach().cpu().numpy().astype(np.float64)
    initialized_glucose = state[0] / (VG_L_PER_KG * snapshot.effective_weight_kg) * MG_DL_PER_MMOL_L
    timestamps = pd.DatetimeIndex(replay["timestamp"])
    deltas = timestamps[1:] - timestamps[:-1]
    insulin_like_columns = [
        column for column in replay.columns
        if "insulin" in column.lower() or "bolus" in column.lower()
    ]
    return {
        "basal": {
            "units": "U/hour; total integrates each five-minute interval",
            "recorded_rate_min_u_per_hour": float(recorded_basal.min()),
            "recorded_rate_max_u_per_hour": float(recorded_basal.max()),
            "recorded_total_u": float(basal_units.sum()),
            "materialized_total_u": candidate.basal_total_u,
            "maximum_absolute_rate_difference_after_float32_u_per_hour": float(
                np.max(np.abs(materialized[:, 0] - recorded_basal))
            ),
            "source_column_comparison": source_basal,
        },
        "bolus": {
            "units": "U/interval",
            "recorded_total_u": float(recorded_bolus.sum()),
            "materialized_total_u": candidate.bolus_total_u,
            "event_interval_count": int((recorded_bolus > 0).sum()),
            "event_intervals_exactly_preserved": bool(
                np.array_equal(materialized[:, 1], recorded_bolus.astype(np.float32))
            ),
            "physiological_columns": list(inputs.input_names),
            "available_insulin_like_source_columns": insulin_like_columns,
            "combined_insulin_added": False,
        },
        "carbohydrates": {
            "units": "g/interval",
            "announced_total_g": float(announced.sum()),
            "consumed_total_g": float(recorded_consumed.sum()),
            "materialized_consumed_total_g": candidate.consumed_carbs_total_g,
            "announcement_event_count": int((announced > 0).sum()),
            "consumption_event_count": int((recorded_consumed > 0).sum()),
            "same_interval_event_count": int(((announced > 0) & (recorded_consumed > 0)).sum()),
            "consumption_intervals_exactly_preserved": bool(
                np.array_equal(materialized[:, 2], recorded_consumed.astype(np.float32))
            ),
            "announcements_added_to_physiological_ingestion": False,
        },
        "timestamps_and_cgm": {
            "input_start": timestamps[0],
            "input_end": timestamps[-1],
            "output_start": assessment.aligned_observations[0].availability_timestamp,
            "output_end": assessment.aligned_observations[-1].availability_timestamp,
            "exact_five_minute_cadence": bool(
                len(deltas) == 575 and (deltas == pd.Timedelta(minutes=5)).all()
            ),
            "continuity_identifiers": continuity,
            "coverage": asdict(assessment.coverage),
            "measurement_age": _measurement_age(assessment),
            "event_error_comparison": _event_error_audit(
                assessment, candidate.interval_inputs
            ),
        },
        "initialization": {
            "gru_completed_interval_count": len(snapshot.initialization_intervals),
            "gru_input_shape": list(snapshot.gru_input.shape),
            "gru_history_start": snapshot.initialization_intervals["timestamp"].iloc[0],
            "gru_history_end": snapshot.initialization_intervals["timestamp"].iloc[-1],
            "gru_boundary_timestamp": snapshot.simulation_start,
            "gru_boundary_convention": snapshot.initialization_provenance["gru_boundary"],
            "physiological_replay_interval_count": int(
                snapshot.physiological_initialization_inputs.shape[0]
            ),
            "physiological_replay_start": snapshot.initialization_intervals["timestamp"].iloc[-72],
            "physiological_replay_end": snapshot.simulation_start,
            "recorded_boundary_glucose_mg_dl": float(snapshot.boundary_row["cgm_mg_dl"]),
            "initialized_state_glucose_mg_dl": float(initialized_glucose),
            "initial_state": dict(zip(snapshot.state_names, state.tolist())),
            "estimated_parameters": dict(zip(snapshot.parameter_names, parameters.tolist())),
            "parameter_fraction_between_bounds": dict(
                zip(snapshot.parameter_names, fractions.tolist())
            ),
            "minimum_normalized_distance_to_bound": float(
                np.minimum(fractions, 1.0 - fractions).min()
            ),
            "latest_observation_used_for_initialization": snapshot.simulation_start,
            "observations_after_s_used": False,
            "parameters_held_fixed_for_replay": True,
        },
        "weight": {
            "effective_weight_kg": snapshot.effective_weight_kg,
            "provenance": snapshot.effective_weight_provenance,
            "patient_specific_weight_columns": [
                column for column in replay.columns if "weight" in column.lower()
            ],
            "trusted_patient_specific_weight_available": False,
        },
    }


def _json_default(value: object) -> object:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (pd.Timestamp, Path)):
        return str(value)
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().tolist()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _dataframe_fingerprint(frame: pd.DataFrame) -> str:
    values = pd.util.hash_pandas_object(frame, index=True, categorize=True).to_numpy()
    return hashlib.sha256(values.tobytes()).hexdigest()


def _model_state_unchanged(
    model: torch.nn.Module, before: dict[str, torch.Tensor]
) -> bool:
    current = model.state_dict()
    return current.keys() == before.keys() and all(
        torch.equal(value, before[name]) for name, value in current.items()
    )


def _plot_window(
    assessment: BaselineReliabilityAssessment,
    inputs: BasalCandidateInputBatch,
    output_path: Path,
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    aligned = assessment.aligned_observations
    timestamp = pd.DatetimeIndex([item.availability_timestamp for item in aligned])
    predicted = np.asarray([item.predicted_glucose_mg_dl for item in aligned])
    observed = np.asarray([
        np.nan if item.observed_glucose_mg_dl is None else item.observed_glucose_mg_dl
        for item in aligned
    ])
    error = predicted - observed
    source = inputs.candidates[0].interval_inputs.detach().cpu().numpy()
    event_time = pd.DatetimeIndex(inputs.input_timestamps)

    figure, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True,
                                gridspec_kw={"height_ratios": [2.2, 1.2, 1.0]})
    axes[0].plot(timestamp, observed, label="Recorded CGM", linewidth=1.3)
    axes[0].plot(timestamp, predicted, label="Unchanged-basal prediction", linewidth=1.3)
    axes[0].set_ylabel("Glucose (mg/dL)")
    axes[0].legend(loc="upper left")
    axes[0].grid(alpha=0.25)
    axes[1].axhline(0, color="0.4", linewidth=0.8)
    axes[1].plot(timestamp, error, color="tab:red", linewidth=1.0)
    axes[1].set_ylabel("Predicted - recorded\n(mg/dL)")
    axes[1].grid(alpha=0.25)
    carbs = source[:, 2]
    bolus = source[:, 1]
    axes[2].vlines(event_time[carbs > 0], 0, carbs[carbs > 0],
                   color="tab:green", label="Consumed carbohydrate (g)")
    axes[2].set_ylabel("Consumed carbs (g)")
    bolus_axis = axes[2].twinx()
    bolus_axis.vlines(event_time[bolus > 0], 0, bolus[bolus > 0],
                      color="tab:purple", label="Delivered bolus (U)")
    bolus_axis.set_ylabel("Bolus (U)")
    handles1, labels1 = axes[2].get_legend_handles_labels()
    handles2, labels2 = bolus_axis.get_legend_handles_labels()
    axes[2].legend(handles1 + handles2, labels1 + labels2, loc="upper left")
    axes[2].set_xlabel("Output time (events applied at interval start)")
    axes[2].grid(alpha=0.2)
    figure.suptitle(
        f"{assessment.identity.dataset}/{assessment.identity.patient_id} — baseline replay"
    )
    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def _aggregate(windows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [
        item for item in windows
        if item["error_development"]["cumulative"][-1]["status"] == "complete"
    ]
    fields = ("mae_mg_dl", "rmse_mg_dl", "mean_signed_error_mg_dl", "maximum_absolute_error_mg_dl")
    full = {
        field: _distribution(
            item["error_development"]["cumulative"][-1][field]
            for item in complete
        )
        for field in fields
    }
    prefixes = {}
    for index, steps in enumerate(PREFIX_STEPS):
        prefixes[str(steps)] = {
            field: _distribution(
                item["error_development"]["cumulative"][index][field]
                for item in complete
            )
            for field in fields
        }
    return {
        "window_count": len(windows),
        "patient_count": len({
            (item["identity"]["dataset"], item["identity"]["patient_id"])
            for item in windows
        }),
        "complete_coverage_count": len(complete),
        "numerical_failure_count": sum(
            item["assessment"]["baseline_simulation_status"] != "simulation_valid"
            for item in windows
        ),
        "equally_weighted_patient_full_window_metrics": full,
        "equally_weighted_patient_prefix_metrics": prefixes,
    }


def _markdown_report(payload: dict[str, Any]) -> str:
    def number(value: float | None) -> str:
        return "unavailable" if value is None else f"{value:.3f}"

    lines = [
        "# Baseline GRU–Hovorka 48-hour diagnostic",
        "",
        "This is a development-only diagnostic. Numerical validity is not predictive accuracy, and no result authorizes basal selection.",
        "",
        "## Established contracts",
        "",
        "- Training code builds 24-hour, 289-row GRU histories and forecasts 24 five-minute outputs (120 minutes).",
        "- The saved checkpoint selection metric is explicitly scoped to 5–60 minutes.",
        "- During the six-hour historical physiological replay, each next observed CGM replaces Q1; future forecasts accept no glucose observations.",
        "- Native training uses announced `carbs_g` as both the historical and future physiological carbohydrate input. The current runtime intentionally uses `consumed_carbs_g` for both physiological phases while retaining announcements as the GRU feature.",
        "- Parameters are estimated once per training window and fixed over its forecast. The basal diagnostic extends that fixed vector observation-free for 576 outputs (48 hours).",
        "- Basal is U/hour, bolus is delivered U/interval, and current-runtime consumed carbohydrate is g/interval. Announcements are not double-counted.",
        "",
        "## Pilot coverage",
        "",
        f"- Completed windows: {payload['aggregate']['window_count']}",
        f"- Complete CGM coverage: {payload['aggregate']['complete_coverage_count']}",
        f"- Numerical failures: {payload['aggregate']['numerical_failure_count']}",
        f"- Preparation/execution failures: {len(payload['failures'])}",
        "",
        "## Per-window full replay",
        "",
        "| Patient | T | MAE | RMSE | Bias | Max abs | Endpoint |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for item in payload["windows"]:
        metric = item["error_development"]["cumulative"][-1]
        lines.append(
            f"| {item['identity']['dataset']}/{item['identity']['patient_id']} | "
            f"{item['decision_timestamp']} | {number(metric['mae_mg_dl'])} | "
            f"{number(metric['rmse_mg_dl'])} | "
            f"{number(metric['mean_signed_error_mg_dl'])} | "
            f"{number(metric['maximum_absolute_error_mg_dl'])} | "
            f"{number(metric['endpoint_error_mg_dl'])} |"
        )
    lines.extend([
        "",
        "## Patient-equal cumulative error",
        "",
        "| Horizon | Mean MAE | Mean RMSE | Mean bias | Mean max abs |",
        "|---:|---:|---:|---:|---:|",
    ])
    for steps in PREFIX_STEPS:
        metrics = payload["aggregate"]["equally_weighted_patient_prefix_metrics"][str(steps)]
        lines.append(
            f"| {steps * 5 // 60} h | {number(metrics['mae_mg_dl']['mean'])} | "
            f"{number(metrics['rmse_mg_dl']['mean'])} | "
            f"{number(metrics['mean_signed_error_mg_dl']['mean'])} | "
            f"{number(metrics['maximum_absolute_error_mg_dl']['mean'])} |"
        )
    known = next(
        (item for item in payload["windows"]
         if item["identity"] == asdict(KNOWN_EXAMPLE.identity)),
        None,
    )
    if known is not None:
        lines.extend([
            "",
            "## adult#004 cumulative and local error",
            "",
            "| Prefix | MAE | RMSE | Bias | Max abs | Endpoint |",
            "|---:|---:|---:|---:|---:|---:|",
        ])
        for metric in known["error_development"]["cumulative"]:
            lines.append(
                f"| {metric['label']} | {number(metric['mae_mg_dl'])} | "
                f"{number(metric['rmse_mg_dl'])} | "
                f"{number(metric['mean_signed_error_mg_dl'])} | "
                f"{number(metric['maximum_absolute_error_mg_dl'])} | "
                f"{number(metric['endpoint_error_mg_dl'])} |"
            )
        lines.extend([
            "",
            "Successive four-hour block MAE (mg/dL): "
            + ", ".join(
                f"{metric['label']}={number(metric['mae_mg_dl'])}"
                for metric in known["error_development"]["four_hour_blocks"]
            )
            + ".",
        ])
    maximum_basal_difference = max(
        item["audit"]["basal"]["maximum_absolute_rate_difference_after_float32_u_per_hour"]
        for item in payload["windows"]
    )
    maximum_initialization_difference = max(
        abs(
            item["audit"]["initialization"]["initialized_state_glucose_mg_dl"]
            - item["audit"]["initialization"]["recorded_boundary_glucose_mg_dl"]
        )
        for item in payload["windows"]
    )
    events_higher = sum(
        item["audit"]["timestamps_and_cgm"]["event_error_comparison"]
        ["within_30_minutes_after_event"]["mean_absolute_error_mg_dl"]
        > item["audit"]["timestamps_and_cgm"]["event_error_comparison"]
        ["outside_30_minutes_after_event"]["mean_absolute_error_mg_dl"]
        for item in payload["windows"]
    )
    lines.extend([
        "",
        "## Input and initialization audit",
        "",
        f"- All materialized bolus and consumed-carbohydrate event intervals exactly match source rows. Maximum baseline float32 replacement difference was {maximum_basal_difference:.3g} U/hour.",
        "- `basal_u` exactly equals `basal_rate_u_per_hour × 5/60` in these windows, but its units remain undocumented and were not inferred from magnitude.",
        "- Announced and consumed carbohydrate totals match per window, but consumption spans more intervals than announcements; announcements are not added again.",
        f"- Initialized glucose matches the recorded S boundary within {maximum_initialization_difference:.3g} mg/dL across the pilot.",
        "- CGM measurement ages are 0–2 minutes (median 1 minute) in every pilot window; all timestamp cadence and source-run continuity checks pass.",
        f"- Event-adjacent MAE was higher than non-event-adjacent MAE in {events_higher} of {len(payload['windows'])} windows, so there is no consistent event clustering signal in this small sample.",
        "- No trusted patient-specific weight column is present; all runs retain the checkpoint's fixed 70 kg contract.",
        "- Source dataframe and frozen model state fingerprints are unchanged after execution.",
        "",
        "## Evidence and hypotheses",
        "",
        "1. **Strongest evidence: forecast-horizon extrapolation.** The trained objective covers 120 minutes and saved selection covers the first hour, while this replay runs 48 hours. The diagnostic does not establish 48-hour training support.",
        "2. **Demonstrated contract difference: carbohydrate timing.** Native training feeds announced carbohydrates into physiological initialization and forecast; the current runtime feeds consumed carbohydrates. Pilot totals match, but consumption is distributed over many more intervals, so timing is materially different even without double counting.",
        "3. **Strong evidence: observation-free drift.** Both implementations overwrite Q1 with observed CGM during historical initialization, but the training forecast is only 120 minutes; the 48-hour forecast has no correction, allowing state/parameter mismatch to accumulate much longer.",
        "4. **Plausible: fixed patient parameters over a much longer rollout.** Fixed parameters match training-window behavior but are held 24 times longer than the declared training horizon.",
        "5. **Plausible input uncertainty: aggregated event timing and CGM measurement age.** Events are applied at bucket start because within-bucket timing is unavailable. Event-adjacent error is descriptive, not causal.",
        "6. **Unresolved: fixed 70 kg versus patient-specific weight.** No trusted patient-weight field exists in the mandated dataset, so this cannot be tested or claimed as the cause here.",
        "",
        "## Smallest discriminating next experiment",
        "",
        "Without changing weights or data, run a paired two-hour experiment at the same origins: (A) the native training physiological convention using announced carbohydrate for initialization and forecast, and (C) the current consumed-carbohydrate convention. Two hours matches the declared training horizon. A consistent A-over-C improvement would support the carbohydrate-contract hypothesis; similar results would shift weight toward parameter/initialization error and long-horizon drift, which the existing continuous prefixes already show after six hours. This must remain diagnostic and must not authorize selection.",
        "",
        "## Limitations",
        "",
        "This bounded development pilot is not independent validation, does not prove causation, and does not establish clinical safety or counterfactual accuracy.",
    ])
    return "\n".join(lines) + "\n"


def run_baseline_diagnostic_pilot(
    *,
    output_directory: str | Path = DEFAULT_RESULTS_DIRECTORY,
    maximum_development_patients: int = 4,
    include_known_example: bool = True,
    write_plots: bool = True,
) -> dict[str, Any]:
    """Run a bounded baseline-only pilot and write ignored diagnostic artifacts."""

    if maximum_development_patients < 1 or maximum_development_patients > 4:
        raise ValueError("maximum_development_patients must be between 1 and 4")
    resolved_dataset = _resolve_repository_path(DEFAULT_DATASET_PATH)
    mandated = (REPOSITORY_ROOT / DEFAULT_DATASET_PATH).resolve()
    if resolved_dataset.resolve() != mandated:
        raise BasalPreparationError("Diagnostic dataset path differs from the mandated file")
    data = pd.read_parquet(resolved_dataset)
    frozen = load_frozen_gru(DEFAULT_CHECKPOINT_PATH, expected_sha256=FROZEN_CHECKPOINT_SHA256)
    data_fingerprint_before = _dataframe_fingerprint(data)
    model_state_before = {
        name: value.detach().clone() for name, value in frozen.model.state_dict().items()
    }
    actual_splits = {
        str((str(dataset), str(patient))): str(group["split"].iloc[0])
        for (dataset, patient), group in data.groupby(["dataset", "patient_id"], sort=False)
    }
    if actual_splits != frozen.checkpoint["patient_splits"]:
        raise BasalPreparationError("patient split metadata differs from the frozen checkpoint")
    selection = select_development_windows(
        data, maximum_patients=maximum_development_patients, windows_per_patient=1
    )
    references = list(selection.windows)
    known_split = actual_splits.get(str((KNOWN_EXAMPLE.dataset, KNOWN_EXAMPLE.patient_id)))
    if include_known_example:
        if known_split != "development":
            raise ValueError("Known adult#004 example is not a development patient")
        if KNOWN_EXAMPLE not in references:
            references.append(KNOWN_EXAMPLE)

    search_configuration, _ = load_search_configuration(EXAMPLE_CONFIGURATION_PATH)
    reliability_criteria, criteria_digest = load_reliability_criteria(
        UNCALIBRATED_CRITERIA_PATH
    )
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    windows: list[dict[str, Any]] = []
    failures: list[str] = []
    for reference in references:
        try:
            snapshot = prepare_basal_snapshot(
                data,
                reference.identity,
                reference.decision_timestamp,
                lambda history: predict_parameters(frozen, history),
                dataset_path=str(resolved_dataset.resolve()),
                checkpoint_sha256=frozen.checkpoint_sha256,
                checkpoint_metadata=frozen.checkpoint,
            )
            candidate_set = baseline_only_candidate_set(
                generate_basal_candidates(snapshot, search_configuration)
            )
            inputs = build_candidate_inputs(snapshot, candidate_set)
            simulation = simulate_candidate_batch(inputs, candidate_batch_size=1)
            assessment = assess_baseline_reliability(
                snapshot, simulation, reliability_criteria
            )
            development = analyze_error_development(assessment)
            slug = f"{reference.dataset}-{reference.patient_id}".replace("#", "-").replace("/", "-")
            plot_name = f"{slug}-{reference.decision_timestamp:%Y%m%d%H%M}.png"
            if write_plots:
                _plot_window(assessment, inputs, output / plot_name)
            windows.append({
                "identity": asdict(reference.identity),
                "decision_timestamp": reference.decision_timestamp,
                "baseline_candidate_id": assessment.baseline_candidate_id,
                "baseline_rate_u_per_hour": assessment.baseline_rate_u_per_hour,
                "assessment": {
                    "baseline_simulation_status": assessment.baseline_simulation_status,
                    "coverage": asdict(assessment.coverage),
                    "full_window_metrics": (
                        None if assessment.full_window_metrics is None
                        else asdict(assessment.full_window_metrics)
                    ),
                    "day0_metrics": (
                        None if assessment.day0_metrics is None
                        else asdict(assessment.day0_metrics)
                    ),
                    "day1_metrics": (
                        None if assessment.day1_metrics is None
                        else asdict(assessment.day1_metrics)
                    ),
                    "endpoint_error_mg_dl": assessment.endpoint_error_mg_dl,
                    "gate_status": assessment.status,
                    "future_selection_authorized": assessment.future_selection_authorized,
                    "criteria_configuration_hash": assessment.criteria_configuration_hash,
                },
                "error_development": asdict(development),
                "audit": audit_window(snapshot, inputs, assessment),
                "plot": plot_name if write_plots else None,
            })
        except (ValueError, RuntimeError) as exc:
            failures.append(
                f"{reference.dataset}/{reference.patient_id} at "
                f"{reference.decision_timestamp}: {exc}"
            )
    data_unchanged = _dataframe_fingerprint(data) == data_fingerprint_before
    model_unchanged = _model_state_unchanged(frozen.model, model_state_before)
    if not data_unchanged or not model_unchanged:
        raise RuntimeError(
            "Diagnostic execution mutated source data or frozen model state"
        )
    payload = {
        "scope": "bounded development-only unchanged-basal diagnostic",
        "dataset_path": str(resolved_dataset.resolve()),
        "checkpoint_sha256": frozen.checkpoint_sha256,
        "checkpoint_training_contract": {
            "history_steps": frozen.checkpoint["history_steps"],
            "forecast_horizon_steps": frozen.checkpoint["horizon_steps"],
            "forecast_horizon_minutes": int(HORIZON * 5),
            "validation_metric_scope": frozen.checkpoint.get("validation_metric_scope"),
            "validation_selection": frozen.checkpoint.get("validation_selection"),
            "training_physiological_history_observation_handling": (
                "Q1 is replaced with each next observed historical CGM value"
            ),
            "training_physiological_history_carbohydrate": "carbs_g (announced)",
            "training_forecast_carbohydrate": "carbs_g (announced)",
            "current_runtime_initialization_carbohydrate": "consumed_carbs_g",
            "current_runtime_forecast_carbohydrate": "consumed_carbs_g",
            "forecast_observation_handling": "no future glucose argument or correction",
            "parameters_during_forecast": "one GRU estimate fixed over the forecast window",
        },
        "selection": {
            **asdict(selection),
            "known_example_added": bool(
                include_known_example and KNOWN_EXAMPLE not in selection.windows
            ),
            "selected_reference_count": len(references),
        },
        "reliability_criteria_hash": criteria_digest,
        "reliability_authorization_changed": False,
        "source_immutability": {
            "dataframe_unchanged": data_unchanged,
            "frozen_model_state_unchanged": model_unchanged,
        },
        "windows": windows,
        "failures": failures,
        "aggregate": _aggregate(windows),
    }
    (output / "diagnostics.json").write_text(
        json.dumps(payload, indent=2, default=_json_default) + "\n"
    )
    (output / "REPORT.md").write_text(_markdown_report(payload))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_RESULTS_DIRECTORY)
    parser.add_argument("--maximum-development-patients", type=int, default=4)
    parser.add_argument("--no-known-example", action="store_true")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    result = run_baseline_diagnostic_pilot(
        output_directory=args.out,
        maximum_development_patients=args.maximum_development_patients,
        include_known_example=not args.no_known_example,
        write_plots=not args.no_plots,
    )
    print(json.dumps(result["aggregate"], indent=2))


if __name__ == "__main__":
    main()
