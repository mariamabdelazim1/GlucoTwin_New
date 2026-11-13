# Prediction service

This directory contains the protected GRU–Hovorka inference runtime and experimental bolus optimization package. The checkpoint is loaded from `baseline/model.pt`.

The current model contract requires 288 completed five-minute history rows plus the current boundary row. The feature order is:

1. `cgm_mg_dl`
2. `basal_rate_u_per_hour`
3. `bolus_u`
4. `carbs_g`

The physiological simulator uses basal rate, delivered bolus, and `consumed_carbs_g`. The runtime currently uses a fixed 70 kg physiological weight. The migrated bolus optimizer remains experimental and must not automatically deliver insulin.

## Research bolus-optimizer default

`bolus_optimization/migrated_selected_configuration.json` is the single canonical default for research bolus-optimizer entry points. It preserves the migrated trigger, glucose-penalty, feasibility, meal-consumption, physiological-initialization, parameter-refresh, and four-hour simulation settings, with these research-default changes:

- candidates are exactly `0, 0.5, 1.0, ..., 19.5, 20.0` U;
- the insulin penalty weight is `0.0`;
- candidates are scored from the raw Hovorka trajectory; and
- gated-endpoint and residual scoring corrections are disabled.

The 20 U ceiling is an experimental search bound, not a validated safe-dose limit. This configuration is not connected to web/mobile dosing, automatic insulin delivery, or any clinical dosing flow. Dataset/checkpoint identity verification remains strict by default.

The supporting exploratory run reported 3,949 matched complete pairs from 3,950 attempted episodes across 23 development/validation patients. One pair failed simulator-validity checks, testing patients were excluded, and the run used an explicit dataset-hash mismatch override. These are internal exploratory simulations—not independent validation, final test-set validation, or clinical evidence.

Historical alternatives remain available for explicit reproducibility:

- `bolus_optimization/historical_migrated_selected_configuration_v1.json` is the previous migrated 3 U policy;
- `bolus_optimization/bolus_search_configuration_migrated_final_v1.json` and `scoring_configuration_migrated_final_v1.json` are its standalone components; and
- `bolus_search_configuration_v1.json`, `scoring_configuration_v1.json`, and `trigger_configuration_v1.json` are earlier standalone diagnostic defaults.

The standalone paired runner uses the canonical policy when no component paths are supplied:

```bash
python -m bolus_optimization.run_paired_episodes model_ready_5min.parquet
```

Explicit historical or custom component paths still take precedence, for example:

```bash
python -m bolus_optimization.run_paired_episodes model_ready_5min.parquet \
  --search-configuration bolus_optimization/bolus_search_configuration_migrated_final_v1.json \
  --scoring-configuration bolus_optimization/scoring_configuration_migrated_final_v1.json
```

The paired runner performs strict dataset/checkpoint verification. The mismatch override in `run_expanded_exploratory_bolus.py` is scoped only to that archived exploratory experiment and is not a normal optimizer default.

An HTTP application layer will be added here; clients must access it through `services/api`, not directly.
