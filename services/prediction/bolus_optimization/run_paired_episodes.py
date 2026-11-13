"""Step 11 continuous paired Hovorka episodes with optimizer delivery.

The baseline replays recorded boluses.  The optimized arm replaces every
recorded bolus with either the event-driven selected dose or zero.  Dataset
CGM is used only by the existing episode initializer; after initialization all
observations come from each arm's Hovorka state.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd
import torch

from final_model_adapter import sha256, verify_dataset

from .candidate_inputs import (
    DEFAULT_CONSUMPTION_CONFIGURATION, ConsumptionConfiguration,
    create_decision_snapshot, load_consumption_configuration,
)
from .candidate_search import (
    DEFAULT_SEARCH_CONFIGURATION, BolusSearchConfiguration,
    CandidateSearchResult, generate_bolus_candidates, load_search_configuration,
    simulate_bolus_candidates,
)
from .checkpoint import FrozenGRU, load_frozen_gru
from .configuration import FROZEN_CHECKPOINT_SHA256
from .data import read_optimization_data
from .episodes import (
    ALLOWED_SPLITS, EPISODE_INTERVALS, EXPECTED_SOURCE_HASHES,
    InitializedEpisode, build_episode_definitions, initialize_episode,
    mutable_storage_is_independent,
)
from .events import (
    DEFAULT_TRIGGER_CONFIGURATION, EvaluationEvent, TriggerConfiguration,
    acknowledge_evaluation, create_detector_state, detect_evaluation_event,
    load_trigger_configuration,
)
from .history import complete_interval, current_glucose_mg_dl
from .parameter_updates import RefreshConfiguration, refresh_parameters_if_due
from .physiology import PARAMETER_NAMES, STATE_NAMES
from .scoring import (
    DEFAULT_SCORING_CONFIGURATION, ScoringConfiguration, SelectionResult,
    load_scoring_configuration, score_and_select_candidates,
)
from .verify_candidate_search import _versions
from .verify_history_updates import (
    _flatten_refresh, select_diagnostic_episodes, verify_arm_refresh_schedule,
)


INTERVAL = pd.Timedelta(minutes=5)
SelectionOverride = Callable[[object, object, EvaluationEvent], SelectionResult]
OptimizerRunner = Callable[
    [object, object, EvaluationEvent, ConsumptionConfiguration,
     BolusSearchConfiguration, ScoringConfiguration], "EvaluationExecution"
]

RELEVANT_SOURCE_FILES = (
    "final_model_adapter.py", "optimize.py", "test.py", "bolus_optimization/configuration.py",
    "bolus_optimization/checkpoint.py", "bolus_optimization/data.py",
    "bolus_optimization/physiology.py", "bolus_optimization/episodes.py",
    "bolus_optimization/history.py", "bolus_optimization/parameter_updates.py",
    "bolus_optimization/verify_history_updates.py", "bolus_optimization/events.py",
    "bolus_optimization/candidate_inputs.py", "bolus_optimization/candidate_search.py",
    "bolus_optimization/scoring.py", "bolus_optimization/run_paired_episodes.py",
)


@dataclass(frozen=True)
class EvaluationExecution:
    selection: SelectionResult
    search: CandidateSearchResult | None
    candidate_diagnostics: Mapping[str, Any] | None = None


@dataclass
class PairedEpisodeResult:
    episode: InitializedEpisode
    episode_rows: list[dict]
    trajectory_rows: list[dict]
    input_rows: list[dict]
    event_rows: list[dict]
    recommendation_rows: list[dict]
    acknowledgement_rows: list[dict]
    delivery_rows: list[dict]
    score_rows: list[dict]
    rejection_rows: list[dict]
    failure_rows: list[dict]
    order_rows: list[dict]


def _component_values(components):
    if components is None:
        return {}
    return {name: getattr(components, name) for name in components.__dataclass_fields__}


def _run_optimizer(
    arm,
    current_events,
    event: EvaluationEvent,
    consumption: ConsumptionConfiguration,
    search_configuration: BolusSearchConfiguration,
    scoring: ScoringConfiguration,
    *,
    weight_kg: float,
    substeps: int,
    search_configuration_hash: str | None,
) -> EvaluationExecution:
    snapshot = create_decision_snapshot(
        arm, current_events, event, arm.detector_state
    )
    search = simulate_bolus_candidates(
        snapshot, search_configuration, consumption,
        weight_kg=weight_kg, substeps=substeps,
        search_configuration_hash=search_configuration_hash,
    )
    selection = score_and_select_candidates(search, search_configuration, scoring)
    return EvaluationExecution(selection, search, None)


def _event_row(definition, arm, detection):
    event = detection.event
    return {
        "episode_id": definition.episode_id, "dataset": definition.dataset,
        "patient_id": definition.patient_id, "split": definition.split,
        "arm": arm.arm_name, "decision_timestamp": detection.timestamp,
        "evaluation_eligible": detection.evaluation_eligible,
        "event_id": event.event_id if event else None,
        "event_type": event.event_type if event else None,
        "trigger_reasons": "|".join(detection.trigger_reasons),
        "suppression_reasons": "|".join(detection.suppression_reasons),
        "glucose_mg_dl": detection.current_glucose_mg_dl,
        "announced_carbs_g": detection.announced_carbs_g,
        "high_persistence_minutes": detection.high_persistence_minutes,
        "parameter_estimation_timestamp": detection.latest_parameter_estimation_timestamp,
    }


def _recommendation_row(definition, arm, event, selection):
    row = {
        "episode_id": definition.episode_id, "dataset": definition.dataset,
        "patient_id": definition.patient_id, "split": definition.split,
        "arm": arm.arm_name, "event_id": event.event_id,
        "event_type": event.event_type, "decision_timestamp": event.timestamp,
        "status": selection.status,
        "no_feasible_reason": selection.no_feasible_reason,
        "selected_candidate_id": selection.selected_candidate_id,
        "selected_dose_u": selection.selected_dose_u,
        "selected_score": selection.selected_score,
        "feasible_candidate_count": selection.feasible_candidate_count,
        "rejected_candidate_count": selection.rejected_candidate_count,
        "selected_at_upper_grid_boundary": selection.selected_at_upper_grid_boundary,
        "additional_bolus_for_simulation_u": selection.additional_bolus_for_simulation_u,
        "fallback_is_not_guaranteed_safe": selection.status == "no_feasible_recommendation",
    }
    row.update({f"selected_{key}": value for key, value in _component_values(
        selection.selected_components
    ).items()})
    return row


def _score_rows(definition, search, selection, diagnostics=None):
    rows, rejections = [], []
    if search is None:
        return rows, rejections
    for scored in selection.scored_candidates:
        row = {
            "episode_id": definition.episode_id, "dataset": definition.dataset,
            "patient_id": definition.patient_id, "split": definition.split,
            "arm": search.arm_name, "event_id": selection.evaluation_event_id,
            "decision_timestamp": search.decision_timestamp,
            "candidate_index": scored.candidate_index,
            "candidate_id": scored.candidate_id, "dose_u": scored.dose_u,
            "numerical_status": scored.numerical_status,
            "feasibility_status": scored.feasibility_status,
            "rejection_reason": scored.rejection_reason,
            "score": scored.score, "tie_set_member": scored.tie_set_member,
            "selected": scored.selected,
        }
        row.update(_component_values(scored.components))
        diagnostic = diagnostics.get(scored.candidate_id) if diagnostics else None
        if diagnostic is not None:
            values = (
                diagnostic.__dict__ if hasattr(diagnostic, "__dict__")
                else dict(diagnostic)
            )
            row.update({f"gated_{key}": value for key, value in values.items()})
        rows.append(row)
        if scored.rejection_reason is not None:
            rejections.append({
                key: row[key] for key in (
                    "episode_id", "dataset", "patient_id", "split", "arm",
                    "event_id", "decision_timestamp", "candidate_index",
                    "candidate_id", "dose_u", "feasibility_status",
                    "rejection_reason",
                )
            })
    return rows, rejections


def _trajectory_row(definition, arm, completed_intervals: int):
    row = {
        "episode_id": definition.episode_id, "dataset": definition.dataset,
        "patient_id": definition.patient_id, "split": definition.split,
        "arm": arm.arm_name, "boundary_timestamp": arm.current_timestamp,
        "completed_episode_intervals": completed_intervals,
        "glucose_mg_dl": arm.history.current_glucose_mg_dl,
        "observation_source": arm.history.current_source,
        "parameter_estimation_timestamp": arm.parameter_estimation_timestamp,
        "arm_status": arm.status,
    }
    row.update({name: float(value) for name, value in zip(STATE_NAMES, arm.physiological_state)})
    return row


def _selection_dose(selection: SelectionResult) -> tuple[float, str]:
    if selection.status == "selected":
        if selection.selected_dose_u is None:
            raise RuntimeError("A selected result has no dose")
        return float(selection.selected_dose_u), (
            "successful_zero_dose_selection" if selection.selected_dose_u == 0
            else "selected_optimizer_bolus"
        )
    if selection.status == "no_feasible_recommendation":
        if selection.selected_dose_u is not None or selection.additional_bolus_for_simulation_u != 0:
            raise RuntimeError("Malformed no-feasible fallback")
        return 0.0, "no_feasible_zero_fallback_not_guaranteed_safe"
    raise RuntimeError(f"Unknown selection status: {selection.status}")


def run_paired_episode(
    episode: InitializedEpisode,
    frozen: FrozenGRU,
    trigger: TriggerConfiguration,
    consumption: ConsumptionConfiguration,
    search_configuration: BolusSearchConfiguration,
    scoring: ScoringConfiguration,
    refresh_configuration: RefreshConfiguration | None = None,
    *,
    weight_kg: float = 70.0,
    substeps: int = 5,
    search_configuration_hash: str | None = None,
    selection_override: SelectionOverride | None = None,
    optimizer_runner: OptimizerRunner | None = None,
) -> PairedEpisodeResult:
    """Run one initialized pair for exactly 288 real intervals.

    ``selection_override`` is a test seam.  Production diagnostics leave it
    unset and always execute snapshot -> candidate simulation -> scoring.
    """

    if selection_override is not None and optimizer_runner is not None:
        raise ValueError("selection_override and optimizer_runner are mutually exclusive")
    if episode.initialization_status != "initialized" or episode.environment is None:
        raise ValueError("Episode must be successfully initialized")
    if not mutable_storage_is_independent(episode):
        raise RuntimeError("Paired arms do not own independent mutable storage")
    refresh_configuration = refresh_configuration or RefreshConfiguration()
    definition = episode.definition
    arms = (episode.baseline_arm, episode.optimized_arm)
    for arm in arms:
        if arm is None or arm.current_timestamp != definition.start_timestamp:
            raise RuntimeError("Arm is not at the episode start boundary")
        if arm.detector_state is None:
            arm.detector_state = create_detector_state(arm, definition)

    result = PairedEpisodeResult(
        episode, [], [], [], [], [], [], [], [], [], [], [],
    )
    for arm in arms:
        result.trajectory_rows.append(_trajectory_row(definition, arm, 0))

    for interval_index in range(EPISODE_INTERVALS):
        expected_boundary = definition.start_timestamp + interval_index * INTERVAL
        for arm in arms:
            if arm.status != "active":
                continue
            if arm.current_timestamp != expected_boundary:
                arm.status = "failed_step11_schedule"
                arm.failure_reason = "arm_clock_does_not_match_interval_boundary"
                result.failure_rows.append({
                    "episode_id": definition.episode_id, "arm": arm.arm_name,
                    "stopping_boundary": arm.current_timestamp,
                    "failure_reason": arm.failure_reason,
                })
                continue
            order = []
            event = None
            selection = None
            delivered = None
            action_status = None
            try:
                # 1. Observe simulated glucose.
                current_glucose_mg_dl(arm, weight_kg=weight_kg)
                order.append("observe_simulated_glucose")
                # 2. Reveal current announcements and exogenous interval inputs.
                current_events = episode.environment.reveal(arm)
                order.append("reveal_current_interval")
                # 3. Refresh from completed history at this boundary.
                refresh_parameters_if_due(
                    arm, frozen, current_events, refresh_configuration
                )
                order.append("refresh_parameters_if_scheduled")
                # 4. Detect and determine the interval bolus.
                detection = detect_evaluation_event(
                    arm, current_events, trigger, arm.detector_state,
                    weight_kg=weight_kg,
                )
                order.append("detect_event")
                result.event_rows.append(_event_row(definition, arm, detection))
                event = detection.event
                if arm.arm_name == "recorded_bolus_baseline":
                    delivered = float(current_events.recorded_bolus_u)
                    action_status = "recorded_dataset_bolus"
                    if event is not None:
                        outcome = acknowledge_evaluation(
                            arm.detector_state, event.event_id,
                            status="completed",
                            outcome="observation_only_recorded_action",
                            acknowledgement_timestamp=event.timestamp,
                            selected_dose_u=delivered,
                        )
                        result.acknowledgement_rows.append({
                            "episode_id": definition.episode_id, "arm": arm.arm_name,
                            **outcome.__dict__, "delivery_policy": "recorded_dataset_bolus",
                        })
                else:
                    delivered = 0.0
                    action_status = "no_eligible_event_zero"
                    if event is not None:
                        if optimizer_runner is not None:
                            execution = optimizer_runner(
                                arm, current_events, event, consumption,
                                search_configuration, scoring,
                            )
                        elif selection_override is None:
                            execution = _run_optimizer(
                                arm, current_events, event, consumption,
                                search_configuration, scoring,
                                weight_kg=weight_kg, substeps=substeps,
                                search_configuration_hash=search_configuration_hash,
                            )
                        else:
                            execution = EvaluationExecution(
                                selection_override(arm, current_events, event), None, None
                            )
                        selection = execution.selection
                        if selection.evaluation_event_id != event.event_id:
                            raise RuntimeError("Selection does not belong to the pending event")
                        delivered, action_status = _selection_dose(selection)
                        result.recommendation_rows.append(
                            _recommendation_row(definition, arm, event, selection)
                        )
                        score_rows, rejection_rows = _score_rows(
                            definition, execution.search, selection,
                            execution.candidate_diagnostics,
                        )
                        result.score_rows.extend(score_rows)
                        result.rejection_rows.extend(rejection_rows)
                        outcome = acknowledge_evaluation(
                            arm.detector_state, event.event_id,
                            status="completed", outcome=action_status,
                            acknowledgement_timestamp=event.timestamp,
                            selected_dose_u=selection.selected_dose_u,
                        )
                        result.acknowledgement_rows.append({
                            "episode_id": definition.episode_id, "arm": arm.arm_name,
                            **outcome.__dict__, "delivery_policy": "optimizer_replacement",
                        })
                order.append("determine_and_acknowledge_bolus")
                # 5-7. Apply [t,t+5), advance, then commit the t+5 observation.
                completion = complete_interval(
                    arm, current_events, delivered,
                    weight_kg=weight_kg, substeps=substeps,
                    delivery_source=(
                        "recorded_dataset_bolus" if arm.arm_name == "recorded_bolus_baseline"
                        else "optimizer_selected_bolus"
                    ),
                )
                order.extend(("apply_interval_inputs", "advance_hovorka", "commit_history"))
                result.input_rows.append({
                    "episode_id": definition.episode_id, "dataset": definition.dataset,
                    "patient_id": definition.patient_id, "split": definition.split,
                    "arm": arm.arm_name, "interval_index": interval_index,
                    "interval_start_timestamp": current_events.timestamp,
                    "interval_end_timestamp": current_events.timestamp + INTERVAL,
                    "basal_rate_u_per_hour": current_events.basal_rate_u_per_hour,
                    "consumed_carbs_g": current_events.consumed_carbs_g,
                    "announced_carbs_g": current_events.carbs_g,
                    "delivered_bolus_u": delivered,
                    "action_status": action_status,
                    "event_id": event.event_id if event else None,
                    "selection_status": selection.status if selection else None,
                    "interval_completed": completion.success,
                    "failure_reason": completion.failure_reason,
                })
                if not completion.success:
                    raise RuntimeError(completion.failure_reason)
                result.trajectory_rows.append(
                    _trajectory_row(definition, arm, interval_index + 1)
                )
                if delivered > 0:
                    result.delivery_rows.append({
                        "episode_id": definition.episode_id, "dataset": definition.dataset,
                        "patient_id": definition.patient_id, "split": definition.split,
                        "arm": arm.arm_name, "timestamp": current_events.timestamp,
                        "delivered_bolus_u": delivered,
                        "source": (
                            "recorded_dataset_bolus" if arm.arm_name == "recorded_bolus_baseline"
                            else "optimizer_selected_bolus"
                        ),
                        "event_id": event.event_id if event else None,
                    })
            except Exception as error:
                if event is not None and arm.detector_state.pending_event_id == event.event_id:
                    try:
                        outcome = acknowledge_evaluation(
                            arm.detector_state, event.event_id,
                            status="failed",
                            outcome=f"implementation_failure:{type(error).__name__}",
                            acknowledgement_timestamp=event.timestamp,
                            retry_policy="no_retry_until_glucose_resets",
                        )
                        result.acknowledgement_rows.append({
                            "episode_id": definition.episode_id, "arm": arm.arm_name,
                            **outcome.__dict__, "delivery_policy": "not_delivered",
                        })
                    except Exception:
                        pass
                if not arm.status.startswith("failed"):
                    arm.status = "failed_step11"
                    arm.failure_reason = f"{type(error).__name__}:{error}"
                result.failure_rows.append({
                    "episode_id": definition.episode_id, "arm": arm.arm_name,
                    "stopping_boundary": arm.current_timestamp,
                    "failure_reason": arm.failure_reason,
                })
            finally:
                result.order_rows.append({
                    "episode_id": definition.episode_id, "arm": arm.arm_name,
                    "interval_index": interval_index, "boundary_timestamp": expected_boundary,
                    "observed_order": "|".join(order),
                    "boundary_order_pass": order == [
                        "observe_simulated_glucose", "reveal_current_interval",
                        "refresh_parameters_if_scheduled", "detect_event",
                        "determine_and_acknowledge_bolus", "apply_interval_inputs",
                        "advance_hovorka", "commit_history",
                    ],
                })

    for arm in arms:
        completed = bool(
            arm.status == "active" and arm.current_timestamp == definition.end_timestamp
            and len(arm.event_bookkeeping["applied_events"]) == EPISODE_INTERVALS
        )
        result.episode_rows.append({
            "episode_id": definition.episode_id, "dataset": definition.dataset,
            "patient_id": definition.patient_id, "split": definition.split,
            "arm": arm.arm_name, "start_timestamp": definition.start_timestamp,
            "end_timestamp": definition.end_timestamp,
            "stopping_boundary": arm.current_timestamp,
            "completed_intervals": len(arm.event_bookkeeping["applied_events"]),
            "status": "completed" if completed else arm.status,
            "failure_reason": arm.failure_reason,
            "pending_event_id": arm.detector_state.pending_event_id,
            "terminal_decision_attempted": definition.end_timestamp in arm.detector_state.boundary_results,
        })
    return result


def _write_frame(rows, path: Path, *, parquet: bool = False):
    frame = pd.DataFrame(rows)
    if parquet:
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False)
    return frame


def run_continuous_diagnostic(
    dataset_path: str | Path,
    checkpoint_path: str | Path,
    output_directory: str | Path,
    *,
    trigger_configuration_path: str | Path = DEFAULT_TRIGGER_CONFIGURATION,
    consumption_configuration_path: str | Path = DEFAULT_CONSUMPTION_CONFIGURATION,
    search_configuration_path: str | Path = DEFAULT_SEARCH_CONFIGURATION,
    scoring_configuration_path: str | Path = DEFAULT_SCORING_CONFIGURATION,
    episodes_per_patient: int = 1,
    refresh_minutes: int = 120,
    weight_kg: float = 70.0,
    substeps: int = 5,
    selected_episode_ids: set[str] | None = None,
):
    started = time.perf_counter()
    out = Path(output_directory)
    out.mkdir(parents=True, exist_ok=True)
    trigger, trigger_hash = load_trigger_configuration(trigger_configuration_path)
    consumption, consumption_hash = load_consumption_configuration(consumption_configuration_path)
    search, search_hash = load_search_configuration(search_configuration_path)
    scoring, scoring_hash = load_scoring_configuration(scoring_configuration_path)
    refresh = RefreshConfiguration(refresh_minutes)
    data, patient_splits, loader_audit = read_optimization_data(dataset_path)
    frozen = load_frozen_gru(checkpoint_path, expected_sha256=FROZEN_CHECKPOINT_SHA256)
    verify_dataset(dataset_path, frozen.checkpoint)
    if patient_splits != frozen.checkpoint["patient_splits"]:
        raise ValueError("Patient splits differ from the frozen checkpoint")
    all_definitions = build_episode_definitions(data)
    if selected_episode_ids is None:
        definitions = select_diagnostic_episodes(all_definitions, episodes_per_patient)
    else:
        available = {item.episode_id for item in all_definitions if item.eligible}
        unknown = set(selected_episode_ids).difference(available)
        if unknown:
            raise ValueError(f"Unknown or ineligible selected episodes: {sorted(unknown)}")
        definitions = [item for item in all_definitions if item.episode_id in selected_episode_ids]
        if not definitions:
            raise ValueError("No smoke episodes were selected")
    groups = {
        (str(dataset), str(patient)): group.sort_values("timestamp").reset_index(drop=True)
        for (dataset, patient), group in data[data["split"].isin(ALLOWED_SPLITS)].groupby(
            ["dataset", "patient_id"], sort=False
        )
    }
    aggregate = {name: [] for name in (
        "episode_rows", "trajectory_rows", "input_rows", "event_rows",
        "recommendation_rows", "acknowledgement_rows", "delivery_rows",
        "score_rows", "rejection_rows", "failure_rows", "order_rows",
    )}
    initialization_failures = 0
    schedule_checks = []
    pair_checks = []
    refresh_rows = []
    for definition in definitions:
        episode = initialize_episode(
            groups[(definition.dataset, definition.patient_id)], definition, frozen,
            weight_kg=weight_kg, substeps=substeps,
        )
        if episode.initialization_status != "initialized":
            initialization_failures += 1
            aggregate["failure_rows"].append({
                "episode_id": definition.episode_id, "arm": "pair",
                "stopping_boundary": definition.start_timestamp,
                "failure_reason": str(episode.failure),
            })
            continue
        initialized_equal = all(torch.equal(
            getattr(episode.baseline_arm, name), getattr(episode.optimized_arm, name)
        ) for name in ("physiological_state", "parameters"))
        run = run_paired_episode(
            episode, frozen, trigger, consumption, search, scoring, refresh,
            weight_kg=weight_kg, substeps=substeps,
            search_configuration_hash=search_hash,
        )
        for name in aggregate:
            aggregate[name].extend(getattr(run, name))
        arms = (episode.baseline_arm, episode.optimized_arm)
        for arm in arms:
            schedule_checks.append(
                verify_arm_refresh_schedule(arm, refresh, definition.end_timestamp)
            )
            refresh_rows.extend(_flatten_refresh(definition, arm, row) for row in arm.refresh_log)
        pair_inputs = pd.DataFrame(run.input_rows)
        shared_equal = False
        if len(pair_inputs):
            baseline = pair_inputs[pair_inputs.arm == "recorded_bolus_baseline"].sort_values("interval_index")
            optimized = pair_inputs[pair_inputs.arm == "optimized_bolus"].sort_values("interval_index")
            shared = [
                "interval_start_timestamp", "basal_rate_u_per_hour",
                "consumed_carbs_g", "announced_carbs_g",
            ]
            shared_equal = len(baseline) == len(optimized) and baseline[shared].reset_index(drop=True).equals(
                optimized[shared].reset_index(drop=True)
            )
        pair_checks.append({
            "episode_id": definition.episode_id,
            "initialization_equal": initialized_equal,
            "mutable_storage_independent": mutable_storage_is_independent(episode),
            "shared_exogenous_inputs_equal": shared_equal,
            "shared_refresh_offsets_equal": tuple(x["scheduled_offset_minutes"] for x in arms[0].refresh_log)
            == tuple(x["scheduled_offset_minutes"] for x in arms[1].refresh_log),
            "both_complete": all(
                arm.status == "active" and arm.current_timestamp == definition.end_timestamp
                for arm in arms
            ),
        })

    episode_frame = _write_frame(aggregate["episode_rows"], out / "episode_inventory.csv")
    trajectory_frame = _write_frame(aggregate["trajectory_rows"], out / "glucose_trajectories.parquet", parquet=True)
    input_frame = _write_frame(aggregate["input_rows"], out / "applied_interval_inputs.parquet", parquet=True)
    event_frame = _write_frame(aggregate["event_rows"], out / "event_log.parquet", parquet=True)
    recommendation_frame = _write_frame(aggregate["recommendation_rows"], out / "recommendation_log.parquet", parquet=True)
    acknowledgement_frame = _write_frame(aggregate["acknowledgement_rows"], out / "acknowledgement_log.parquet", parquet=True)
    delivery_frame = _write_frame(aggregate["delivery_rows"], out / "delivery_log.parquet", parquet=True)
    score_frame = _write_frame(aggregate["score_rows"], out / "candidate_scores.parquet", parquet=True)
    rejection_frame = _write_frame(aggregate["rejection_rows"], out / "candidate_rejections.csv")
    failure_frame = _write_frame(aggregate["failure_rows"], out / "failures.csv")
    order_frame = _write_frame(aggregate["order_rows"], out / "boundary_order_checks.csv")
    refresh_frame = _write_frame(refresh_rows, out / "parameter_refresh_log.parquet", parquet=True)
    pair_frame = _write_frame(pair_checks, out / "verification_checks.csv")
    _write_frame(schedule_checks, out / "refresh_schedule_checks.csv")

    source_hashes = {path: sha256(path) for path in RELEVANT_SOURCE_FILES}
    dataset_hash = sha256(dataset_path)
    configuration = {
        "step": 11,
        "scope": "continuous paired 24-hour Hovorka arms with optimizer bolus replacement",
        "dataset": str(Path(dataset_path).resolve()), "dataset_sha256": dataset_hash,
        "checkpoint": str(Path(checkpoint_path).resolve()),
        "checkpoint_sha256": frozen.checkpoint_sha256,
        "checkpoint_dataset_sha256": frozen.checkpoint.get("data_sha256"),
        "dataset_hash_discrepancy": {"status": "resolved_match"},
        "splits": list(ALLOWED_SPLITS), "testing_patients_used": False,
        "interval_order": [
            "observe simulated glucose", "reveal current announcement and exogenous inputs",
            "scheduled per-arm GRU refresh", "event detection and interval bolus decision",
            "apply interval inputs", "advance Hovorka to t+5", "commit t+5 observation",
        ],
        "episode_intervals": EPISODE_INTERVALS,
        "terminal_boundary_decisions": False,
        "refresh_minutes": refresh_minutes,
        "scheduled_refresh_offsets_minutes": list(refresh.scheduled_offsets),
        "trigger_configuration_sha256": trigger_hash,
        "consumption_configuration_sha256": consumption_hash,
        "search_configuration_sha256": search_hash,
        "scoring_configuration_sha256": scoring_hash,
        "candidate_count": len(generate_bolus_candidates(search)),
        "baseline_policy": "dataset basal + dataset consumption + recorded dataset bolus",
        "optimized_policy": "dataset basal + dataset consumption + selected bolus replacement; otherwise zero",
        "source_hashes": source_hashes,
        "expected_preserved_source_hashes": EXPECTED_SOURCE_HASHES,
        "loader_audit": loader_audit, "software_versions": _versions(),
    }
    (out / "configuration.json").write_text(json.dumps(configuration, indent=2, default=str) + "\n")

    completed_arms = int((episode_frame.get("status", pd.Series(dtype=str)) == "completed").sum())
    complete_pairs = int(sum(item["both_complete"] for item in pair_checks))
    event_counts = Counter(
        (row["arm"], row["event_type"])
        for row in aggregate["event_rows"] if row["event_type"] is not None
    )
    positive_selected = int(sum(
        row["arm"] == "optimized_bolus" and row["delivered_bolus_u"] > 0
        for row in aggregate["delivery_rows"]
    ))
    zero_selected = int(sum(
        row["status"] == "selected" and row["selected_dose_u"] == 0
        for row in aggregate["recommendation_rows"]
    ))
    no_feasible = int(sum(
        row["status"] == "no_feasible_recommendation"
        for row in aggregate["recommendation_rows"]
    ))
    upper = int(sum(
        bool(row["selected_at_upper_grid_boundary"])
        for row in aggregate["recommendation_rows"]
    ))
    delivered_totals = {
        arm: float(input_frame.loc[input_frame.arm == arm, "delivered_bolus_u"].sum())
        if len(input_frame) else 0.0
        for arm in ("recorded_bolus_baseline", "optimized_bolus")
    }
    schedule_pass = bool(
        len(schedule_checks) == len(episode_frame)
        and all(item["ordered_exact_match"] for item in schedule_checks)
    )
    pair_pass = bool(pair_checks and all(
        item["initialization_equal"] and item["mutable_storage_independent"]
        and item["shared_exogenous_inputs_equal"]
        and item["shared_refresh_offsets_equal"] and item["both_complete"]
        for item in pair_checks
    ))
    lifecycle_failures = int(episode_frame.get(
        "pending_event_id", pd.Series(dtype=object)
    ).notna().sum())
    causality_failures = int(sum(
        pd.Timestamp(row["parameter_estimation_timestamp"])
        > pd.Timestamp(row["decision_timestamp"])
        for row in aggregate["event_rows"]
    ))
    terminal_failures = int(episode_frame.get(
        "terminal_decision_attempted", pd.Series(dtype=bool)
    ).fillna(False).sum())
    boundary_failures = int((~order_frame["boundary_order_pass"]).sum()) if len(order_frame) else 1
    preservation_pass = bool(
        frozen.checkpoint_sha256 == FROZEN_CHECKPOINT_SHA256
        and all(source_hashes[path] == expected for path, expected in EXPECTED_SOURCE_HASHES.items())
    )
    implementation_pass = bool(
        initialization_failures == 0 and len(failure_frame) == 0
        and schedule_pass and pair_pass and lifecycle_failures == 0
        and causality_failures == 0
        and terminal_failures == 0 and boundary_failures == 0
        and preservation_pass
    )
    completion_pass = bool(
        completed_arms == 2 * len(definitions) and complete_pairs == len(definitions)
    )
    summary = {
        "scope": "continuous paired 24-hour Hovorka simulation with optimizer delivery",
        "episodes_attempted": len(definitions), "arms_attempted": 2 * len(definitions),
        "completed_arms": completed_arms, "complete_episode_pairs": complete_pairs,
        "event_counts_by_arm_and_type": {
            f"{arm}:{event_type}": count
            for (arm, event_type), count in sorted(event_counts.items())
        },
        "optimizer_recommendations": len(recommendation_frame),
        "positive_selected_deliveries": positive_selected,
        "successful_zero_dose_selections": zero_selected,
        "no_feasible_outcomes": no_feasible,
        "total_delivered_bolus_u_by_arm": delivered_totals,
        "upper_grid_boundary_selections": upper,
        "simulation_failures": len(failure_frame),
        "lifecycle_failures": lifecycle_failures,
        "causality_failures": causality_failures,
        "schedule_failures": sum(not item["ordered_exact_match"] for item in schedule_checks),
        "boundary_order_failures": boundary_failures,
        "terminal_boundary_failures": terminal_failures,
        "shared_exogenous_and_refresh_verification_pass": pair_pass,
        "strict_refresh_schedule_pass": schedule_pass,
        "preservation_checks_pass": preservation_pass,
        "split_isolation_pass": not bool((episode_frame.get("split", pd.Series(dtype=str)) == "testing").any()),
        "implementation_verification_pass": implementation_pass,
        "simulation_completion_pass": completion_pass,
        "overall_pass": bool(implementation_pass and completion_pass),
        "selected_actions_delivered": positive_selected > 0,
        "effectiveness_inference_permitted": False,
        "dataset_hash_discrepancy": "resolved_match",
        "runtime_seconds": time.perf_counter() - started,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    (out / "summary.md").write_text("\n".join([
        "# Step 11 continuous paired-arm verification", "",
        f"Implementation verification: **{'PASS' if implementation_pass else 'FAIL'}**",
        f"Simulation completion: **{'PASS' if completion_pass else 'FAIL'}**",
        f"Overall result: **{'PASS' if summary['overall_pass'] else 'FAIL'}**", "",
        f"Completed arms / complete pairs: {completed_arms} / {complete_pairs}",
        f"Optimizer recommendations: {len(recommendation_frame)}",
        f"Positive selected deliveries: {positive_selected}",
        f"Successful zero selections: {zero_selected}",
        f"No-feasible outcomes: {no_feasible}",
        f"Upper-grid selections: {upper}",
        f"Total baseline bolus: {delivered_totals['recorded_bolus_baseline']:.6g} U",
        f"Total optimized bolus: {delivered_totals['optimized_bolus']:.6g} U", "",
        "Selected actions were delivered when positive; zero selections and no-feasible fallbacks remain distinct.",
        "This smoke diagnostic does not establish effectiveness or clinical safety.",
        "The dataset hash matches the final checkpoint exactly.", "",
    ]))
    return summary


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the standalone CLI while preserving explicit component overrides."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--checkpoint", default="baseline/model.pt")
    parser.add_argument("--out", default="results/bolus_optimization_migrated_final/step11_continuous_arms")
    parser.add_argument("--trigger-configuration", default=str(DEFAULT_TRIGGER_CONFIGURATION))
    parser.add_argument("--consumption-configuration", default=str(DEFAULT_CONSUMPTION_CONFIGURATION))
    parser.add_argument("--search-configuration", default=str(DEFAULT_SEARCH_CONFIGURATION))
    parser.add_argument("--scoring-configuration", default=str(DEFAULT_SCORING_CONFIGURATION))
    parser.add_argument("--episodes-per-patient", type=int, default=1)
    parser.add_argument("--refresh-minutes", type=int, default=120)
    parser.add_argument("--weight-kg", type=float, default=70.0)
    parser.add_argument("--substeps", type=int, default=5)
    return parser


def main():
    parser = build_argument_parser()
    args = parser.parse_args()
    if args.episodes_per_patient < 0 or args.weight_kg <= 0 or args.substeps <= 0:
        parser.error("episode count must be nonnegative; weight and substeps must be positive")
    summary = run_continuous_diagnostic(
        args.dataset, args.checkpoint, args.out,
        trigger_configuration_path=args.trigger_configuration,
        consumption_configuration_path=args.consumption_configuration,
        search_configuration_path=args.search_configuration,
        scoring_configuration_path=args.scoring_configuration,
        episodes_per_patient=args.episodes_per_patient,
        refresh_minutes=args.refresh_minutes, weight_kg=args.weight_kg,
        substeps=args.substeps,
    )
    print(Path(args.out) / "summary.json")
    if not summary["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
