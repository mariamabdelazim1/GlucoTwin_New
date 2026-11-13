"""Retrospective basal preparation and constant-rate candidate generation."""

from .candidate_generation import (
    BASELINE_CONSTANCY_ABSOLUTE_TOLERANCE_U_PER_HOUR,
    EXAMPLE_CONFIGURATION_PATH,
    BasalCandidateSet,
    BasalRateCandidate,
    BasalSearchConfiguration,
    configuration_hash,
    extract_constant_baseline_rate,
    generate_basal_candidates,
    load_search_configuration,
)
from .candidate_inputs import (
    PHYSIOLOGICAL_INPUT_UNITS,
    BasalCandidateInputBatch,
    CandidatePhysiologicalInputs,
    build_candidate_inputs,
)

from .preparation import (
    DEFAULT_DATASET_PATH,
    BasalPreparationError,
    HistoricalWindows,
    PatientIdentity,
    PreparedBasalSnapshot,
    SnapshotClone,
    ValidationOutcome,
    build_historical_windows,
    prepare_basal_snapshot,
    prepare_basal_snapshot_from_file,
)
from .simulation import (
    DEFAULT_CANDIDATE_BATCH_SIZE,
    FIXED_WEIGHT_KG,
    BasalCandidateSimulationResult,
    BasalSimulationBatchResult,
    BasalSimulationFailure,
    simulate_candidate_batch,
)

__all__ = [
    "BASELINE_CONSTANCY_ABSOLUTE_TOLERANCE_U_PER_HOUR",
    "EXAMPLE_CONFIGURATION_PATH",
    "BasalCandidateSet",
    "BasalCandidateInputBatch",
    "BasalCandidateSimulationResult",
    "BasalRateCandidate",
    "BasalSearchConfiguration",
    "CandidatePhysiologicalInputs",
    "DEFAULT_DATASET_PATH",
    "DEFAULT_CANDIDATE_BATCH_SIZE",
    "FIXED_WEIGHT_KG",
    "BasalPreparationError",
    "HistoricalWindows",
    "PatientIdentity",
    "PHYSIOLOGICAL_INPUT_UNITS",
    "PreparedBasalSnapshot",
    "BasalSimulationBatchResult",
    "BasalSimulationFailure",
    "SnapshotClone",
    "ValidationOutcome",
    "build_historical_windows",
    "build_candidate_inputs",
    "configuration_hash",
    "extract_constant_baseline_rate",
    "generate_basal_candidates",
    "load_search_configuration",
    "prepare_basal_snapshot",
    "prepare_basal_snapshot_from_file",
    "simulate_candidate_batch",
]
