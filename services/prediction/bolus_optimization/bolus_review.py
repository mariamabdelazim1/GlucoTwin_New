"""Annotation-only review flags for a single proposed bolus dose.

This module is deliberately separate from candidate generation, scoring,
selection and delivery.  It does not clip, replace, approve or deliver a dose.
The thresholds are research software review triggers, not safe-dose limits.
"""

from __future__ import annotations

import hashlib
import json
import math
import numbers
from dataclasses import asdict, dataclass
from pathlib import Path


NO_DOSE_THRESHOLD_FLAG = "NO_DOSE_THRESHOLD_FLAG"
ELEVATED_BOLUS_REQUIRES_REVIEW = "ELEVATED_BOLUS_REQUIRES_REVIEW"
HIGH_BOLUS_REQUIRES_REVIEW = "HIGH_BOLUS_REQUIRES_REVIEW"
EXCEEDS_PATIENT_PRESCRIBED_MAX = "EXCEEDS_PATIENT_PRESCRIBED_MAX"

DEFAULT_BOLUS_REVIEW_CONFIGURATION_PATH = Path(__file__).with_name(
    "bolus_review_configuration_v1.json"
)

NO_TRIGGER_EXPLANATION = (
    "review_required=false means only that these threshold rules did not "
    "trigger. It does not establish safety or approve the dose."
)
REVIEW_TRIGGERED_EXPLANATION = (
    "review_required=true means at least one research software review rule "
    "triggered. It does not determine whether the dose is appropriate or safe."
)


def _finite_real(value, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be numeric and not Boolean")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive:
        if result <= 0:
            raise ValueError(f"{name} must be strictly positive")
    elif result < 0:
        raise ValueError(f"{name} must be nonnegative")
    return result


@dataclass(frozen=True)
class BolusReviewConfiguration:
    configuration_version: str
    elevated_bolus_threshold_u: float
    high_bolus_threshold_u: float
    intended_use: str

    def __post_init__(self):
        if not isinstance(self.configuration_version, str) \
                or not self.configuration_version.strip():
            raise ValueError("configuration_version must be a nonempty string")
        if not isinstance(self.intended_use, str) or not self.intended_use.strip():
            raise ValueError("intended_use must be a nonempty string")
        elevated = _finite_real(
            self.elevated_bolus_threshold_u,
            "elevated_bolus_threshold_u",
            positive=True,
        )
        high = _finite_real(
            self.high_bolus_threshold_u,
            "high_bolus_threshold_u",
            positive=True,
        )
        if elevated >= high:
            raise ValueError(
                "thresholds must satisfy 0 < elevated_bolus_threshold_u "
                "< high_bolus_threshold_u"
            )
        object.__setattr__(self, "elevated_bolus_threshold_u", elevated)
        object.__setattr__(self, "high_bolus_threshold_u", high)


def load_bolus_review_configuration(
    path: str | Path = DEFAULT_BOLUS_REVIEW_CONFIGURATION_PATH,
) -> tuple[BolusReviewConfiguration, str]:
    """Load and validate the versioned review configuration and return its hash."""

    raw = Path(path).read_bytes()
    configuration = BolusReviewConfiguration(**json.loads(raw))
    return configuration, hashlib.sha256(raw).hexdigest()


DEFAULT_BOLUS_REVIEW_CONFIGURATION, DEFAULT_BOLUS_REVIEW_CONFIGURATION_SHA256 = (
    load_bolus_review_configuration()
)


@dataclass(frozen=True)
class BolusReviewResult:
    proposed_bolus_u: float
    threshold_classification: str
    flags: tuple[str, ...]
    thresholds_used: BolusReviewConfiguration
    patient_prescribed_max_bolus_u: float | None
    patient_limit_status: str
    review_required: bool
    review_required_explanation: str

    def as_dict(self) -> dict:
        """Return a new JSON-compatible representation of the annotation."""

        result = asdict(self)
        result["flags"] = list(self.flags)
        return result


def review_bolus_dose(
    proposed_bolus_u,
    patient_prescribed_max_bolus_u=None,
    *,
    configuration: BolusReviewConfiguration = DEFAULT_BOLUS_REVIEW_CONFIGURATION,
) -> BolusReviewResult:
    """Classify one proposed dose without changing or approving it.

    ``patient_prescribed_max_bolus_u`` is accepted only when supplied by the
    caller.  No limit is inferred from historical doses or patient metadata.
    """

    if not isinstance(configuration, BolusReviewConfiguration):
        raise ValueError("configuration must be a BolusReviewConfiguration")
    dose = _finite_real(proposed_bolus_u, "proposed_bolus_u")
    prescribed_maximum = None
    if patient_prescribed_max_bolus_u is not None:
        prescribed_maximum = _finite_real(
            patient_prescribed_max_bolus_u,
            "patient_prescribed_max_bolus_u",
            positive=True,
        )

    if dose <= configuration.elevated_bolus_threshold_u:
        classification = NO_DOSE_THRESHOLD_FLAG
    elif dose <= configuration.high_bolus_threshold_u:
        classification = ELEVATED_BOLUS_REQUIRES_REVIEW
    else:
        classification = HIGH_BOLUS_REQUIRES_REVIEW

    flags = [classification]
    if prescribed_maximum is None:
        patient_limit_status = "unavailable"
    elif dose > prescribed_maximum:
        patient_limit_status = "exceeded"
        flags.append(EXCEEDS_PATIENT_PRESCRIBED_MAX)
    else:
        patient_limit_status = "within_limit"

    review_required = classification != NO_DOSE_THRESHOLD_FLAG \
        or patient_limit_status == "exceeded"
    return BolusReviewResult(
        proposed_bolus_u=dose,
        threshold_classification=classification,
        flags=tuple(flags),
        thresholds_used=configuration,
        patient_prescribed_max_bolus_u=prescribed_maximum,
        patient_limit_status=patient_limit_status,
        review_required=review_required,
        review_required_explanation=(
            REVIEW_TRIGGERED_EXPLANATION if review_required
            else NO_TRIGGER_EXPLANATION
        ),
    )
