"""Candidate feasibility, explainable scoring and deterministic selection.

Selection is returned to the caller only.  This module does not acknowledge an
event, mutate a simulation, create a delivery or evaluate clinical safety.
"""

from __future__ import annotations

import numbers
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from .candidate_search import (
    BolusSearchConfiguration, CandidateSearchResult, CandidateSimulationResult,
    generate_bolus_candidates,
)
from .configuration import PREDICTION_HORIZON_STEPS, SAMPLE_INTERVAL_MINUTES
from .configuration_loading import (
    DEFAULT_RESEARCH_CONFIGURATION, load_component_payload,
)
from .physiology import _normalize_state


DEFAULT_SCORING_CONFIGURATION = DEFAULT_RESEARCH_CONFIGURATION


def _number(value, name: str, *, positive: bool = False, nonnegative: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be numeric and not Boolean")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0:
        raise ValueError(f"{name} must be strictly positive")
    if nonnegative and result < 0:
        raise ValueError(f"{name} must be nonnegative")
    return result


@dataclass(frozen=True)
class ScoringConfiguration:
    configuration_version: str
    target_lower_mg_dl: float
    target_upper_mg_dl: float
    severe_low_threshold_mg_dl: float
    hard_minimum_mg_dl: float
    low_weight: float
    high_weight: float
    severe_low_weight: float
    insulin_weight: float
    terminal_weight: float
    glucose_scale_mg_dl: float
    insulin_scale_u: float
    terminal_window_minutes: int
    absolute_tie_tolerance: float
    relative_tie_tolerance: float
    intended_use: str

    def __post_init__(self):
        if not self.configuration_version or not self.intended_use:
            raise ValueError("Scoring version and intended use are required")
        numeric = (
            "target_lower_mg_dl", "target_upper_mg_dl", "severe_low_threshold_mg_dl",
            "hard_minimum_mg_dl", "low_weight", "high_weight", "severe_low_weight",
            "insulin_weight", "terminal_weight", "glucose_scale_mg_dl", "insulin_scale_u",
            "absolute_tie_tolerance", "relative_tie_tolerance",
        )
        for name in numeric:
            positive = name in {"target_lower_mg_dl", "target_upper_mg_dl", "severe_low_threshold_mg_dl",
                                "hard_minimum_mg_dl", "glucose_scale_mg_dl", "insulin_scale_u"}
            nonnegative = not positive
            object.__setattr__(self, name, _number(
                getattr(self, name), name, positive=positive, nonnegative=nonnegative
            ))
        if not self.severe_low_threshold_mg_dl < self.target_lower_mg_dl < self.target_upper_mg_dl:
            raise ValueError("Glucose thresholds must satisfy severe low < target lower < target upper")
        if self.hard_minimum_mg_dl > self.target_lower_mg_dl:
            raise ValueError("hard_minimum_mg_dl must be no higher than target lower")
        if self.low_weight <= 0 or self.high_weight <= 0:
            raise ValueError("Low and high glucose weights must be positive")
        duration = self.terminal_window_minutes
        if isinstance(duration, (bool, np.bool_)) or not isinstance(duration, numbers.Integral):
            raise ValueError("terminal_window_minutes must be a positive integer")
        duration = int(duration)
        if duration <= 0 or duration > 240 or duration % SAMPLE_INTERVAL_MINUTES:
            raise ValueError("terminal window must be a positive five-minute multiple no longer than 240")
        object.__setattr__(self, "terminal_window_minutes", duration)

    @property
    def terminal_window_steps(self):
        return self.terminal_window_minutes // SAMPLE_INTERVAL_MINUTES


def load_scoring_configuration(path: str | Path = DEFAULT_SCORING_CONFIGURATION):
    _, _, payload, content_hash = load_component_payload(path, "scoring")
    return ScoringConfiguration(**payload), content_hash


@dataclass(frozen=True)
class ScoreComponents:
    low_component: float
    high_component: float
    severe_low_component: float
    insulin_component: float
    terminal_component: float
    weighted_low: float
    weighted_high: float
    weighted_severe_low: float
    weighted_insulin: float
    weighted_terminal: float
    total_score: float


def calculate_score_components(
    predicted_glucose_mg_dl: torch.Tensor,
    dose_u: float,
    configuration: ScoringConfiguration,
) -> ScoreComponents:
    if not isinstance(predicted_glucose_mg_dl, torch.Tensor) \
            or predicted_glucose_mg_dl.ndim != 1 \
            or len(predicted_glucose_mg_dl) != PREDICTION_HORIZON_STEPS:
        raise ValueError("Scoring requires exactly 48 predicted glucose values")
    dose = _number(dose_u, "dose_u", nonnegative=True)
    glucose = predicted_glucose_mg_dl.detach().to(dtype=torch.float64)
    low = torch.clamp(configuration.target_lower_mg_dl - glucose, min=0) / configuration.glucose_scale_mg_dl
    high = torch.clamp(glucose - configuration.target_upper_mg_dl, min=0) / configuration.glucose_scale_mg_dl
    severe = torch.clamp(configuration.severe_low_threshold_mg_dl - glucose, min=0) / configuration.glucose_scale_mg_dl
    low_component = float(torch.mean(low.square()))
    high_component = float(torch.mean(high.square()))
    severe_component = float(torch.mean(severe.square()))
    insulin_component = float((dose / configuration.insulin_scale_u) ** 2)
    terminal_component = float(torch.mean(
        low[-configuration.terminal_window_steps:].square()
        + high[-configuration.terminal_window_steps:].square()
    ))
    weighted = (
        configuration.low_weight * low_component,
        configuration.high_weight * high_component,
        configuration.severe_low_weight * severe_component,
        configuration.insulin_weight * insulin_component,
        configuration.terminal_weight * terminal_component,
    )
    total = float(sum(weighted))
    return ScoreComponents(
        low_component, high_component, severe_component, insulin_component,
        terminal_component, *weighted, total,
    )


@dataclass(frozen=True)
class ScoredCandidate:
    candidate_index: int
    candidate_id: str
    dose_u: float
    numerical_status: str
    feasibility_status: str
    rejection_reason: str | None
    components: ScoreComponents | None
    score: float | None
    tie_set_member: bool
    selected: bool


@dataclass(frozen=True)
class SelectionResult:
    evaluation_event_id: str
    status: str
    no_feasible_reason: str | None
    selected_candidate_id: str | None
    selected_dose_u: float | None
    selected_score: float | None
    selected_components: ScoreComponents | None
    lowest_numerical_score: float | None
    tie_candidate_ids: tuple[str, ...]
    tie_breaking_reason: str | None
    feasible_candidate_count: int
    rejected_candidate_count: int
    rejection_reason_counts: dict[str, int]
    selected_at_upper_grid_boundary: bool
    additional_bolus_for_simulation_u: float
    scored_candidates: tuple[ScoredCandidate, ...]


class SearchInventoryError(ValueError):
    pass


def _validated_timestamp_grid(values, expected, name: str):
    try:
        raw = tuple(values)
    except TypeError:
        raise SearchInventoryError(f"{name} must be a timestamp sequence") from None
    if len(raw) != PREDICTION_HORIZON_STEPS:
        raise SearchInventoryError(f"{name} must contain exactly 48 timestamps")
    parsed = []
    for index, value in enumerate(raw):
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError, OverflowError):
            raise SearchInventoryError(f"{name}[{index}] is not a valid timestamp") from None
        if pd.isna(timestamp):
            raise SearchInventoryError(f"{name}[{index}] must not be NaT")
        parsed.append(timestamp)
    parsed = tuple(parsed)
    if len(set(parsed)) != len(parsed):
        raise SearchInventoryError(f"{name} contains duplicate timestamps")
    if parsed != expected:
        raise SearchInventoryError(f"{name} is reordered, shifted or off the five-minute grid")
    return parsed


