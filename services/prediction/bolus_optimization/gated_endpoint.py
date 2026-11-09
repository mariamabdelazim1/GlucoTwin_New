"""Candidate-specific experimental residual correction at the +60-minute point.

The residual changes one value used for candidate scoring only. It never
changes Hovorka state, inferred parameters, raw trajectories, or arm history.
The saved validation selection remains disabled; callers must explicitly opt
into this experimental override.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from typing import Any, Mapping

import numpy as np
import pandas as pd
import torch
from threadpoolctl import threadpool_limits

from final_model_adapter import ResidualDiagnostic, native

from .candidate_search import CandidateSearchResult
from .scoring import (
    ScoringConfiguration, SelectionResult, calculate_score_components,
    score_and_select_candidates,
)


SCORING_MODE = "raw_trajectory_with_gated_60min"
CORRECTED_INDEX = 11
CORRECTED_HORIZON_MINUTES = 60
RESIDUAL_CLIP_MG_DL = 50.0


@dataclass(frozen=True)
class CandidateEndpointDiagnostic:
    candidate_id: str
    dose_u: float
    raw_60_mg_dl: float
    predicted_residual_mg_dl: float
    clipped_residual_mg_dl: float
    gate: float
    alpha: float
    correction_mg_dl: float
    corrected_60_mg_dl: float
    current_bolus_feature_u: float
    raw_min_mg_dl: float
    raw_feasible: bool
    corrected_endpoint_feasible: bool
    raw_score: float
    experimental_score: float
    raw_trajectory_json: str
    scoring_trajectory_json: str
    history_source: str


@dataclass(frozen=True)
class GatedEndpointSelection:
    selection: SelectionResult
    diagnostics: Mapping[str, CandidateEndpointDiagnostic]
    scoring_mode: str = SCORING_MODE


def _candidate_feature_frame(arm, current_events, search: CandidateSearchResult) -> pd.DataFrame:
    """Rebuild the trained residual contract separately for every dose."""

    base_history = arm.history.gru_input(current_events).detach().clone()
    rows = []
    for candidate in search.candidates:
        if candidate.simulation_status != "simulation_valid":
            rows.append(None)
            continue
        history = base_history.clone()
        # The candidate is represented once in physiology by future_inputs[0].
        # This copy is feature construction only, so current_bolus reflects the
        # evaluated scenario without applying another physiological impulse.
        history[-1, 2] = float(candidate.dose_u)
        prediction = candidate.predicted_glucose_mg_dl.detach().to(torch.float32)
        frame = native.feature_frame(
            history.unsqueeze(0).cpu(),
            prediction[:12].unsqueeze(0).cpu().numpy(),
            search.fixed_parameters.unsqueeze(0).detach().cpu().numpy(),
        )
        rows.append(frame.iloc[0])
    valid_rows = [row for row in rows if row is not None]
    if not valid_rows:
        return pd.DataFrame(index=range(len(rows)))
    columns = valid_rows[0].index
    return pd.DataFrame([
        row if row is not None else pd.Series({column: np.nan for column in columns})
        for row in rows
    ]).reset_index(drop=True)


def score_with_gated_endpoint(
    arm,
    current_events,
    search: CandidateSearchResult,
    search_configuration,
    scoring_configuration: ScoringConfiguration,
    residual: ResidualDiagnostic,
    *,
    force_gated: bool,
    model_predictor=None,
) -> GatedEndpointSelection:
    """Score raw four-hour forecasts after replacing only their +60 value.

    Raw hard-minimum violations remain infeasible even if the output residual
    would lift the corrected endpoint. ``model_predictor`` is a test seam; the
    production path always uses the preserved residual model and feature order.
    """

    if not force_gated:
        raise ValueError("Gated endpoint scoring requires explicit force_gated=True")
    if residual.enabled:
        raise ValueError("This override is defined for the saved enabled=False selection")
    payload = residual.payload
    features = tuple(payload["features"])
    config = payload["config"]
    required_config = {"recent_threshold", "forecast_threshold", "alpha"}
    if not required_config.issubset(config):
        raise ValueError("Residual configuration is incomplete")
    frame = _candidate_feature_frame(arm, current_events, search)
    missing = [name for name in features if name not in frame]
    if missing:
        raise ValueError(f"Residual feature contract is incomplete: {missing}")

    valid_mask = np.array([
        item.simulation_status == "simulation_valid" for item in search.candidates
    ])
    predicted = np.full(len(search.candidates), np.nan, dtype=float)
    predictor = model_predictor or payload["model"].predict
    if valid_mask.any():
        matrix = frame.loc[valid_mask, list(features)].to_numpy(dtype=float)
        if not np.isfinite(matrix).all():
            raise ValueError("Candidate residual features contain nonfinite values")
        with threadpool_limits(limits=1):
            predicted[valid_mask] = np.asarray(predictor(matrix), dtype=float)
    gate = np.zeros(len(search.candidates), dtype=float)
    if valid_mask.any():
        valid_frame = frame.loc[valid_mask]
        gate[valid_mask] = native.rising_gate(
            valid_frame, float(config["recent_threshold"]),
            float(config["forecast_threshold"]),
        )
    clipped = np.clip(predicted, -RESIDUAL_CLIP_MG_DL, RESIDUAL_CLIP_MG_DL)
    correction = float(config["alpha"]) * gate * clipped

    transformed = []
    diagnostics: dict[str, CandidateEndpointDiagnostic] = {}
    for index, candidate in enumerate(search.candidates):
        if candidate.simulation_status != "simulation_valid":
            transformed.append(candidate)
            continue
        raw = candidate.predicted_glucose_mg_dl.detach().clone()
        scoring = raw.clone()
        raw_min = float(raw.min())
        corrected = float(raw[CORRECTED_INDEX]) + float(correction[index])
        raw_feasible = raw_min >= scoring_configuration.hard_minimum_mg_dl
        corrected_feasible = corrected >= scoring_configuration.hard_minimum_mg_dl
        # If raw physiology violates the hard minimum, retain that raw value in
        # the scoring inventory so the output correction cannot hide it.
        if raw_feasible:
            scoring[CORRECTED_INDEX] = corrected
        raw_components = calculate_score_components(raw, candidate.dose_u, scoring_configuration)
        experimental_components = calculate_score_components(
            scoring, candidate.dose_u, scoring_configuration
        )
        transformed.append(replace(
            candidate,
            predicted_glucose_mg_dl=scoring,
            trajectory_min_mg_dl=float(scoring.min()),
            trajectory_max_mg_dl=float(scoring.max()),
            endpoint_glucose_mg_dl=float(scoring[-1]),
        ))
        diagnostics[candidate.candidate_id] = CandidateEndpointDiagnostic(
            candidate.candidate_id, float(candidate.dose_u),
            float(raw[CORRECTED_INDEX]), float(predicted[index]), float(clipped[index]),
            float(gate[index]), float(config["alpha"]), float(correction[index]), corrected,
            float(frame.loc[index, "current_bolus"]), raw_min, raw_feasible,
            corrected_feasible, raw_components.total_score,
            experimental_components.total_score if raw_feasible else raw_components.total_score,
            json.dumps([float(value) for value in raw]),
            json.dumps([float(value) for value in scoring]),
            "observed_initialization_then_arm_local_simulated_history",
        )
    transformed_search = replace(search, candidates=tuple(transformed))
    selection = score_and_select_candidates(
        transformed_search, search_configuration, scoring_configuration
    )
    return GatedEndpointSelection(selection, diagnostics)
