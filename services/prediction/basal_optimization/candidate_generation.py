"""Generate constant basal-rate candidates without simulating or ranking them."""

from __future__ import annotations

import hashlib
import json
import numbers
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .preparation import PatientIdentity, PreparedBasalSnapshot, REPLAY_INTERVALS


BASELINE_CONSTANCY_ABSOLUTE_TOLERANCE_U_PER_HOUR = 1e-9
EXAMPLE_CONFIGURATION_PATH = Path(__file__).with_name(
    "example_candidate_configuration_v1.json"
)


def _finite_number(value: object, name: str, *, positive: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be numeric and not Boolean")
    result = float(value)
    if not np.isfinite(result) or result < 0 or (positive and result <= 0):
        qualifier = "strictly positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be finite and {qualifier}")
    return result


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Integral):
        raise ValueError(f"{name} must be a positive integer")
    result = int(value)
    if result <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return result


def _decimal(value: float, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} cannot be represented as a decimal") from None
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True)
class BasalSearchConfiguration:
    configuration_version: str
    maximum_decrease_u_per_hour: float
    maximum_increase_u_per_hour: float
    absolute_minimum_u_per_hour: float
    absolute_maximum_u_per_hour: float
    increment_u_per_hour: float
    maximum_candidate_count: int
    intended_use: str

    def __post_init__(self) -> None:
        if not isinstance(self.configuration_version, str) or not self.configuration_version.strip():
            raise ValueError("configuration_version must be a nonempty string")
        if not isinstance(self.intended_use, str) or not self.intended_use.strip():
            raise ValueError("intended_use must be a nonempty string")
        for name in (
            "maximum_decrease_u_per_hour",
            "maximum_increase_u_per_hour",
            "absolute_minimum_u_per_hour",
            "absolute_maximum_u_per_hour",
        ):
            object.__setattr__(self, name, _finite_number(getattr(self, name), name))
        object.__setattr__(
            self,
            "increment_u_per_hour",
            _finite_number(self.increment_u_per_hour, "increment_u_per_hour", positive=True),
        )
        object.__setattr__(
            self,
            "maximum_candidate_count",
            _positive_integer(self.maximum_candidate_count, "maximum_candidate_count"),
        )
        if self.absolute_minimum_u_per_hour > self.absolute_maximum_u_per_hour:
            raise ValueError(
                "absolute_minimum_u_per_hour cannot exceed absolute_maximum_u_per_hour"
            )


