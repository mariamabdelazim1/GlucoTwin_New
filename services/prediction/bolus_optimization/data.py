"""Data loading rules specific to bolus optimization."""

from pathlib import Path

import numpy as np
import pandas as pd

from .configuration import (
    MODEL_FEATURES,
    PHYSIOLOGICAL_CARBOHYDRATE_FEATURE,
    SAMPLE_INTERVAL_MINUTES,
)


def read_optimization_data(path: str | Path):
    """Load complete five-minute intervals without changing model features.

    A partial terminal interval cannot seed or belong to a four-hour forecast,
    so it is reported and excluded. A partial interval inside a patient timeline
    is rejected because dropping it would create an unmodelled gap.
    """

    data = pd.read_parquet(path)
    raw_rows = len(data)
    numeric_inputs = [*MODEL_FEATURES, PHYSIOLOGICAL_CARBOHYDRATE_FEATURE]
    needed = [
        "dataset",
        "patient_id",
        "split",
        "timestamp",
        "source_minute_count",
        *numeric_inputs,
    ]
    missing = set(needed).difference(data.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    data = data.sort_values(["dataset", "patient_id", "timestamp"]).reset_index(drop=True)

    excluded = []
    counts = pd.to_numeric(data["source_minute_count"], errors="coerce").to_numpy(dtype=float)
    valid_counts = (
        np.isfinite(counts)
        & np.equal(counts, np.floor(counts))
        & (counts >= 1)
        & (counts <= SAMPLE_INTERVAL_MINUTES)
    )
    if not valid_counts.all():
        invalid = data.loc[
            ~valid_counts,
            ["dataset", "patient_id", "timestamp", "source_minute_count"],
        ]
        raise ValueError(
            "source_minute_count must contain finite integers from 1 through 5: "
            f"{invalid.to_dict('records')}"
        )
    partial = data["source_minute_count"].lt(SAMPLE_INTERVAL_MINUTES)
    if partial.any():
        group_last = data.groupby(["dataset", "patient_id"])["timestamp"].transform("max")
        internal = partial & data["timestamp"].ne(group_last)
        if internal.any():
            rows = data.loc[internal, ["dataset", "patient_id", "timestamp"]]
            raise ValueError(f"Partial internal intervals are unsupported: {rows.to_dict('records')}")
        excluded = data.loc[
            partial,
            ["dataset", "patient_id", "split", "timestamp", "source_minute_count"],
        ].astype({"timestamp": "string"}).to_dict("records")
        data = data.loc[~partial].reset_index(drop=True)

    if data[needed].isna().any().any() or not np.isfinite(data[numeric_inputs].to_numpy()).all():
        raise ValueError("Missing or nonfinite optimization input data")
    if (data[numeric_inputs].to_numpy() < 0).any() or (data["cgm_mg_dl"] <= 0).any():
        raise ValueError("Invalid negative inputs or nonpositive CGM")
    if data.duplicated(["dataset", "patient_id", "timestamp"]).any():
        raise ValueError("Duplicate timestamps")

    labels = {}
    for key, group in data.groupby(["dataset", "patient_id"]):
        if group["split"].nunique() != 1:
            raise ValueError(f"Patient crosses splits: {key}")
        labels[str(key)] = group["split"].iloc[0]
        if not group["timestamp"].diff().dropna().eq(pd.Timedelta(minutes=5)).all():
            raise ValueError(f"Patient has gaps: {key}")

    audit = {
        "raw_rows": raw_rows,
        "complete_interval_rows": len(data),
        "source_minute_count_validated_before_filtering": True,
        "source_minute_count_contract": "finite integer in [1, 5]",
        "excluded_partial_terminal_intervals": excluded,
    }
    return data, labels, audit