def _validate_inventory(
    search_result: CandidateSearchResult,
    search_configuration: BolusSearchConfiguration,
):
    if not isinstance(search_result, CandidateSearchResult):
        raise TypeError("search_result must be a CandidateSearchResult")
    expected = generate_bolus_candidates(
        search_configuration, tensor_dtype=search_result.fixed_parameters.dtype
    )
    snapshot = search_result.candidate_inputs.snapshot
    if search_result.evaluation_event_id != snapshot.evaluation_event_id \
            or search_result.decision_timestamp != snapshot.decision_timestamp \
            or search_result.parameter_estimation_timestamp != snapshot.parameter_estimation_timestamp:
        raise SearchInventoryError("Search and snapshot identities or timestamps do not match")
    try:
        decision_timestamp = pd.Timestamp(search_result.decision_timestamp)
    except (TypeError, ValueError, OverflowError):
        raise SearchInventoryError("Search decision timestamp is invalid") from None
    if pd.isna(decision_timestamp):
        raise SearchInventoryError("Search decision timestamp must not be NaT")
    interval = pd.Timedelta(minutes=SAMPLE_INTERVAL_MINUTES)
    expected_inputs = tuple(
        decision_timestamp + index * interval
        for index in range(PREDICTION_HORIZON_STEPS)
    )
    expected_outputs = tuple(timestamp + interval for timestamp in expected_inputs)
    _validated_timestamp_grid(
        search_result.candidate_inputs.interval_timestamps,
        expected_inputs, "candidate input interval timestamps",
    )
    _validated_timestamp_grid(
        search_result.candidate_inputs.output_timestamps,
        expected_outputs, "candidate output timestamps",
    )
    if len(search_result.candidates) != len(expected):
        raise SearchInventoryError("Search inventory has missing or extra candidates")
    if search_result.generated_candidate_count != len(expected) \
            or search_result.simulated_candidate_count != len(expected):
        raise SearchInventoryError("Search candidate counts do not match the configured grid")
    ids = [item.candidate_id for item in search_result.candidates]
    if len(ids) != len(set(ids)):
        raise SearchInventoryError("Search inventory contains duplicate candidate IDs")
    expected_by_id = {item.candidate_id: (index, item.bolus_u) for index, item in enumerate(expected)}
    materialized_candidates = tuple(search_result.candidate_inputs.candidates)
    if len(materialized_candidates) != len(expected):
        raise SearchInventoryError(
            "Materialized candidate-input inventory has missing or extra candidates"
        )
    materialized_ids = [item.candidate_id for item in materialized_candidates]
    if len(materialized_ids) != len(set(materialized_ids)):
        raise SearchInventoryError(
            "Materialized candidate-input inventory contains duplicate candidate IDs"
        )
    inputs_by_id = {item.candidate_id: item for item in materialized_candidates}
    if set(ids) != set(expected_by_id) or set(inputs_by_id) != set(expected_by_id):
        raise SearchInventoryError("Search inventory does not match the configured grid, including zero")
    for item in search_result.candidates:
        index, dose = expected_by_id[item.candidate_id]
        materialized = inputs_by_id[item.candidate_id]
        if item.candidate_index != index or item.dose_u != dose or materialized.bolus_u != dose:
            raise SearchInventoryError("Candidate index or dose does not match configured grid")
        expected_tensor_dose = torch.tensor(
            dose, dtype=materialized.future_inputs.dtype,
            device=materialized.future_inputs.device,
        )
        if not torch.equal(materialized.future_inputs[0, 1], expected_tensor_dose) \
                or not torch.all(materialized.future_inputs[1:, 1] == 0).item():
            raise SearchInventoryError("Candidate interval-zero bolus does not match its dose")
        _validated_timestamp_grid(
            item.prediction_timestamps, expected_outputs,
            f"candidate {item.candidate_id} prediction timestamps",
        )
    return expected


