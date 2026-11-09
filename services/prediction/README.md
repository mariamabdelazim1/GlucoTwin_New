# Prediction service

This directory contains the protected GRU–Hovorka inference runtime and experimental bolus optimization package. The checkpoint is loaded from `baseline/model.pt`.

The current model contract requires 288 completed five-minute history rows plus the current boundary row. The feature order is:

1. `cgm_mg_dl`
2. `basal_rate_u_per_hour`
3. `bolus_u`
4. `carbs_g`

The physiological simulator uses basal rate, delivered bolus, and `consumed_carbs_g`. The runtime currently uses a fixed 70 kg physiological weight. The migrated bolus optimizer remains experimental and must not automatically deliver insulin.

An HTTP application layer will be added here; clients must access it through `services/api`, not directly.
