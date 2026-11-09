"""Step 10 observation-only verification of feasibility, scoring and selection."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from final_model_adapter import sha256

from .candidate_inputs import (
    DEFAULT_CONSUMPTION_CONFIGURATION, create_decision_snapshot,
    load_consumption_configuration,
)
from .candidate_search import (
    DEFAULT_SEARCH_CONFIGURATION, generate_bolus_candidates, load_search_configuration,
    simulate_bolus_candidates,
)
from .checkpoint import load_frozen_gru
from .configuration import FROZEN_CHECKPOINT_SHA256
from .data import read_optimization_data
from .episodes import ALLOWED_SPLITS, EXPECTED_SOURCE_HASHES, build_episode_definitions, initialize_episode
from .events import (
    DEFAULT_TRIGGER_CONFIGURATION, acknowledge_evaluation, create_detector_state,
    detect_evaluation_event, load_trigger_configuration,
)
from .history import complete_interval, current_glucose_mg_dl
from .parameter_updates import RefreshConfiguration, refresh_parameters_if_due
from .scoring import (
    DEFAULT_SCORING_CONFIGURATION, load_scoring_configuration,
    score_and_select_candidates,
)
from .verify_candidate_search import _arm_unchanged, _capture_arm, _versions
from .verify_history_updates import select_diagnostic_episodes, verify_arm_refresh_schedule


RELEVANT_SOURCE_FILES = (
    "final_model_adapter.py", "optimize.py", "test.py", "bolus_optimization/configuration.py",
    "bolus_optimization/checkpoint.py", "bolus_optimization/data.py",
    "bolus_optimization/physiology.py", "bolus_optimization/episodes.py",
    "bolus_optimization/history.py", "bolus_optimization/parameter_updates.py",
    "bolus_optimization/verify_history_updates.py", "bolus_optimization/events.py",
    "bolus_optimization/candidate_inputs.py", "bolus_optimization/candidate_search.py",
    "bolus_optimization/scoring.py", "bolus_optimization/verify_selection.py",
)


def _component_values(components):
    names = (
        "low_component", "high_component", "severe_low_component",
        "insulin_component", "terminal_component", "weighted_low",
        "weighted_high", "weighted_severe_low", "weighted_insulin",
        "weighted_terminal", "total_score",
    )
    return {name: getattr(components, name) if components is not None else None for name in names}


def _scored_row(definition, search, selection, scored, scoring):
    row = {
        "evaluation_event_id": selection.evaluation_event_id,
        "episode_id": search.episode_id, "dataset": definition.dataset,
        "patient_id": search.patient_id, "split": definition.split,
        "arm": search.arm_name, "decision_timestamp": search.decision_timestamp,
        "candidate_index": scored.candidate_index, "candidate_id": scored.candidate_id,
        "dose_u": scored.dose_u, "numerical_status": scored.numerical_status,
        "feasibility_status": scored.feasibility_status,
        "rejection_reason": scored.rejection_reason,
        "score": scored.score, "tie_set_member": scored.tie_set_member,
        "selected": scored.selected,
        "low_weight": scoring.low_weight, "high_weight": scoring.high_weight,
        "severe_low_weight": scoring.severe_low_weight,
        "insulin_weight": scoring.insulin_weight,
        "terminal_weight": scoring.terminal_weight,
        "glucose_scale_mg_dl": scoring.glucose_scale_mg_dl,
        "insulin_scale_u": scoring.insulin_scale_u,
    }
    row.update(_component_values(scored.components))
    return row


def _selection_row(definition, search, selection):
    row = {
        "evaluation_event_id": selection.evaluation_event_id,
        "episode_id": search.episode_id, "dataset": definition.dataset,
        "patient_id": search.patient_id, "split": definition.split,
        "arm": search.arm_name, "decision_timestamp": search.decision_timestamp,
        "parameter_estimation_timestamp": search.parameter_estimation_timestamp,
        "status": selection.status, "no_feasible_reason": selection.no_feasible_reason,
        "selected_candidate_id": selection.selected_candidate_id,
        "selected_dose_u": selection.selected_dose_u,
        "selected_score": selection.selected_score,
        "lowest_numerical_score": selection.lowest_numerical_score,
        "tie_candidate_ids": "|".join(selection.tie_candidate_ids),
        "tie_breaking_reason": selection.tie_breaking_reason,
        "feasible_candidate_count": selection.feasible_candidate_count,
        "rejected_candidate_count": selection.rejected_candidate_count,
        "rejection_reason_counts_json": json.dumps(selection.rejection_reason_counts, sort_keys=True),
        "selected_at_upper_grid_boundary": selection.selected_at_upper_grid_boundary,
        "additional_bolus_for_simulation_u": selection.additional_bolus_for_simulation_u,
        "action_delivered_by_step10": False,
    }
    row.update({f"selected_{key}": value for key, value in _component_values(selection.selected_components).items()})
    return row


def _selections_equal(first, second):
    return bool(
        first.status == second.status
        and first.selected_candidate_id == second.selected_candidate_id
        and first.selected_dose_u == second.selected_dose_u
        and first.selected_score == second.selected_score
        and first.tie_candidate_ids == second.tie_candidate_ids
        and first.rejection_reason_counts == second.rejection_reason_counts
    )


def run_selection_diagnostic(
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
):
    started = time.perf_counter()
    dataset_path, checkpoint_path, out = Path(dataset_path), Path(checkpoint_path), Path(output_directory)
    out.mkdir(parents=True, exist_ok=True)
    trigger, trigger_hash = load_trigger_configuration(trigger_configuration_path)
    consumption, consumption_hash = load_consumption_configuration(consumption_configuration_path)
    search_configuration, search_hash = load_search_configuration(search_configuration_path)
    expected_candidate_count = len(generate_bolus_candidates(search_configuration))
    scoring, scoring_hash = load_scoring_configuration(scoring_configuration_path)
    refresh = RefreshConfiguration(refresh_minutes)
    data, patient_splits, loader_audit = read_optimization_data(dataset_path)
    frozen = load_frozen_gru(checkpoint_path, expected_sha256=FROZEN_CHECKPOINT_SHA256)
    if patient_splits != frozen.checkpoint["patient_splits"]:
        raise ValueError("Patient splits differ from the frozen checkpoint")
    selected_episodes = select_diagnostic_episodes(build_episode_definitions(data), episodes_per_patient)
    groups = {
        (str(dataset), str(patient)): group.sort_values("timestamp").reset_index(drop=True)
        for (dataset, patient), group in data[data["split"].isin(ALLOWED_SPLITS)].groupby(
            ["dataset", "patient_id"], sort=False
        )
    }
    episode_rows, scored_rows, selection_rows, rejection_rows, check_rows = [], [], [], [], []
    attempted_arms = completed_arms = lifecycle_failures = ongoing_failures = 0
    construction_failures = paired_checks = paired_failures = 0
    schedule_checks = []
    for definition in selected_episodes:
        episode = initialize_episode(
            groups[(definition.dataset, definition.patient_id)], definition, frozen,
            weight_kg=weight_kg, substeps=substeps,
        )
        if episode.initialization_status != "initialized":
            ongoing_failures += 1
            continue
        arms = (episode.baseline_arm, episode.optimized_arm)
        for arm in arms:
            arm.detector_state = create_detector_state(arm, definition)
        attempted_arms += 2
        for _ in range(288):
            if not all(arm.status == "active" for arm in arms):
                break
            current = (
                episode.environment.reveal(episode.baseline_arm),
                episode.environment.reveal(episode.optimized_arm),
            )
            detections, boundary_selections = [], []
            for arm, current_events in zip(arms, current):
                selection = None
                try:
                    current_glucose_mg_dl(arm, weight_kg=weight_kg)
                    refresh_parameters_if_due(arm, frozen, current_events, refresh)
                    detection = detect_evaluation_event(
                        arm, current_events, trigger, arm.detector_state, weight_kg=weight_kg
                    )
                    detections.append(detection)
                    if detection.event is not None:
                        before = _capture_arm(arm)
                        try:
                            snapshot = create_decision_snapshot(
                                arm, current_events, detection.event, arm.detector_state
                            )
                            search = simulate_bolus_candidates(
                                snapshot, search_configuration, consumption,
                                weight_kg=weight_kg, substeps=substeps,
                                search_configuration_hash=search_hash,
                            )
                            selection = score_and_select_candidates(
                                search, search_configuration, scoring
                            )
                            for scored in selection.scored_candidates:
                                scored_rows.append(_scored_row(
                                    definition, search, selection, scored, scoring
                                ))
                                if scored.rejection_reason is not None:
                                    rejection_rows.append({
                                        "evaluation_event_id": selection.evaluation_event_id,
                                        "episode_id": search.episode_id,
                                        "patient_id": search.patient_id, "arm": search.arm_name,
                                        "candidate_index": scored.candidate_index,
                                        "candidate_id": scored.candidate_id,
                                        "dose_u": scored.dose_u,
                                        "failure_class": scored.feasibility_status,
                                        "rejection_reason": scored.rejection_reason,
                                    })
                            selection_rows.append(_selection_row(definition, search, selection))
                            score_sum_pass = all(
                                item.components is None or abs(
                                    item.components.total_score - sum((
                                        item.components.weighted_low,
                                        item.components.weighted_high,
                                        item.components.weighted_severe_low,
                                        item.components.weighted_insulin,
                                        item.components.weighted_terminal,
                                    ))
                                ) <= 1e-12
                                for item in selection.scored_candidates
                            )
                            check_rows.append({
                                "evaluation_event_id": selection.evaluation_event_id,
                                "episode_id": search.episode_id,
                                "patient_id": search.patient_id, "arm": search.arm_name,
                                "decision_timestamp": search.decision_timestamp,
                                "candidate_inventory_pass": len(selection.scored_candidates)
                                == search.generated_candidate_count,
                                "score_explanation_pass": score_sum_pass,
                                "selection_contract_pass": (
                                    selection.status == "selected"
                                    and selection.selected_candidate_id is not None
                                    and selection.selected_dose_u is not None
                                ) or (
                                    selection.status == "no_feasible_recommendation"
                                    and selection.selected_candidate_id is None
                                    and selection.selected_dose_u is None
                                    and selection.additional_bolus_for_simulation_u == 0.0
                                ),
                                "selection_no_mutation_pass": _arm_unchanged(arm, before),
                                "pending_event_preserved_pass": arm.detector_state.pending_event_id
                                == detection.event.event_id,
                                "no_step10_delivery_pass": arm.detector_state.deliveries == before["deliveries"],
                            })
                        except Exception:
                            construction_failures += 1
                            raise
                        acknowledge_evaluation(
                            arm.detector_state, detection.event.event_id,
                            status="completed", outcome="diagnostic_selection_not_delivered",
                            acknowledgement_timestamp=arm.current_timestamp,
                            selected_dose_u=selection.selected_dose_u,
                        )
                    boundary_selections.append(selection)
                    completion = complete_interval(
                        arm, current_events, current[0].recorded_bolus_u,
                        weight_kg=weight_kg, substeps=substeps,
                    )
                    if not completion.success:
                        ongoing_failures += 1
                        raise RuntimeError(completion.failure_reason)
                except Exception as error:
                    arm.status = "failed_step10_diagnostic"
                    arm.failure_reason = f"{type(error).__name__}:{error}"
            if len(detections) == 2:
                paired_checks += 1
                paired_ok = bool(
                    detections[0].evaluation_eligible == detections[1].evaluation_eligible
                    and detections[0].trigger_reasons == detections[1].trigger_reasons
                    and detections[0].suppression_reasons == detections[1].suppression_reasons
                )
                if len(boundary_selections) == 2 and all(x is not None for x in boundary_selections):
                    paired_ok = paired_ok and _selections_equal(*boundary_selections)
                paired_failures += int(not paired_ok)
        for arm in arms:
            completed = arm.status == "active" and arm.current_timestamp == definition.end_timestamp
            completed_arms += int(completed)
            lifecycle_failures += int(arm.detector_state.pending_event_id is not None)
            schedule_checks.append(verify_arm_refresh_schedule(arm, refresh, definition.end_timestamp))
            episode_rows.append({
                "episode_id": definition.episode_id, "dataset": definition.dataset,
                "patient_id": definition.patient_id, "split": definition.split,
                "arm": arm.arm_name, "start_timestamp": definition.start_timestamp,
                "end_timestamp": definition.end_timestamp,
                "status": "completed" if completed else arm.status,
                "failure_reason": arm.failure_reason,
            })

    scored_frame, selection_frame = pd.DataFrame(scored_rows), pd.DataFrame(selection_rows)
    rejection_columns = [
        "evaluation_event_id", "episode_id", "patient_id", "arm",
        "candidate_index", "candidate_id", "dose_u", "failure_class", "rejection_reason",
    ]
    rejection_frame = pd.DataFrame(rejection_rows, columns=rejection_columns)
    checks = pd.DataFrame(check_rows)
    pd.DataFrame(episode_rows).to_csv(out / "evaluated_episodes.csv", index=False)
    scored_frame.to_parquet(out / "scored_candidates.parquet", index=False)
    selection_frame.to_parquet(out / "selection_results.parquet", index=False)
    rejection_frame.to_csv(out / "candidate_rejections.csv", index=False)
    checks.to_csv(out / "verification_checks.csv", index=False)

    source_hashes = {path: sha256(path) for path in RELEVANT_SOURCE_FILES}
    dataset_hash = sha256(dataset_path)
    checkpoint_dataset_hash = frozen.checkpoint.get("data_sha256")
    configuration = {
        "step": 10, "scope": "feasibility, scoring and selection without delivery",
        "dataset": str(dataset_path.resolve()), "dataset_sha256": dataset_hash,
        "checkpoint": str(checkpoint_path.resolve()), "checkpoint_sha256": frozen.checkpoint_sha256,
        "checkpoint_dataset_sha256": checkpoint_dataset_hash,
        "dataset_hash_discrepancy": {
            "status": "unresolved",
            "current_dataset_matches_checkpoint_record": dataset_hash == checkpoint_dataset_hash,
        },
        "splits": list(ALLOWED_SPLITS), "testing_patients_used": False,
        "search_configuration_sha256": search_hash,
        "consumption_configuration_sha256": consumption_hash,
        "scoring_configuration": {
            "path": str(Path(scoring_configuration_path).resolve()), "sha256": scoring_hash,
            **scoring.__dict__,
            "hard_minimum_boundary": "inclusive; equality is feasible",
            "clinical_status": "experimental and not clinically validated",
        },
        "trigger_configuration_sha256": trigger_hash,
        "diagnostic_action_source": "externally supplied recorded action, identical in both arms",
        "selected_actions_delivered": False,
        "source_hashes": source_hashes,
        "expected_preserved_source_hashes": EXPECTED_SOURCE_HASHES,
        "loader_audit": loader_audit, "software_versions": _versions(),
    }
    (out / "configuration.json").write_text(json.dumps(configuration, indent=2, default=str) + "\n")

    check_columns = [name for name in checks.columns if name.endswith("_pass")]
    verification_failures = int((~checks[check_columns].all(axis=1)).sum()) if len(checks) else len(selection_frame)
    schedule_pass = bool(
        len(schedule_checks) == attempted_arms
        and all(item["ordered_exact_match"] for item in schedule_checks)
    )
    preservation_pass = bool(
        frozen.checkpoint_sha256 == FROZEN_CHECKPOINT_SHA256
        and all(source_hashes[path] == expected for path, expected in EXPECTED_SOURCE_HASHES.items())
    )
    inventory_pass = len(scored_frame) == len(selection_frame) * expected_candidate_count
    implementation_pass = bool(
        construction_failures == 0 and verification_failures == 0
        and paired_failures == 0 and lifecycle_failures == 0
        and schedule_pass and preservation_pass and inventory_pass
    )
    completion_pass = bool(completed_arms == attempted_arms and ongoing_failures == 0)
    selections = int((selection_frame["status"] == "selected").sum()) if len(selection_frame) else 0
    no_feasible = int((selection_frame["status"] == "no_feasible_recommendation").sum()) if len(selection_frame) else 0
    zero_selections = int(((selection_frame["status"] == "selected") & (selection_frame["selected_dose_u"] == 0)).sum()) if len(selection_frame) else 0
    upper = int(selection_frame["selected_at_upper_grid_boundary"].sum()) if len(selection_frame) else 0
    feasible_candidates = int((scored_frame["feasibility_status"] == "feasible").sum()) if len(scored_frame) else 0
    rejected_candidates = len(scored_frame) - feasible_candidates
    rejection_counts = rejection_frame["rejection_reason"].value_counts().to_dict() if len(rejection_frame) else {}
    summary = {
        "scope": "candidate feasibility, scoring and selection; no optimizer delivery",
        "episodes_attempted": len(selected_episodes), "arms_attempted": attempted_arms,
        "arms_completed_288_intervals": completed_arms,
        "evaluated_events": len(selection_frame), "scored_candidates": len(scored_frame),
        "feasible_candidates": feasible_candidates, "rejected_candidates": rejected_candidates,
        "candidate_rejection_reasons": rejection_counts,
        "successful_selections": selections,
        "zero_dose_selections": zero_selections,
        "no_feasible_recommendations": no_feasible,
        "upper_grid_boundary_selections": upper,
        "construction_failures": construction_failures,
        "ongoing_episode_failures": ongoing_failures,
        "verification_failures": verification_failures,
        "paired_selection_checks": paired_checks,
        "paired_selection_failures": paired_failures,
        "lifecycle_failures": lifecycle_failures,
        "strict_step6_refresh_schedule_pass": schedule_pass,
        "preservation_checks_pass": preservation_pass,
        "split_isolation_pass": not bool((selection_frame.get("split", pd.Series(dtype=str)) == "testing").any()),
        "implementation_verification_pass": implementation_pass,
        "simulation_completion_pass": completion_pass,
        "overall_pass": bool(implementation_pass and completion_pass),
        "selected_actions_delivered": False,
        "dataset_hash_discrepancy": "unresolved",
        "runtime_seconds": time.perf_counter() - started,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    (out / "summary.md").write_text("\n".join([
        "# Step 10 scoring and selection verification", "",
        f"Implementation verification: **{'PASS' if implementation_pass else 'FAIL'}**",
        f"Simulation completion: **{'PASS' if completion_pass else 'FAIL'}**",
        f"Overall result: **{'PASS' if summary['overall_pass'] else 'FAIL'}**", "",
        f"Events: {len(selection_frame)}", f"Scored candidates: {len(scored_frame)}",
        f"Selections/no-feasible: {selections}/{no_feasible}",
        f"Zero selections: {zero_selections}", f"Upper-grid selections: {upper}", "",
        "Recommendation rate is reported separately from implementation correctness.",
        "Selected and fallback actions were not delivered; recorded actions advanced both arms.",
        "The scoring policy is experimental and not clinically validated.",
        "The checkpoint/dataset hash discrepancy remains unresolved.", "",
    ]))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--checkpoint", default="baseline/model.pt")
    parser.add_argument("--out", default="results/bolus_optimization_migrated_final/step10_scoring_selection")
    parser.add_argument("--trigger-configuration", default=str(DEFAULT_TRIGGER_CONFIGURATION))
    parser.add_argument("--consumption-configuration", default=str(DEFAULT_CONSUMPTION_CONFIGURATION))
    parser.add_argument("--search-configuration", default=str(DEFAULT_SEARCH_CONFIGURATION))
    parser.add_argument("--scoring-configuration", default=str(DEFAULT_SCORING_CONFIGURATION))
    parser.add_argument("--episodes-per-patient", type=int, default=1)
    parser.add_argument("--refresh-minutes", type=int, default=120)
    parser.add_argument("--weight-kg", type=float, default=70.0)
    parser.add_argument("--substeps", type=int, default=5)
    args = parser.parse_args()
    if args.episodes_per_patient < 0 or args.weight_kg <= 0 or args.substeps <= 0:
        parser.error("episode count must be nonnegative; weight and substeps must be positive")
    summary = run_selection_diagnostic(
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
