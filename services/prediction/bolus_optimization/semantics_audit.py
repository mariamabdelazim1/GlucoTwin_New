"""Audit split integrity, timing, units, and meal-flow semantics.

Run from the project root:
python -m bolus_optimization.semantics_audit model_ready_5min_cleaned.parquet
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

from final_model_adapter import sha256

from .configuration import DEFAULT_OUTPUT_DIRECTORY, SAMPLE_INTERVAL_MINUTES
from .data import read_optimization_data


AUDIT_COLUMNS = (
    "dataset",
    "patient_id",
    "split",
    "timestamp",
    "cgm_mg_dl",
    "cgm_measurement_timestamp",
    "carbs_g",
    "consumed_carbs_g",
    "basal_rate_u_per_hour",
    "bolus_u",
    "source_minute_count",
)


def _quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {key: None for key in ("min", "p50", "p90", "p99", "max")}
    array = np.asarray(values, dtype=float)
    return {
        "min": float(array.min()),
        "p50": float(np.quantile(array, 0.50)),
        "p90": float(np.quantile(array, 0.90)),
        "p99": float(np.quantile(array, 0.99)),
        "max": float(array.max()),
    }


def audit_meal_flow(data: pd.DataFrame, tolerance: float = 1e-7) -> dict:
    """FIFO-match consumed grams to prior/current announced meal buckets.

    The matching is an audit device, not a new physiological model. It allows
    consumption to continue across rows and calendar days and never treats an
    announcement itself as carbohydrate ingestion.
    """

    completed = []
    unmatched_consumption_g = 0.0
    unmatched_consumption_rows = 0
    open_meals = []
    for (dataset, patient_id), group in data.groupby(["dataset", "patient_id"], sort=False):
        queue: deque[dict] = deque()
        event_rows = group.loc[
            group["carbs_g"].gt(tolerance) | group["consumed_carbs_g"].gt(tolerance),
            ["timestamp", "carbs_g", "consumed_carbs_g"],
        ]
        for row in event_rows.itertuples(index=False):
            timestamp = pd.Timestamp(row.timestamp)
            announced = float(row.carbs_g)
            consumed = float(row.consumed_carbs_g)
            if announced > tolerance:
                queue.append(
                    {
                        "dataset": str(dataset),
                        "patient_id": str(patient_id),
                        "announcement_timestamp": timestamp,
                        "announced_g": announced,
                        "remaining_g": announced,
                        "consumed_g": 0.0,
                        "first_consumption_timestamp": None,
                        "last_consumption_timestamp": None,
                        "consumption_rows": set(),
                        "crossed_day_boundary": False,
                        "consumed_after_announcement_day_g": 0.0,
                    }
                )
            amount = consumed
            row_was_unmatched = False
            while amount > tolerance:
                if not queue:
                    unmatched_consumption_g += amount
                    row_was_unmatched = True
                    break
                meal = queue[0]
                allocated = min(amount, meal["remaining_g"])
                meal["remaining_g"] -= allocated
                meal["consumed_g"] += allocated
                meal["consumption_rows"].add(timestamp)
                if meal["first_consumption_timestamp"] is None:
                    meal["first_consumption_timestamp"] = timestamp
                meal["last_consumption_timestamp"] = timestamp
                if timestamp.normalize() != meal["announcement_timestamp"].normalize():
                    meal["crossed_day_boundary"] = True
                    meal["consumed_after_announcement_day_g"] += allocated
                amount -= allocated
                if meal["remaining_g"] <= tolerance:
                    meal["remaining_g"] = 0.0
                    completed.append(queue.popleft())
            if row_was_unmatched:
                unmatched_consumption_rows += 1
        open_meals.extend(queue)

    first_lags = []
    completion_lags = []
    consumption_row_counts = []
    for meal in completed:
        first_lags.append(
            (meal["first_consumption_timestamp"] - meal["announcement_timestamp"]).total_seconds()
            / 60.0
        )
        completion_lags.append(
            (meal["last_consumption_timestamp"] - meal["announcement_timestamp"]).total_seconds()
            / 60.0
        )
        consumption_row_counts.append(len(meal["consumption_rows"]))

    crossing = [meal for meal in completed if meal["crossed_day_boundary"]]
    return {
        "matching_method": "FIFO gram conservation within each patient; current/prior announcements only",
        "announcement_buckets": int((data["carbs_g"] > tolerance).sum()),
        "completed_announcement_buckets": len(completed),
        "unconsumed_announcement_buckets": len(open_meals),
        "unconsumed_announced_g": float(sum(meal["remaining_g"] for meal in open_meals)),
        "unmatched_consumption_rows": unmatched_consumption_rows,
        "unmatched_consumption_g": float(unmatched_consumption_g),
        "first_consumption_lag_minutes": _quantiles(first_lags),
        "completion_lag_minutes": _quantiles(completion_lags),
        "consumption_rows_per_announcement": _quantiles(consumption_row_counts),
        "announcements_with_consumption_across_day_boundary": len(crossing),
        "grams_consumed_after_announcement_day": float(
            sum(meal["consumed_after_announcement_day_g"] for meal in crossing)
        ),
    }


def carbohydrate_conservation_checks(
    data: pd.DataFrame, meal_flow: dict, tolerance: float = 1e-7
) -> dict[str, bool]:
    """Return the required carbohydrate-integrity gate results."""

    totals = data.groupby(["dataset", "patient_id"])[
        ["carbs_g", "consumed_carbs_g"]
    ].sum()
    return {
        "global_announced_equals_consumed": bool(
            abs(float(data["carbs_g"].sum() - data["consumed_carbs_g"].sum())) <= tolerance
        ),
        "every_patient_announced_equals_consumed": bool(
            (totals["carbs_g"] - totals["consumed_carbs_g"]).abs().le(tolerance).all()
        ),
        "no_unmatched_consumption": bool(
            meal_flow["unmatched_consumption_g"] <= tolerance
            and meal_flow["unmatched_consumption_rows"] == 0
        ),
        "no_incomplete_announcements": bool(
            meal_flow["unconsumed_announced_g"] <= tolerance
            and meal_flow["unconsumed_announcement_buckets"] == 0
        ),
    }


def _provenance_evidence(generation_code: Path | None, data_dictionary: Path | None) -> dict:
    evidence = {
        "generation_code": None,
        "data_dictionary": None,
        "five_minute_bucket_start_verified": False,
        "within_bucket_event_minute_preserved_in_supplied_parquet": False,
        "meal_field_mapping_and_aggregation_verified": False,
        "insulin_interval_aggregation_verified": False,
        "generation_code_supports_bucket_aggregation": False,
        "data_dictionary_supports_half_open_start_labels": False,
    }
    if generation_code is not None:
        text = generation_code.read_text()
        evidence["generation_code"] = {
            "path": str(generation_code.resolve()),
            "sha256": sha256(generation_code),
        }
        evidence["generation_code_supports_bucket_aggregation"] = (
            "time_bucket(INTERVAL '5 minutes', timestamp)" in text
            and "sum(carbs_g)" in text
            and "sum(consumed_carbs_g)" in text
        )
        evidence["meal_field_mapping_and_aggregation_verified"] = all(
            token in text
            for token in (
                "meal_occurrence_g::DOUBLE AS carbs_g",
                "meal_consumed_g::DOUBLE AS consumed_carbs_g",
                "sum(carbs_g) AS carbs_g",
                "sum(consumed_carbs_g) AS consumed_carbs_g",
            )
        )
        evidence["insulin_interval_aggregation_verified"] = (
            "sum(bolus_u) AS bolus_u" in text
            and "avg(basal_rate_u_per_hour) AS basal_rate_u_per_hour" in text
        )
    if data_dictionary is not None:
        text = data_dictionary.read_text()
        evidence["data_dictionary"] = {
            "path": str(data_dictionary.resolve()),
            "sha256": sha256(data_dictionary),
        }
        evidence["data_dictionary_supports_half_open_start_labels"] = bool(
            "timestamp` is the start of a half-open input interval" in text
            and "[timestamp, timestamp + 5 minutes)" in text
        )
    evidence["five_minute_bucket_start_verified"] = bool(
        evidence["generation_code_supports_bucket_aggregation"]
        and evidence["data_dictionary_supports_half_open_start_labels"]
    )
    return evidence


def _bundle_evidence(
    out: Path,
    evidence: dict,
    generation_code: Path | None,
    data_dictionary: Path | None,
) -> None:
    """Copy exact provenance inputs into the local review bundle."""

    evidence_dir = out / "review_bundle" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for key, source, name in (
        ("generation_code", generation_code, "export_padova_forecasting_dataset.py"),
        ("data_dictionary", data_dictionary, "DATA_DICTIONARY.md"),
    ):
        destination = evidence_dir / name
        if source is None:
            if destination.exists():
                destination.unlink()
            continue
        shutil.copyfile(source, destination)
        if sha256(source) != sha256(destination):
            raise RuntimeError(f"Review-bundle evidence copy hash mismatch: {source}")
        evidence[key]["review_bundle_copy"] = str(destination.resolve())


def _markdown(payload: dict) -> str:
    validation = payload["validation"]
    meals = payload["meal_semantics"]
    totals = meals["carbohydrate_totals"]
    matching = meals["announcement_consumption_matching"]
    units = payload["insulin_units"]
    convention = payload["timing_convention"]
    evidence = convention["provenance_evidence"]
    if evidence["five_minute_bucket_start_verified"]:
        provenance_text = (
            "The supplied export code and data dictionary verify that `timestamp` labels "
            "the start of a half-open five-minute bucket."
        )
    elif evidence["generation_code"] is not None or evidence["data_dictionary"] is not None:
        provenance_text = (
            "Only partial provenance evidence was supplied, so the half-open start-label "
            "convention is not fully verified by this audit."
        )
    else:
        provenance_text = (
            "No export code or data dictionary was supplied to this run, so the row-label "
            "convention is unverified provenance."
        )
    return f"""# Step 2 — Meal semantics and timing audit

