# Retrospective basal preparation

This package implements timestamped historical preparation, frozen GRU–Hovorka
initialization, constant-rate candidate generation, physiological-input
construction, and numerical replay. It does not score, rank, select, recommend,
or deliver a basal rate.

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

## Continuous 48-hour simulation

`simulation.py` consumes only a validated `BasalCandidateInputBatch` and calls
the authoritative `bolus_optimization.physiology.predict_from_state` function.
Each candidate is advanced continuously through all 576 five-minute intervals
using its constant basal, recorded delivered boluses, and recorded
`consumed_carbs_g`. No announced carbohydrate, meal ledger, recorded replay
CGM, GRU refresh, or parameter fitting enters state propagation.

```python
from basal_optimization import simulate_candidate_batch

simulation = simulate_candidate_batch(candidate_inputs, candidate_batch_size=8)
```

The first glucose output aligns to `S + 5 minutes` and the last to `T`. All ten
state compartments carry across the 24-hour boundary without reinitialization;
the seven parameters remain fixed. Runtime settings are explicitly 70 kg,
float32, five-minute intervals, and five integration substeps. Candidate
batching bounds memory use but does not split a candidate's 576-interval state
trajectory.

Results preserve the 576 timestamp positions, partial finite predictions, the
first failing interval/substep/reason, roundoff corrections, and NaNs after a
numerical failure. State trajectories are not returned. A
`simulation_valid` result means only that the numerical validity rules passed;
it does not establish clinical safety, effectiveness, or 48-hour predictive
accuracy. No scores, ranks, selected rate, or recommendation are produced.

## Baseline glucose-fit reliability gate

`reliability.py` assesses only the candidate identified consistently by both
`baseline_candidate_id` and its baseline flag. Predictions are joined to
recorded outcomes by exact timestamp: outputs at `S + 5 minutes, ..., T` use
the 575 replay rows after `S` plus the outcome row at `T`. The initialization
value at `S` is not scored. Timestamp storage precision is normalized for
comparison without rounding, localizing, or removing timezone information.
Missing, duplicate, invalid, or late-measurement observations are reported and
prevent authorization; observations are never filled or interpolated.

The assessment reports float64 MAE, RMSE, predicted-minus-observed bias,
maximum absolute error, and counts for the full 576 outputs and both exact
288-output days, plus endpoint error. `simulation_valid` remains a numerical
status distinct from predictive reliability.

The shipped versioned configuration,
`uncalibrated_reliability_configuration_v1.json`, deliberately contains no
limits because no independently justified limits were available. It therefore
returns `criteria_not_calibrated` and `future_selection_authorized=False`.
Provisional development criteria must configure finite, positive full-window,
Day 0, and Day 1 MAE/RMSE limits; comparisons are inclusive. A pass is named
`reliable_under_experimental_criteria`, never “clinically safe.” A future
selector must refuse to select unless `future_selection_authorized` is true.

`run_development_reliability_pilot(maximum_patients=...)` provides an explicit,
bounded development-only diagnostic workflow. It deterministically chooses
complete windows without crossing patient or available continuity identifiers,
loads the data and frozen model once, excludes validation/testing patients,
and reports pooled-window distributions separately from equally weighted
per-patient distributions. It does not derive thresholds from the errors it
evaluates; callers must supply separately justified provisional criteria or
retain the uncalibrated status.

## Long-rollout diagnostics

`diagnostics.py` is a development-only, baseline-only diagnostic entry point:

```bash
python -m basal_optimization.diagnostics --maximum-development-patients 4
```

It selects at most four deterministic development patients, adds the known
development example `PadovaBaseline/adult#004` when needed, loads the dataset
and checkpoint once, and simulates only the explicitly flagged unchanged-basal
candidate. It reports cumulative errors at 2, 4, 6, 12, 24, and 48 hours plus
successive non-overlapping four-hour blocks. Every value is a slice of the same
continuous trajectory; prefixes are not reinitialized or rerun.

The diagnostic audits exact input preservation, five-minute timestamp cadence,
CGM measurement age, event-adjacent errors, initialization state and parameter
values, parameter-bound proximity, and the fixed 70 kg contract. Generated
JSON, Markdown, and plots are written under the ignored
`services/prediction/results/basal_diagnostics/` directory.

The inspected native training code establishes these important limits:

- the GRU consumes 288 completed five-minute history rows plus the current
  boundary row;
- physiological history uses only the last six hours and replaces Q1 with the
  next recorded CGM after every historical advance;
- native training supplies announced `carbs_g` to both historical and future
  physiology, whereas the current runtime intentionally supplies
  `consumed_carbs_g` to both physiological phases;
- the declared training forecast is 24 outputs, or 120 minutes, with one fixed
  parameter estimate and no future glucose correction; and
- checkpoint selection metrics are explicitly scoped to 5–60 minutes.

The 48-hour basal replay instead holds the estimate fixed for 576 outputs with
no observation correction. That is a documented extrapolation beyond the
training and checkpoint-selection horizons, not evidence of a simulator bug.
Diagnostic results do not alter the uncalibrated reliability criteria and
cannot authorize future selection.
