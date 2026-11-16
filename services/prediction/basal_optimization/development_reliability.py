"""Small, deterministic development-only workflow for baseline-fit diagnostics.

This module does not derive or tune reliability limits.  It selects explicitly
bounded pilot windows and summarizes already-computed assessments without
allowing patients with more windows to silently dominate patient summaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .preparation import INTERVAL, INITIALIZATION_INTERVALS, REPLAY_INTERVALS, PatientIdentity
from .reliability import BaselineReliabilityAssessment, ReliabilityCriteria, assess_baseline_reliability


CONTINUITY_COLUMNS = ("source_run_id", "source_record_id", "continuous_record_id")


@dataclass(frozen=True, order=True)
class DevelopmentWindowReference:
    dataset: str
    patient_id: str
    decision_timestamp: pd.Timestamp

    @property
    def identity(self) -> PatientIdentity:
        return PatientIdentity(self.dataset, self.patient_id)


@dataclass(frozen=True)
class DevelopmentWindowSelection:
    windows: tuple[DevelopmentWindowReference, ...]
    maximum_patients: int
    windows_per_patient: int
    development_patient_count: int
    selected_patient_count: int
    excluded_nondevelopment_patient_count: int
    excluded_development_patient_count: int
    exclusion_reasons: tuple[str, ...]


@dataclass(frozen=True)
class MetricDistribution:
    count: int
    minimum: float | None
    median: float | None
    mean: float | None
    maximum: float | None


@dataclass(frozen=True)
class PatientMetricSummary:
    identity: PatientIdentity
    completed_window_count: int
    mean_metrics: dict[str, float]


@dataclass(frozen=True)
class DevelopmentReliabilitySummary:
    window_count: int
    patient_count: int
    complete_window_count: int
    numerical_failure_count: int
    status_counts: tuple[tuple[str, int], ...]
    pooled_window_metrics: dict[str, MetricDistribution]
    patient_mean_metrics: tuple[PatientMetricSummary, ...]
    equally_weighted_patient_metrics: dict[str, MetricDistribution]


@dataclass(frozen=True)
class DevelopmentReliabilityPilot:
    selection: DevelopmentWindowSelection
    assessments: tuple[BaselineReliabilityAssessment, ...]
    window_failures: tuple[str, ...]
    summary: DevelopmentReliabilitySummary


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{label} must be a positive integer")
    result = int(value)
    if result <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return result


def _eligible_segment_windows(segment: pd.DataFrame) -> list[pd.Timestamp]:
    required_rows = INITIALIZATION_INTERVALS + REPLAY_INTERVALS + 1
    ordered = segment.sort_values("timestamp", kind="stable")
    timestamps = pd.DatetimeIndex(ordered["timestamp"])
    if len(timestamps) < required_rows or timestamps.has_duplicates:
        return []
    eligible: list[pd.Timestamp] = []
    # Non-overlapping replays make the pilot deterministic and prevent dense
    # windows from making one long patient record dominate by default.
    for decision_index in range(required_rows - 1, len(timestamps), REPLAY_INTERVALS):
        window = timestamps[decision_index - required_rows + 1 : decision_index + 1]
        expected = pd.date_range(window[0], periods=required_rows, freq=INTERVAL)
        if window.as_unit("ns").equals(expected.as_unit("ns")):
            eligible.append(pd.Timestamp(window[-1]))
    return eligible


def select_development_windows(
    data: pd.DataFrame,
    *,
    maximum_patients: int,
    windows_per_patient: int = 1,
) -> DevelopmentWindowSelection:
    """Select a small deterministic pilot; validation/testing rows are excluded."""

    maximum_patients = _positive_integer(maximum_patients, "maximum_patients")
    windows_per_patient = _positive_integer(windows_per_patient, "windows_per_patient")
    required = {"dataset", "patient_id", "split", "timestamp"}
    missing = sorted(required.difference(data.columns))
    if missing:
        raise ValueError(f"Development selection is missing columns: {missing}")

    identities = data[["dataset", "patient_id", "split"]].drop_duplicates()
    inconsistent = identities.groupby(["dataset", "patient_id"])["split"].nunique()
    if (inconsistent != 1).any():
        raise ValueError("Patient split metadata must be constant for development selection")
    patient_splits = identities.drop_duplicates(["dataset", "patient_id"])
    nondevelopment = int((patient_splits["split"] != "development").sum())
    development = patient_splits.loc[patient_splits["split"] == "development"]
    development_keys = sorted(
        (str(row.dataset), str(row.patient_id))
        for row in development.itertuples(index=False)
    )

    selected: list[DevelopmentWindowReference] = []
    exclusions: list[str] = []
    selected_patients = 0
    for dataset, patient_id in development_keys:
        if selected_patients >= maximum_patients:
            break
        patient = data.loc[
            (data["dataset"].astype(str) == dataset)
            & (data["patient_id"].astype(str) == patient_id)
        ].copy()
        patient["timestamp"] = pd.to_datetime(patient["timestamp"], errors="coerce")
        if patient["timestamp"].isna().any():
            exclusions.append(f"{dataset}/{patient_id}: invalid timestamp")
            continue
        continuity = [column for column in CONTINUITY_COLUMNS if column in patient.columns]
        if continuity and patient[continuity].isna().any(axis=None):
            exclusions.append(f"{dataset}/{patient_id}: missing continuity identifier")
            continue
        segments: Iterable[tuple[object, pd.DataFrame]]
        if continuity:
            segments = patient.groupby(continuity, sort=True, dropna=False)
        else:
            segments = ((None, patient),)
        eligible = sorted(
            timestamp
            for _, segment in segments
            for timestamp in _eligible_segment_windows(segment)
        )
        if not eligible:
            exclusions.append(f"{dataset}/{patient_id}: no complete 72-hour window plus outcome")
            continue
        for timestamp in eligible[:windows_per_patient]:
            selected.append(DevelopmentWindowReference(dataset, patient_id, timestamp))
        selected_patients += 1

    return DevelopmentWindowSelection(
        windows=tuple(selected),
        maximum_patients=maximum_patients,
        windows_per_patient=windows_per_patient,
        development_patient_count=len(development_keys),
        selected_patient_count=selected_patients,
        excluded_nondevelopment_patient_count=nondevelopment,
        excluded_development_patient_count=len(exclusions),
        exclusion_reasons=tuple(exclusions),
    )


def _distribution(values: Iterable[float]) -> MetricDistribution:
    array = np.asarray(list(values), dtype=np.float64)
    if not len(array):
        return MetricDistribution(0, None, None, None, None)
    if not np.isfinite(array).all():
        raise ValueError("Development reliability summary received nonfinite metrics")
    return MetricDistribution(
        len(array), float(array.min()), float(np.median(array)),
        float(array.mean()), float(array.max()),
    )


def summarize_development_assessments(
    assessments: Iterable[BaselineReliabilityAssessment],
) -> DevelopmentReliabilitySummary:
    """Report pooled windows and equally weighted per-patient mean metrics."""

    items = tuple(assessments)
    names = ("full_mae", "full_rmse", "day0_mae", "day0_rmse", "day1_mae", "day1_rmse")

    def metric_values(item: BaselineReliabilityAssessment) -> dict[str, float] | None:
        if item.full_window_metrics is None or item.day0_metrics is None or item.day1_metrics is None:
            return None
        return {
            "full_mae": item.full_window_metrics.mae_mg_dl,
            "full_rmse": item.full_window_metrics.rmse_mg_dl,
            "day0_mae": item.day0_metrics.mae_mg_dl,
            "day0_rmse": item.day0_metrics.rmse_mg_dl,
            "day1_mae": item.day1_metrics.mae_mg_dl,
            "day1_rmse": item.day1_metrics.rmse_mg_dl,
        }

    valid = [(item, metric_values(item)) for item in items]
    valid = [(item, values) for item, values in valid if values is not None]
    pooled = {name: _distribution(values[name] for _, values in valid) for name in names}
    per_patient: dict[tuple[str, str], list[dict[str, float]]] = {}
    for item, values in valid:
        per_patient.setdefault((item.identity.dataset, item.identity.patient_id), []).append(values)
    patient_distributions = {
        name: _distribution(
            float(np.mean([window[name] for window in windows]))
            for windows in per_patient.values()
        )
        for name in names
    }
    patient_summaries = tuple(
        PatientMetricSummary(
            PatientIdentity(dataset, patient_id),
            len(windows),
            {name: float(np.mean([window[name] for window in windows])) for name in names},
        )
        for (dataset, patient_id), windows in sorted(per_patient.items())
    )
    statuses: dict[str, int] = {}
    for item in items:
        statuses[item.status] = statuses.get(item.status, 0) + 1
    return DevelopmentReliabilitySummary(
        window_count=len(items),
        patient_count=len({(item.identity.dataset, item.identity.patient_id) for item in items}),
        complete_window_count=sum(item.coverage.complete for item in items),
        numerical_failure_count=sum(item.baseline_simulation_status != "simulation_valid" for item in items),
        status_counts=tuple(sorted(statuses.items())),
        pooled_window_metrics=pooled,
        patient_mean_metrics=patient_summaries,
        equally_weighted_patient_metrics=patient_distributions,
    )


def run_development_reliability_pilot(
    *,
    maximum_patients: int,
    windows_per_patient: int = 1,
    criteria: ReliabilityCriteria | None = None,
    dataset_path: str | Path | None = None,
    search_configuration_path: str | Path | None = None,
) -> DevelopmentReliabilityPilot:
    """Run a bounded pilot while loading the frozen GRU and source data once.

    No criteria are derived here. Passing ``criteria=None`` intentionally
    produces ``criteria_not_calibrated`` assessments.
    """

    from bolus_optimization.checkpoint import load_frozen_gru, predict_parameters
    from bolus_optimization.configuration import FROZEN_CHECKPOINT_SHA256
    from .candidate_generation import (
        EXAMPLE_CONFIGURATION_PATH, generate_basal_candidates, load_search_configuration,
    )
    from .candidate_inputs import build_candidate_inputs
    from .preparation import (
        DEFAULT_CHECKPOINT_PATH, DEFAULT_DATASET_PATH, REPOSITORY_ROOT,
        BasalPreparationError, _resolve_repository_path, prepare_basal_snapshot,
    )
    from .simulation import simulate_candidate_batch

    requested_dataset = DEFAULT_DATASET_PATH if dataset_path is None else Path(dataset_path)
    resolved_dataset = _resolve_repository_path(requested_dataset)
    mandated = (REPOSITORY_ROOT / DEFAULT_DATASET_PATH).resolve()
    if resolved_dataset.resolve() != mandated:
        raise BasalPreparationError(
            f"development reliability requires {mandated}; received {resolved_dataset.resolve()}"
        )
    data = pd.read_parquet(resolved_dataset)
    frozen = load_frozen_gru(
        DEFAULT_CHECKPOINT_PATH, expected_sha256=FROZEN_CHECKPOINT_SHA256
    )
    actual_splits = {
        str((str(dataset), str(patient))): str(group["split"].iloc[0])
        for (dataset, patient), group in data.groupby(["dataset", "patient_id"], sort=False)
    }
    if actual_splits != frozen.checkpoint["patient_splits"]:
        raise BasalPreparationError("patient split metadata differs from the frozen checkpoint")
    selection = select_development_windows(
        data, maximum_patients=maximum_patients, windows_per_patient=windows_per_patient
    )
    config_path = (
        EXAMPLE_CONFIGURATION_PATH
        if search_configuration_path is None
        else Path(search_configuration_path)
    )
    search_configuration, _ = load_search_configuration(config_path)
    assessments: list[BaselineReliabilityAssessment] = []
    failures: list[str] = []
    for reference in selection.windows:
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
            candidate_set = generate_basal_candidates(snapshot, search_configuration)
            inputs = build_candidate_inputs(snapshot, candidate_set)
            simulation = simulate_candidate_batch(inputs)
            assessments.append(assess_baseline_reliability(snapshot, simulation, criteria))
        except (ValueError, RuntimeError) as exc:
            failures.append(
                f"{reference.dataset}/{reference.patient_id} at "
                f"{reference.decision_timestamp}: {exc}"
            )
    frozen_assessments = tuple(assessments)
    return DevelopmentReliabilityPilot(
        selection,
        frozen_assessments,
        tuple(failures),
        summarize_development_assessments(frozen_assessments),
    )
