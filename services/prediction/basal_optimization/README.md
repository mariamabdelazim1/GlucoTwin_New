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
windows, the recorded varying basal trajectory, named seven-parameter and
ten-state tensors, model/checkpoint provenance, and independent cloning for a
later candidate simulator.