def configuration_hash(configuration: BasalSearchConfiguration) -> str:
    if not isinstance(configuration, BasalSearchConfiguration):
        raise TypeError("configuration must be a BasalSearchConfiguration")
    payload = json.dumps(asdict(configuration), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def load_search_configuration(path: str | Path) -> tuple[BasalSearchConfiguration, str]:
    """Load an explicit basal search document and return its canonical hash."""

    resolved = Path(path)
    payload: Any = json.loads(resolved.read_text())
    if not isinstance(payload, Mapping):
        raise ValueError("Basal search configuration must be a JSON object")
    configuration = BasalSearchConfiguration(**payload)
    return configuration, configuration_hash(configuration)


@dataclass(frozen=True)
class BasalRateCandidate:
    candidate_id: str
    rate_u_per_hour: float
    is_recorded_baseline: bool


@dataclass(frozen=True)
class BasalCandidateSet:
    identity: PatientIdentity
    decision_timestamp: pd.Timestamp
    replay_start_timestamp: pd.Timestamp
    replay_end_timestamp: pd.Timestamp
    replay_interval_count: int
    baseline_rate_u_per_hour: float
    baseline_reference: str
    baseline_constancy_absolute_tolerance_u_per_hour: float
    effective_lower_u_per_hour: float
    effective_upper_u_per_hour: float
    candidates: tuple[BasalRateCandidate, ...]
    baseline_candidate_id: str
    configuration_version: str
    configuration_hash: str
    candidate_count: int


def extract_constant_baseline_rate(
    snapshot: PreparedBasalSnapshot,
    *,
    tolerance_u_per_hour: float = BASELINE_CONSTANCY_ABSOLUTE_TOLERANCE_U_PER_HOUR,
) -> float:
    """Return the first recorded replay rate after verifying a constant baseline."""

    tolerance = _finite_number(tolerance_u_per_hour, "tolerance_u_per_hour")
    replay = snapshot.replay_intervals
    if len(replay) != REPLAY_INTERVALS:
        raise ValueError(
            f"Prepared replay must contain exactly {REPLAY_INTERVALS} intervals; "
            f"found {len(replay)}"
        )
    column = "basal_rate_u_per_hour"
    if column not in replay.columns:
        raise ValueError(f"Prepared replay is missing {column}")
    raw = replay[column]
    boolean = raw.map(lambda value: isinstance(value, (bool, np.bool_)))
    if boolean.any():
        locations = replay.loc[boolean, "timestamp"].astype(str).head(5).tolist()
        raise ValueError(f"{column} contains Boolean values at {locations}")
    numeric_types = raw.map(lambda value: isinstance(value, numbers.Real))
    if not numeric_types.all():
        locations = replay.loc[~numeric_types, "timestamp"].astype(str).head(5).tolist()
        raise ValueError(f"{column} contains missing or nonnumeric values at {locations}")
    values = raw.to_numpy(dtype=np.float64, copy=True)
    if not np.isfinite(values).all():
        locations = replay.loc[~np.isfinite(values), "timestamp"].astype(str).head(5).tolist()
        raise ValueError(f"{column} contains missing or nonfinite values at {locations}")
    if (values < 0).any():
        locations = replay.loc[values < 0, "timestamp"].astype(str).head(5).tolist()
        raise ValueError(f"{column} contains negative values at {locations}")
    baseline = float(values[0])
    maximum_deviation = float(np.max(np.abs(values - baseline)))
    if maximum_deviation > tolerance:
        raise ValueError(
            "Recorded replay basal is not constant: first recorded value="
            f"{baseline} U/hour, maximum absolute deviation={maximum_deviation} U/hour, "
            f"tolerance={tolerance} U/hour; varying trajectories are unsupported"
        )
    return baseline


def generate_basal_candidates(
    snapshot: PreparedBasalSnapshot,
    configuration: BasalSearchConfiguration,
) -> BasalCandidateSet:
    """Generate a baseline-centered grid without mutating the prepared snapshot."""

    if not isinstance(configuration, BasalSearchConfiguration):
        raise TypeError("configuration must be a BasalSearchConfiguration")
    baseline = extract_constant_baseline_rate(snapshot)
    baseline_decimal = _decimal(baseline, "baseline_rate_u_per_hour")
    absolute_minimum = _decimal(
        configuration.absolute_minimum_u_per_hour, "absolute_minimum_u_per_hour"
    )
    absolute_maximum = _decimal(
        configuration.absolute_maximum_u_per_hour, "absolute_maximum_u_per_hour"
    )
    if not absolute_minimum <= baseline_decimal <= absolute_maximum:
        raise ValueError(
            f"Recorded baseline {baseline} U/hour lies outside configured absolute bounds "
            f"[{configuration.absolute_minimum_u_per_hour}, "
            f"{configuration.absolute_maximum_u_per_hour}]"
        )

    maximum_decrease = _decimal(
        configuration.maximum_decrease_u_per_hour, "maximum_decrease_u_per_hour"
    )
    maximum_increase = _decimal(
        configuration.maximum_increase_u_per_hour, "maximum_increase_u_per_hour"
    )
    increment = _decimal(configuration.increment_u_per_hour, "increment_u_per_hour")
    relative_lower = baseline_decimal - maximum_decrease
    relative_upper = baseline_decimal + maximum_increase
    effective_lower = max(relative_lower, absolute_minimum)
    effective_upper = min(relative_upper, absolute_maximum)
    if effective_lower > effective_upper:
        raise ValueError("Relative and absolute basal search bounds do not intersect")

    minimum_k = int(
        ((effective_lower - baseline_decimal) / increment).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    maximum_k = int(
        ((effective_upper - baseline_decimal) / increment).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    count = maximum_k - minimum_k + 1
    if count <= 0:
        raise RuntimeError("Effective bounds unexpectedly contain no baseline-centered grid point")
    if count > configuration.maximum_candidate_count:
        raise ValueError(
            f"Configured grid has {count} candidates, exceeding maximum_candidate_count="
            f"{configuration.maximum_candidate_count}"
        )

    decimal_rates = tuple(
        baseline_decimal + increment * k for k in range(minimum_k, maximum_k + 1)
    )
    rates = tuple(
        baseline if k == 0 else float(rate)
        for k, rate in zip(range(minimum_k, maximum_k + 1), decimal_rates)
    )
    if any(not np.isfinite(rate) or rate < 0 for rate in rates):
        raise ValueError("Generated basal rates must be finite and nonnegative")
    if len(set(rates)) != len(rates):
        raise ValueError("Distinct decimal basal rates collapse as Python floats")
    float32_rates = np.asarray(rates, dtype=np.float32)
    if not np.isfinite(float32_rates).all():
        raise ValueError("Generated basal rates are not finite in simulator float32 dtype")
    if len(np.unique(float32_rates)) != len(rates):
        raise ValueError("Distinct basal rates collapse in the simulator float32 dtype")

    candidates = tuple(
        BasalRateCandidate(
            candidate_id=f"basal_{index:04d}",
            rate_u_per_hour=rate,
            is_recorded_baseline=(k == 0),
        )
        for index, (k, rate) in enumerate(
            zip(range(minimum_k, maximum_k + 1), rates)
        )
    )
    baseline_candidates = [item for item in candidates if item.is_recorded_baseline]
    if len(baseline_candidates) != 1:
        raise RuntimeError("Generated grid must contain the recorded baseline exactly once")
    return BasalCandidateSet(
        identity=snapshot.identity,
        decision_timestamp=snapshot.decision_timestamp,
        replay_start_timestamp=snapshot.simulation_start,
        replay_end_timestamp=snapshot.decision_timestamp,
        replay_interval_count=len(snapshot.replay_intervals),
        baseline_rate_u_per_hour=baseline,
        baseline_reference="first recorded basal_rate_u_per_hour in the prepared replay window",
        baseline_constancy_absolute_tolerance_u_per_hour=(
            BASELINE_CONSTANCY_ABSOLUTE_TOLERANCE_U_PER_HOUR
        ),
        effective_lower_u_per_hour=float(effective_lower),
        effective_upper_u_per_hour=float(effective_upper),
        candidates=candidates,
        baseline_candidate_id=baseline_candidates[0].candidate_id,
        configuration_version=configuration.configuration_version,
        configuration_hash=configuration_hash(configuration),
        candidate_count=len(candidates),
    )