Dataset SHA-256: `{payload['dataset']['sha256']}`

## Outcome

- Required audit result: **{'PASS' if payload['audit_result']['overall_pass'] else 'FAIL'}** ({payload['audit_result']['required_checks_passed']}/{payload['audit_result']['required_checks_total']} checks passed)
- Patient-disjoint splits: **{validation['patient_disjoint_splits']}**
- Exact five-minute sampling after documented terminal-partial exclusion: **{validation['exact_five_minute_sampling']}**
- Duplicate patient timestamps: **{validation['duplicate_patient_timestamps']}**
- Missing required values: **{validation['missing_required_values']}**
- Total announced carbohydrate: **{totals['announced_g']:.1f} g**
- Total consumed carbohydrate: **{totals['consumed_g']:.1f} g**
- True unmatched consumption: **{matching['unmatched_consumption_g']:.1f} g**
- Unconsumed announced carbohydrate: **{matching['unconsumed_announced_g']:.1f} g**
- Announcements whose consumption crosses midnight: **{matching['announcements_with_consumption_across_day_boundary']}**

## Semantics used by optimization

- `carbs_g` is a meal announcement. It triggers and informs a decision; it is not added to the physiological gut input.
- `consumed_carbs_g` is the carbohydrate amount entering the ongoing physiological simulation for that interval.
- `basal_rate_u_per_hour` is a U/hour rate applied as each interval arrives.
- `bolus_u` is delivered U summed in the interval and is the recorded-bolus baseline input.
- An announcement is never counted as an additional ingestion event.

