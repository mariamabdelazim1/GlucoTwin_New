# Retrospective basal preparation

This package implements steps 1–3 only: timestamped historical windows,
validation, and frozen GRU–Hovorka initialization. It does not generate,
simulate, score, or select a basal candidate.

For a decision timestamp `T`, simulation starts at `S = T - 48 hours`. The
required 72 hours are kept as distinct half-open windows:

- GRU initialization intervals: `[S - 24 hours, S)` — exactly 288 completed
  five-minute rows.
- Boundary at `S`: observed glucose plus prospective recorded basal and
  announced carbohydrate; bolus is zero because the interval has not completed.
- Recorded replay: `[S, T)` — exactly 576 intervals. The row at `T` is excluded
  and may be retained only as a later outcome observation.
- Physiological warm-up: `[S - 6 hours, S)` — exactly 72 completed intervals,
  using recorded basal (U/hour), delivered bolus (U/interval), and consumed
  carbohydrate (g/interval). Events at `S` are not applied during warm-up.

The sole file-backed input is the repository-relative
`services/prediction/model_ready_5min.parquet`; another path is rejected. The
frozen checkpoint still enforces architecture, feature order, parameter order
and bounds, state-dict, five-minute solver, and fixed 70 kg weight contracts.
Its metadata names `model_ready_5min_cleaned.parquet` as training provenance;
the returned snapshot exposes this difference while using the mandated input.

```python
from basal_optimization import PatientIdentity, prepare_basal_snapshot_from_file

snapshot = prepare_basal_snapshot_from_file(
    PatientIdentity("PadovaBaseline", "adult#004"),
    "2027-01-04 00:00:00",
)
candidate_initial_conditions = snapshot.clone_initial_conditions()
```

The snapshot retains patient/split metadata, all original columns in both
windows, the recorded basal trajectory, named seven-parameter and ten-state
tensors, model/checkpoint provenance, and independent cloning for a later
candidate simulator.

## Constant-rate candidate generation

`candidate_generation.py` performs candidate generation only. It does not
construct simulation tensors, replay the model, score candidates, or recommend
a rate. The baseline is the first actual recorded `basal_rate_u_per_hour` value
in the 576-interval replay. Every replay value must be within an absolute
`1e-9 U/hour` tolerance of that reference; meaningful variation is rejected
rather than averaged. Missing, nonfinite, negative, nonnumeric, and Boolean
rates are rejected.

Search settings are always explicit. The included
`example_candidate_configuration_v1.json` is clearly marked as a research
example and uses:

- maximum decrease/increase: `0.20 U/hour`;
- absolute bounds: `[0, 3] U/hour`;
- increment: `0.05 U/hour`; and
- maximum count: `9`.

These are not clinically validated limits. A development-only inspection of
17 patients found recorded baseline rates from `0.3915` to `1.7245 U/hour`
(median `0.836 U/hour`) and a maximum within-patient span of
`2.22e-16 U/hour`. These descriptive observations do not establish safe
intervention bounds; validation and testing outcomes were not used.

```python
from basal_optimization import (
    EXAMPLE_CONFIGURATION_PATH,
    generate_basal_candidates,
    load_search_configuration,
)

settings, settings_hash = load_search_configuration(EXAMPLE_CONFIGURATION_PATH)
candidate_set = generate_basal_candidates(snapshot, settings)
```

The grid is centered on the exact recorded baseline, uses decimal arithmetic,
intersects relative and absolute bounds, omits non-grid endpoints, and verifies
that unique rates remain distinct in the simulator's float32 dtype. Candidate
metadata includes patient/time references, effective bounds, deterministic IDs,
the baseline candidate ID, configuration version/hash, and count.

## Candidate physiological inputs

`candidate_inputs.py` materializes inputs only; it does not run the simulator.
It validates snapshot/candidate identity, timestamps, baseline metadata, and
recorded values before returning one independent float32 `(576, 3)` tensor per
candidate in this fixed order:

1. `basal_rate_u_per_hour` — candidate rate repeated unchanged, in U/hour;
2. `bolus_u` — recorded delivered units in that interval; and
3. `consumed_carbs_g` — recorded grams consumed in that interval.

Each row represents `[timestamp, timestamp + 5 minutes)`. Input timestamps run
from `S` through `T - 5 minutes`; expected output timestamps run from `S + 5
minutes` through `T`. Events at `S` remain in row zero, while events at `T` and
initialization-history events are excluded. Announced `carbs_g` never becomes
physiological ingestion, and no meal-consumption profile is applied.

```python
from basal_optimization import build_candidate_inputs

candidate_inputs = build_candidate_inputs(snapshot, candidate_set)
```

Each candidate receives independently stored inputs, initial state `(10,)`, and
fixed parameters `(7,)`. The builder reports basal, bolus, and carbohydrate
totals for accounting but does not include predictions, scores, or selection.
The baseline candidate repeats the exact first recorded reference before
float32 conversion; permitted sub-`1e-9 U/hour` raw differences are therefore
replaced by that constant and are not averaged or silently copied.
