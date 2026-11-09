"""Discrete 24-hour arm outcomes and deterministic policy selection helpers."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


SAMPLE_MINUTES = 5
COMPLETE_SAMPLES = 288
OUTCOME_DIFFERENCE_DIRECTION = "optimized_minus_baseline"
PAIR_METRICS = (
    "time_in_range_percent", "below_70_percent", "below_54_percent",
    "above_180_percent", "above_250_percent", "mean_glucose_mg_dl",
    "glucose_sd_mg_dl", "glucose_cv_percent", "minimum_glucose_mg_dl",
    "maximum_glucose_mg_dl", "terminal_glucose_mg_dl",
    "total_delivered_bolus_u",
)

RANKING_CRITERIA = (
    ("patient_macro_delta_time_in_range_percent", "max", "time_percentage_points"),
    ("patient_macro_delta_below_54_percent", "min", "time_percentage_points"),
    ("patient_macro_delta_above_250_percent", "min", "time_percentage_points"),
    ("no_feasible_fraction", "min", "recommendation_fraction"),
    ("upper_grid_fraction", "min", "recommendation_fraction"),
    ("patient_macro_delta_total_delivered_bolus_u", "min", "bolus_u"),
)


def _finite_glucose(values) -> np.ndarray:
    glucose = np.asarray(values, dtype=np.float64)
    if glucose.ndim != 1 or len(glucose) == 0:
        raise ValueError("Outcome glucose must be a nonempty one-dimensional sequence")
    if not np.isfinite(glucose).all() or (glucose <= 0).any():
        raise ValueError("Outcome glucose must be finite and positive")
    return glucose


def calculate_discrete_outcome(
    glucose_values,
    *,
    completed_interval_count: int,
    delivered_bolus_u=(),
    complete: bool,
) -> dict:
    """Calculate outcomes from committed +5... boundaries without interpolation."""

    glucose = _finite_glucose(glucose_values)
    if isinstance(completed_interval_count, bool) or not isinstance(
        completed_interval_count, (int, np.integer)
    ):
        raise ValueError("completed_interval_count must be an integer")
    completed_interval_count = int(completed_interval_count)
    if completed_interval_count != len(glucose) or not 1 <= len(glucose) <= COMPLETE_SAMPLES:
        raise ValueError("Glucose sample count must equal committed interval count in [1, 288]")
    if complete and len(glucose) != COMPLETE_SAMPLES:
        raise ValueError("A complete outcome requires exactly 288 post-advance samples")
    insulin = np.asarray(tuple(delivered_bolus_u), dtype=np.float64)
    if insulin.ndim != 1 or (len(insulin) and (not np.isfinite(insulin).all() or (insulin < 0).any())):
        raise ValueError("Delivered boluses must be finite and nonnegative")
    mean = float(glucose.mean())
    sd = float(glucose.std(ddof=0))

    def exposure(mask):
        count = int(np.count_nonzero(mask))
        return count, count * SAMPLE_MINUTES, 100.0 * count / len(glucose)

    tir = exposure((glucose >= 70.0) & (glucose <= 180.0))
    below70 = exposure(glucose < 70.0)
    below54 = exposure(glucose < 54.0)
    above180 = exposure(glucose > 180.0)
    above250 = exposure(glucose > 250.0)
    result = {
        "outcome_label": "discrete Hovorka-simulated outcomes",
        "complete": bool(complete), "sample_count": len(glucose),
        "completed_interval_count": completed_interval_count,
        "represented_minutes": len(glucose) * SAMPLE_MINUTES,
        "threshold_interpolation": False,
        "time_in_range_count": tir[0], "time_in_range_minutes": tir[1],
        "time_in_range_percent": tir[2],
        "below_70_count": below70[0], "below_70_minutes": below70[1],
        "below_70_percent": below70[2],
        "below_54_count": below54[0], "below_54_minutes": below54[1],
        "below_54_percent": below54[2],
        "above_180_count": above180[0], "above_180_minutes": above180[1],
        "above_180_percent": above180[2],
        "above_250_count": above250[0], "above_250_minutes": above250[1],
        "above_250_percent": above250[2],
        "mean_glucose_mg_dl": mean, "glucose_sd_mg_dl": sd,
        "glucose_cv_percent": 100.0 * sd / mean,
        "minimum_glucose_mg_dl": float(glucose.min()),
        "maximum_glucose_mg_dl": float(glucose.max()),
        "terminal_glucose_mg_dl": float(glucose[-1]),
        "total_delivered_bolus_u": float(insulin.sum()) if len(insulin) else 0.0,
    }
    return result


def arm_outcomes_from_run(run) -> pd.DataFrame:
    rows = []
    for episode_row in run.episode_rows:
        arm = episode_row["arm"]
        trajectory = sorted(
            (row for row in run.trajectory_rows
             if row["arm"] == arm and row["completed_episode_intervals"] > 0),
            key=lambda row: row["completed_episode_intervals"],
        )
        committed = [
            row for row in run.input_rows
            if row["arm"] == arm and row["interval_completed"]
        ]
        complete = episode_row["status"] == "completed"
        if not trajectory:
            empty = {
                **{key: episode_row[key] for key in (
                    "episode_id", "dataset", "patient_id", "split", "arm",
                    "status", "failure_reason", "stopping_boundary",
                )},
                "complete": False, "sample_count": 0,
                "completed_interval_count": 0,
                "represented_minutes": 0,
                "total_delivered_bolus_u": 0.0,
                "recommendation_count": 0, "zero_selection_count": 0,
                "no_feasible_count": 0, "upper_grid_selection_count": 0,
                "upper_grid_selection_frequency": 0.0,
                "simulation_or_implementation_failure_count": 1,
            }
            for metric in PAIR_METRICS:
                empty.setdefault(metric, np.nan)
            rows.append(empty)
            continue
        outcome = calculate_discrete_outcome(
            [row["glucose_mg_dl"] for row in trajectory],
            completed_interval_count=len(committed),
            delivered_bolus_u=[row["delivered_bolus_u"] for row in committed],
            complete=complete,
        )
        recommendations = [
            row for row in run.recommendation_rows if row["arm"] == arm
        ]
        outcome.update({
            "recommendation_count": len(recommendations),
            "zero_selection_count": sum(
                row["status"] == "selected" and row["selected_dose_u"] == 0
                for row in recommendations
            ),
            "no_feasible_count": sum(
                row["status"] == "no_feasible_recommendation"
                for row in recommendations
            ),
            "upper_grid_selection_count": sum(
                bool(row["selected_at_upper_grid_boundary"])
                for row in recommendations
            ),
            "upper_grid_selection_frequency": (
                sum(bool(row["selected_at_upper_grid_boundary"]) for row in recommendations)
                / len(recommendations) if recommendations else 0.0
            ),
            "simulation_or_implementation_failure_count": int(not complete),
        })
        rows.append({
            **{key: episode_row[key] for key in (
                "episode_id", "dataset", "patient_id", "split", "arm",
                "status", "failure_reason", "stopping_boundary",
            )},
            **outcome,
        })
    return pd.DataFrame(rows)


def initialization_failure_arm_outcomes(definition, failure_reason: str) -> pd.DataFrame:
    """Represent a requested episode that failed before either arm was created."""

    rows = []
    for arm in ("recorded_bolus_baseline", "optimized_bolus"):
        row = {
            "episode_id": definition.episode_id, "dataset": definition.dataset,
            "patient_id": definition.patient_id, "split": definition.split,
            "arm": arm, "status": "failed_initialization",
            "failure_reason": str(failure_reason),
            "stopping_boundary": definition.start_timestamp,
            "complete": False, "sample_count": 0,
            "completed_interval_count": 0, "represented_minutes": 0,
            "threshold_interpolation": False,
            "total_delivered_bolus_u": 0.0,
            "recommendation_count": 0, "zero_selection_count": 0,
            "no_feasible_count": 0, "upper_grid_selection_count": 0,
            "upper_grid_selection_frequency": 0.0,
            "simulation_or_implementation_failure_count": 1,
            "maximum_relative_parameter_change": np.nan,
        }
        for metric in PAIR_METRICS:
            row.setdefault(metric, np.nan)
        rows.append(row)
    return pd.DataFrame(rows)


def paired_outcomes(arm_outcomes: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for episode_id, group in arm_outcomes.groupby("episode_id", sort=True):
        by_arm = {row.arm: row for row in group.itertuples(index=False)}
        baseline = by_arm.get("recorded_bolus_baseline")
        optimized = by_arm.get("optimized_bolus")
        complete = bool(
            baseline is not None and optimized is not None
            and baseline.complete and optimized.complete
            and baseline.sample_count == COMPLETE_SAMPLES
            and optimized.sample_count == COMPLETE_SAMPLES
        )
        template = baseline if baseline is not None else optimized
        row = {
            "episode_id": episode_id, "dataset": template.dataset,
            "patient_id": template.patient_id, "split": template.split,
            "complete_pair": complete,
            "difference_direction": OUTCOME_DIFFERENCE_DIRECTION,
            "baseline_status": baseline.status if baseline is not None else "missing",
            "optimized_status": optimized.status if optimized is not None else "missing",
            "baseline_failure_reason": baseline.failure_reason if baseline is not None else "missing",
            "optimized_failure_reason": optimized.failure_reason if optimized is not None else "missing",
        }
        for metric in PAIR_METRICS:
            row[f"baseline_{metric}"] = getattr(baseline, metric, np.nan) if baseline is not None else np.nan
            row[f"optimized_{metric}"] = getattr(optimized, metric, np.nan) if optimized is not None else np.nan
            row[f"delta_{metric}"] = (
                getattr(optimized, metric) - getattr(baseline, metric)
                if complete else np.nan
            )
        rows.append(row)
    return pd.DataFrame(rows)


def patient_aggregates(pairs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (dataset, patient_id, split), group in pairs.groupby(
        ["dataset", "patient_id", "split"], sort=True
    ):
        complete = group[group["complete_pair"]]
        row = {
            "dataset": dataset, "patient_id": patient_id, "split": split,
            "attempted_episode_count": len(group),
            "complete_pair_count": len(complete),
            "incomplete_pair_count": len(group) - len(complete),
        }
        for metric in PAIR_METRICS:
            row[f"mean_delta_{metric}"] = (
                float(complete[f"delta_{metric}"].mean()) if len(complete) else np.nan
            )
        rows.append(row)
    return pd.DataFrame(rows)


def patient_macro(patient_frame: pd.DataFrame) -> dict:
    if len(patient_frame) == 0:
        raise ValueError("Patient macro aggregation requires patients")
    result = {
        "patient_count": len(patient_frame),
        "attempted_episode_count": int(patient_frame["attempted_episode_count"].sum()),
        "complete_pair_count": int(patient_frame["complete_pair_count"].sum()),
        "incomplete_pair_count": int(patient_frame["incomplete_pair_count"].sum()),
    }
    for metric in PAIR_METRICS:
        values = patient_frame[f"mean_delta_{metric}"]
        result[f"patient_macro_delta_{metric}"] = float(values.mean())
    return result


def acceptance_and_rank_record(
    configuration_id: str,
    macro: dict,
    patient_frame: pd.DataFrame,
    *,
    failure_count: int,
    recommendation_count: int,
    no_feasible_count: int,
    upper_grid_count: int,
    criteria: dict,
) -> dict:
    no_feasible_fraction = no_feasible_count / recommendation_count if recommendation_count else 0.0
    upper_fraction = upper_grid_count / recommendation_count if recommendation_count else 0.0
    worst_low54 = float(patient_frame["mean_delta_below_54_percent"].max())
    worst_low70 = float(patient_frame["mean_delta_below_70_percent"].max())
    gates = {
        "zero_failures": failure_count <= criteria["implementation_or_numerical_failures"],
        "complete_pair_fraction": (
            macro["complete_pair_count"] / macro["attempted_episode_count"]
            >= criteria["complete_pair_fraction"]
        ),
        "macro_below_54": macro["patient_macro_delta_below_54_percent"]
        <= criteria["patient_macro_delta_below_54_percentage_points_max"],
        "macro_below_70": macro["patient_macro_delta_below_70_percent"]
        <= criteria["patient_macro_delta_below_70_percentage_points_max"],
        "worst_patient_below_54": worst_low54
        <= criteria["worst_patient_delta_below_54_percentage_points_max"],
        "worst_patient_below_70": worst_low70
        <= criteria["worst_patient_delta_below_70_percentage_points_max"],
        "no_feasible_fraction": no_feasible_fraction
        <= criteria["no_feasible_recommendation_fraction_max"],
    }
    return {
        "configuration_id": configuration_id, "acceptable": all(gates.values()),
        "acceptance_gates": gates, "failure_count": failure_count,
        "recommendation_count": recommendation_count,
        "no_feasible_count": no_feasible_count,
        "no_feasible_fraction": no_feasible_fraction,
        "upper_grid_count": upper_grid_count,
        "upper_grid_fraction": upper_fraction,
        "worst_patient_delta_below_54_percent": worst_low54,
        "worst_patient_delta_below_70_percent": worst_low70,
        **macro,
    }


def deterministic_policy_order(
    records: list[dict], comparison_tolerances: dict | None = None,
) -> list[dict]:
    """Rank acceptable policies using global tolerance tiers, independent of input order.

    At each criterion, every remaining candidate within the declared absolute
    tolerance of the best value advances to the next criterion.  One winner is
    selected lexicographically after all numeric criteria, removed, and the
    process repeats to produce a complete deterministic order.  This avoids the
    input-order dependence and non-transitivity of pairwise fuzzy comparators.
    """

    tolerances = {
        "time_percentage_points": 0.0,
        "recommendation_fraction": 0.0,
        "bolus_u": 0.0,
        **(comparison_tolerances or {}),
    }
    for name, value in tolerances.items():
        if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
            raise ValueError(f"Ranking tolerance {name} must be a finite nonnegative number")
        if not math.isfinite(float(value)) or float(value) < 0:
            raise ValueError(f"Ranking tolerance {name} must be a finite nonnegative number")
    remaining = [record for record in records if record["acceptable"]]
    identifiers = [str(record["configuration_id"]) for record in remaining]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Acceptable configuration IDs must be unique")
    ordered = []
    while remaining:
        tier = list(remaining)
        for field, direction, tolerance_name in RANKING_CRITERIA:
            values = [float(record[field]) for record in tier]
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"Ranking field {field} must be finite")
            best = max(values) if direction == "max" else min(values)
            tolerance = float(tolerances[tolerance_name])
            tier = [
                record for record in tier
                if abs(float(record[field]) - best) <= tolerance
            ]
        winner = min(tier, key=lambda record: str(record["configuration_id"]))
        ordered.append(winner)
        remaining = [record for record in remaining if record is not winner]
    return ordered


def verify_manifest_hashes(manifest_path: str | Path, *, root: str | Path = ".") -> None:
    manifest = json.loads(Path(manifest_path).read_text())
    root = Path(root)
    mismatches = []
    for relative, expected in manifest["required_hashes"].items():
        path = Path(relative)
        if not path.is_absolute():
            path = root / path
        if not path.exists():
            mismatches.append(f"missing:{relative}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            mismatches.append(f"hash_mismatch:{relative}")
    if mismatches:
        raise ValueError("Frozen manifest verification failed: " + ", ".join(mismatches))