There are {matching['announcement_buckets']} announced-meal buckets and {meals['positive_consumption_rows']} positive-consumption rows. Of those consumption rows, {meals['continuation_consumption_rows_without_same_row_announcement']} have no same-row announcement; the FIFO conservation audit matches these as continued consumption of an earlier announcement rather than as unmatched meals.

## Units

Observed basal rates range from {units['basal_rate_u_per_hour']['min']} to {units['basal_rate_u_per_hour']['max']} U/hour. Recorded positive boluses range from {units['bolus_u']['positive_min']} to {units['bolus_u']['positive_max']} U. The existing Hovorka solver converts basal U/hour to mU/min with `*1000/60` and bolus U to an interval-start mU impulse with `*1000`.

## Timing convention

{convention['statement']}

{provenance_text} The supplied five-minute table does not retain the original minute inside each bucket for meal and insulin events. Applying the aggregated event as an impulse at the bucket start therefore remains an inherited solver assumption.

Research audit only; this does not establish clinical dosing safety.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data")
    parser.add_argument("--out", default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--generation-code", type=Path)
    parser.add_argument("--data-dictionary", type=Path)
    args = parser.parse_args()

    data_path = Path(args.data)
    raw = pd.read_parquet(data_path)
    missing_columns = sorted(set(AUDIT_COLUMNS).difference(raw.columns))
    if missing_columns:
        raise ValueError(f"Missing Step 2 audit columns: {missing_columns}")
    data, patient_splits, loader_audit = read_optimization_data(data_path)

    patient_membership = (
        data.groupby(["dataset", "patient_id"])["split"].nunique().rename("split_count")
    )
    split_patients = {
        str(split): int(part[["dataset", "patient_id"]].drop_duplicates().shape[0])
        for split, part in data.groupby("split")
    }
    sampling_deltas = data.groupby(["dataset", "patient_id"])["timestamp"].diff().dropna()
    duplicate_count = int(data.duplicated(["dataset", "patient_id", "timestamp"]).sum())
    missing_counts = {column: int(raw[column].isna().sum()) for column in AUDIT_COLUMNS}
    nonfinite_counts = {
        column: int((~np.isfinite(raw[column].to_numpy(dtype=float))).sum())
        for column in (
            "cgm_mg_dl",
            "carbs_g",
            "consumed_carbs_g",
            "basal_rate_u_per_hour",
            "bolus_u",
        )
    }

    meal_flow = audit_meal_flow(data)
    carbohydrate_checks = carbohydrate_conservation_checks(data, meal_flow)
    announced = data["carbs_g"]
    consumed = data["consumed_carbs_g"]
    announcement_rows = announced.gt(0)
    consumption_rows = consumed.gt(0)
    patient_totals = (
        data.groupby(["dataset", "patient_id", "split"], as_index=False)
        .agg(announced_g=("carbs_g", "sum"), consumed_g=("consumed_carbs_g", "sum"))
    )
    patient_totals["consumed_minus_announced_g"] = (
        patient_totals["consumed_g"] - patient_totals["announced_g"]
    )

    basal = data["basal_rate_u_per_hour"]
    bolus = data["bolus_u"]
    positive_bolus = bolus[bolus.gt(0)]
    evidence = _provenance_evidence(args.generation_code, args.data_dictionary)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    _bundle_evidence(out, evidence, args.generation_code, args.data_dictionary)
    payload = {
        "scope": "Step 2 meal semantics and timing audit",
        "dataset": {
            "path": str(data_path.resolve()),
            "sha256": sha256(data_path),
            **loader_audit,
        },
        "validation": {
            "patient_disjoint_splits": bool(patient_membership.eq(1).all()),
            "patients_in_multiple_splits": int(patient_membership.gt(1).sum()),
            "patients_by_split": split_patients,
            "exact_five_minute_sampling": bool(
                sampling_deltas.eq(pd.Timedelta(minutes=SAMPLE_INTERVAL_MINUTES)).all()
            ),
            "non_five_minute_deltas": int(
                sampling_deltas.ne(pd.Timedelta(minutes=SAMPLE_INTERVAL_MINUTES)).sum()
            ),
            "duplicate_patient_timestamps": duplicate_count,
            "missing_required_values": int(sum(missing_counts.values())),
            "missing_values_by_column": missing_counts,
            "nonfinite_values_by_numeric_column": nonfinite_counts,
        },
        "meal_semantics": {
            "carbs_g": "announcement used to trigger/inform a decision; never added as ingestion",
            "consumed_carbs_g": "grams entering the physiological simulation in this interval",
            "announcement_rows": int(announcement_rows.sum()),
            "positive_consumption_rows": int(consumption_rows.sum()),
            "same_row_announcement_and_consumption": int((announcement_rows & consumption_rows).sum()),
            "continuation_consumption_rows_without_same_row_announcement": int(
                (~announcement_rows & consumption_rows).sum()
            ),
            "carbohydrate_totals": {
                "announced_g": float(announced.sum()),
                "consumed_g": float(consumed.sum()),
                "consumed_minus_announced_g": float(consumed.sum() - announced.sum()),
                "patients_with_nonzero_total_difference_at_1e_7_g": int(
                    patient_totals["consumed_minus_announced_g"].abs().gt(1e-7).sum()
                ),
            },
            "announcement_consumption_matching": meal_flow,
            "double_counting_rule": "Only consumed_carbs_g enters gut input; carbs_g is metadata/decision input",
        },
        "insulin_units": {
            "basal_rate_u_per_hour": {
                "meaning": "U/hour rate applied for each arriving dataset interval",
                "min": float(basal.min()),
                "max": float(basal.max()),
                "negative_rows": int(basal.lt(0).sum()),
                "solver_conversion": "basal_rate_u_per_hour * 1000 / 60 -> mU/min",
            },
            "bolus_u": {
                "meaning": "recorded delivered bolus U summed within the interval; baseline arm input",
                "positive_rows": int(positive_bolus.size),
                "positive_min": float(positive_bolus.min()),
                "positive_max": float(positive_bolus.max()),
                "total_u": float(bolus.sum()),
                "negative_rows": int(bolus.lt(0).sum()),
                "solver_conversion": "bolus_u * 1000 -> interval-start mU impulse",
            },
        },
        "timing_convention": {
            "statement": (
                "Rows represent [timestamp, timestamp + 5 minutes). The solver applies basal over "
                "that interval and treats aggregated meal/bolus events as occurring at timestamp."
            ),
            "provenance_evidence": evidence,
            "interval_start_bucket_label_verified": evidence["five_minute_bucket_start_verified"],
            "interval_start_impulse_application": "assumption",
            "reason": (
                "The five-minute parquet does not retain each event's source minute within its bucket; "
                "the existing solver applies the aggregate at the bucket start."
            ),
        },
    }
    integrity_checks = {
        "patient_disjoint_splits": payload["validation"]["patient_disjoint_splits"],
        "exact_five_minute_sampling": payload["validation"]["exact_five_minute_sampling"],
        "no_duplicate_patient_timestamps": duplicate_count == 0,
        "no_missing_required_values": payload["validation"]["missing_required_values"] == 0,
        "no_nonfinite_numeric_values": sum(nonfinite_counts.values()) == 0,
        "source_minute_count_validated_before_filtering": loader_audit[
            "source_minute_count_validated_before_filtering"
        ],
        "no_negative_basal_or_bolus": bool(basal.ge(0).all() and bolus.ge(0).all()),
        **carbohydrate_checks,
    }
    payload["audit_result"] = {
        "required_checks": integrity_checks,
        "required_checks_passed": sum(integrity_checks.values()),
        "required_checks_total": len(integrity_checks),
        "overall_pass": all(integrity_checks.values()),
    }

    json_path = out / "step2_semantics_audit.json"
    markdown_path = out / "step2_semantics_audit.md"
    totals_path = out / "step2_patient_carbohydrate_totals.csv"
    json_path.write_text(json.dumps(payload, indent=2) + "\n")
    markdown_path.write_text(_markdown(payload))
    patient_totals.to_csv(totals_path, index=False)

    bundle = out / "review_bundle"
    reports = []
    for source in (
        out / "step1_audit.json",
        json_path,
        markdown_path,
        totals_path,
    ):
        if source.exists():
            destination = bundle / source.name
            shutil.copyfile(source, destination)
            reports.append(
                {
                    "path": str(destination.resolve()),
                    "sha256": sha256(destination),
                }
            )
    evidence_files = sorted((bundle / "evidence").glob("*"))
    manifest = {
        "reports": reports,
        "evidence": [
            {"path": str(path.resolve()), "sha256": sha256(path)} for path in evidence_files
        ],
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json_path)
    if not payload["audit_result"]["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
