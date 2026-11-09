"""Load the resolved source policy without inheriting its validation claim."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .candidate_inputs import ConsumptionConfiguration, load_consumption_configuration
from .candidate_search import BolusSearchConfiguration
from .events import TriggerConfiguration
from .parameter_updates import RefreshConfiguration
from .scoring import ScoringConfiguration


DEFAULT_MIGRATED_CONFIGURATION = Path(__file__).with_name(
    "migrated_selected_configuration.json"
)


@dataclass(frozen=True)
class MigratedConfiguration:
    trigger: TriggerConfiguration
    search: BolusSearchConfiguration
    scoring: ScoringConfiguration
    consumption: ConsumptionConfiguration
    refresh: RefreshConfiguration
    source_payload: dict
    sha256: str


def load_migrated_configuration(
    path: str | Path = DEFAULT_MIGRATED_CONFIGURATION,
) -> MigratedConfiguration:
    path = Path(path)
    raw = path.read_bytes()
    payload = json.loads(raw)
    if payload.get("status") != "resolved_from_source_but_requires_renewed_final_model_validation":
        raise ValueError("Migrated policy status must require renewed validation")
    if payload.get("source_selection", {}).get("old_final_testing_ready_does_not_transfer") is not True:
        raise ValueError("Migrated policy must reject inherited readiness")
    if payload.get("residual", {}).get("enabled") is not False:
        raise ValueError("Residual must remain disabled in the migrated optimizer")
    if payload["residual"].get("affects_candidate_scoring") is not False \
            or payload["residual"].get("affects_state_propagation") is not False:
        raise ValueError("Residual diagnostics cannot affect optimization physiology")

    trigger = TriggerConfiguration(**payload["trigger"])
    search = BolusSearchConfiguration(**payload["search"])
    scoring = ScoringConfiguration(**payload["scoring"])
    consumption_path = path.parent.parent / payload["consumption"]["path"]
    consumption, consumption_hash = load_consumption_configuration(consumption_path)
    if consumption_hash != payload["consumption"]["sha256"]:
        raise ValueError("Consumption configuration hash mismatch")
    refresh = RefreshConfiguration(**payload["refresh"])
    return MigratedConfiguration(
        trigger, search, scoring, consumption, refresh, payload,
        hashlib.sha256(raw).hexdigest(),
    )

