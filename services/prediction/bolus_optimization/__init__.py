"""Hovorka-only bolus optimization utilities.

This package is intentionally separate from the existing training and testing
entry points. It reaches the final frozen GRU only through
``final_model_adapter`` to estimate Hovorka parameters; bolus candidates are
evaluated by the uncorrected stateful Hovorka simulator.
"""

from .checkpoint import FrozenGRU, load_frozen_gru, predict_parameters
from .candidate_search import (
    BolusSearchConfiguration,
    CandidateSearchResult,
    CandidateSimulationResult,
    generate_bolus_candidates,
    load_search_configuration,
    simulate_bolus_candidates,
)
from .candidate_inputs import (
    CandidateBolus,
    CandidateInput,
    CandidateInputBatch,
    ConsumptionConfiguration,
    DecisionSnapshot,
    KnownBasalSchedule,
    build_candidate_inputs,
    create_decision_snapshot,
    load_consumption_configuration,
    validate_decision_snapshot,
)
from .configuration import (
    ANNOUNCED_CARBOHYDRATE_FEATURE,
    HISTORICAL_CARBOHYDRATE_FEATURE,
    MODEL_FEATURES,
    PHYSIOLOGICAL_CARBOHYDRATE_FEATURE,
    PREDICTION_HORIZON_MINUTES,
    PREDICTION_HORIZON_STEPS,
    SAMPLE_INTERVAL_MINUTES,
)
from .physiology import (
    CandidateFailure,
    PredictionResult,
    StateResult,
    ValidityInfo,
    advance_state,
    initialize_state,
    physiological_inputs_from_frame,
    predict_from_state,
)
from .migrated_configuration import MigratedConfiguration, load_migrated_configuration
from .scoring import (
    ScoringConfiguration,
    ScoreComponents,
    ScoredCandidate,
    SelectionResult,
    calculate_score_components,
    load_scoring_configuration,
    score_and_select_candidates,
)

__all__ = [
    "ANNOUNCED_CARBOHYDRATE_FEATURE",
    "CandidateFailure",
    "BolusSearchConfiguration",
    "CandidateBolus",
    "CandidateInput",
    "CandidateInputBatch",
    "CandidateSearchResult",
    "CandidateSimulationResult",
    "ConsumptionConfiguration",
    "DecisionSnapshot",
    "FrozenGRU",
    "HISTORICAL_CARBOHYDRATE_FEATURE",
    "MODEL_FEATURES",
    "MigratedConfiguration",
    "KnownBasalSchedule",
    "PHYSIOLOGICAL_CARBOHYDRATE_FEATURE",
    "PredictionResult",
    "PREDICTION_HORIZON_MINUTES",
    "PREDICTION_HORIZON_STEPS",
    "SAMPLE_INTERVAL_MINUTES",
    "ScoredCandidate",
    "ScoringConfiguration",
    "ScoreComponents",
    "SelectionResult",
    "StateResult",
    "ValidityInfo",
    "advance_state",
    "build_candidate_inputs",
    "calculate_score_components",
    "create_decision_snapshot",
    "generate_bolus_candidates",
    "initialize_state",
    "load_frozen_gru",
    "load_migrated_configuration",
    "load_consumption_configuration",
    "load_search_configuration",
    "load_scoring_configuration",
    "validate_decision_snapshot",
    "physiological_inputs_from_frame",
    "predict_parameters",
    "predict_from_state",
    "simulate_bolus_candidates",
    "score_and_select_candidates",
]