def _rejection(candidate: CandidateSimulationResult, reason: str, status: str):
    return ScoredCandidate(
        candidate.candidate_index, candidate.candidate_id, candidate.dose_u,
        candidate.simulation_status, status, reason, None, None, False, False,
    )


def score_and_select_candidates(
    search_result: CandidateSearchResult,
    search_configuration: BolusSearchConfiguration,
    scoring_configuration: ScoringConfiguration,
) -> SelectionResult:
    """Score immutable candidate results and deterministically select one feasible dose."""

    expected = _validate_inventory(search_result, search_configuration)
    scored = []
    for candidate in search_result.candidates:
        if candidate.simulation_status != "simulation_valid":
            scored.append(_rejection(candidate, "simulation_failed", "numerical_failure"))
            continue
        trajectory = candidate.predicted_glucose_mg_dl
        if not isinstance(trajectory, torch.Tensor) or trajectory.ndim != 1 \
                or len(trajectory) != PREDICTION_HORIZON_STEPS:
            scored.append(_rejection(candidate, "incomplete_trajectory", "numerical_failure"))
            continue
        if not torch.isfinite(trajectory).all().item():
            scored.append(_rejection(candidate, "nonfinite_trajectory", "numerical_failure"))
            continue
        if not isinstance(candidate.final_state, torch.Tensor) \
                or not candidate.final_state.dtype.is_floating_point \
                or candidate.final_state.shape != (10,):
            scored.append(_rejection(candidate, "invalid_final_state", "numerical_failure"))
            continue
        _, final_reason, _ = _normalize_state(candidate.final_state.detach().clone())
        if final_reason is not None:
            scored.append(_rejection(candidate, "invalid_final_state", "numerical_failure"))
            continue
        try:
            components = calculate_score_components(
                trajectory, candidate.dose_u, scoring_configuration
            )
        except (ValueError, TypeError, OverflowError):
            scored.append(_rejection(candidate, "nonfinite_score", "score_failure"))
            continue
        component_values = tuple(components.__dict__.values())
        if not all(np.isfinite(value) for value in component_values):
            scored.append(_rejection(candidate, "nonfinite_score", "score_failure"))
            continue
        if float(torch.min(trajectory)) < scoring_configuration.hard_minimum_mg_dl:
            scored.append(ScoredCandidate(
                candidate.candidate_index, candidate.candidate_id, candidate.dose_u,
                candidate.simulation_status, "policy_infeasible",
                "predicted_glucose_below_hard_minimum", components,
                components.total_score, False, False,
            ))
            continue
        scored.append(ScoredCandidate(
            candidate.candidate_index, candidate.candidate_id, candidate.dose_u,
            candidate.simulation_status, "feasible", None, components,
            components.total_score, False, False,
        ))
    feasible = [item for item in scored if item.feasibility_status == "feasible"]
    finite_scores = [item.score for item in scored if item.score is not None and np.isfinite(item.score)]
    lowest_numerical = min(finite_scores) if finite_scores else None
    rejection_counts = {}
    for item in scored:
        if item.rejection_reason:
            rejection_counts[item.rejection_reason] = rejection_counts.get(item.rejection_reason, 0) + 1
    if not feasible:
        if all(item.rejection_reason == "simulation_failed" for item in scored):
            cause = "all_simulations_failed"
        elif all(item.feasibility_status == "score_failure" for item in scored):
            cause = "all_otherwise_eligible_scores_failed"
        elif all(item.feasibility_status == "numerical_failure" for item in scored):
            cause = "all_candidates_numerically_invalid"
        else:
            cause = "all_complete_candidates_violated_feasibility_or_score_rules"
        return SelectionResult(
            search_result.evaluation_event_id, "no_feasible_recommendation", cause,
            None, None, None, None, lowest_numerical, (), None, 0, len(scored),
            rejection_counts, False, 0.0, tuple(scored),
        )
    minimum = min(item.score for item in feasible)
    tolerance = (
        scoring_configuration.absolute_tie_tolerance
        + scoring_configuration.relative_tie_tolerance * abs(minimum)
    )
    tied = [item for item in feasible if abs(item.score - minimum) <= tolerance]
    selected = min(tied, key=lambda item: (item.dose_u, item.candidate_id))
    tie_ids = tuple(item.candidate_id for item in sorted(tied, key=lambda item: (item.dose_u, item.candidate_id)))
    tie_reason = (
        "smallest_bolus_within_effective_tie_then_candidate_id" if len(tied) > 1
        else "unique_minimum_score"
    )
    updated = tuple(ScoredCandidate(
        item.candidate_index, item.candidate_id, item.dose_u, item.numerical_status,
        item.feasibility_status, item.rejection_reason, item.components, item.score,
        item.candidate_id in tie_ids, item.candidate_id == selected.candidate_id,
    ) for item in scored)
    maximum_dose = max(item.bolus_u for item in expected)
    return SelectionResult(
        search_result.evaluation_event_id, "selected", None,
        selected.candidate_id, selected.dose_u, selected.score, selected.components,
        lowest_numerical, tie_ids, tie_reason, len(feasible), len(scored) - len(feasible),
        rejection_counts, selected.dose_u == maximum_dose, selected.dose_u, updated,
    )
