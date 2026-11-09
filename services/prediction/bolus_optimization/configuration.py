"""Fixed interface between the trained encoder and bolus optimization."""

SAMPLE_INTERVAL_MINUTES = 5
PREDICTION_HORIZON_MINUTES = 4 * 60
PREDICTION_HORIZON_STEPS = PREDICTION_HORIZON_MINUTES // SAMPLE_INTERVAL_MINUTES

# Do not replace ``carbs_g`` with consumed_carbs_g.  The existing checkpoint
# was trained with historical announced carbohydrates in this exact order.
MODEL_FEATURES = (
    "cgm_mg_dl",
    "basal_rate_u_per_hour",
    "bolus_u",
    "carbs_g",
)
HISTORICAL_CARBOHYDRATE_FEATURE = "carbs_g"
ANNOUNCED_CARBOHYDRATE_FEATURE = "carbs_g"
PHYSIOLOGICAL_CARBOHYDRATE_FEATURE = "consumed_carbs_g"

DEFAULT_CHECKPOINT = "baseline/model.pt"
DEFAULT_OUTPUT_DIRECTORY = "results/bolus_optimization_migrated_final"
FROZEN_CHECKPOINT_SHA256 = "0b27f4da9cf6f5f9f9e038708c4878ae6e04a6d9347085d6d860dbbefec1a8ac"
