from __future__ import annotations

import dataclasses
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch


PREDICTION_ROOT = Path(__file__).resolve().parents[1]
if str(PREDICTION_ROOT) not in sys.path:
    sys.path.insert(0, str(PREDICTION_ROOT))

from final_model_adapter import verify_dataset
from bolus_optimization.candidate_inputs import (
    DEFAULT_CONSUMPTION_CONFIGURATION,
    load_consumption_configuration,
)
from bolus_optimization.candidate_search import (
    DEFAULT_SEARCH_CONFIGURATION,
    generate_bolus_candidates,
    load_search_configuration,
)
from bolus_optimization.configuration_loading import DEFAULT_RESEARCH_CONFIGURATION
from bolus_optimization.events import (
    DEFAULT_TRIGGER_CONFIGURATION,
    load_trigger_configuration,
)
from bolus_optimization.migrated_configuration import (
    DEFAULT_MIGRATED_CONFIGURATION,
    load_migrated_configuration,
)
from bolus_optimization.run_paired_episodes import (
    _run_optimizer,
    build_argument_parser,
    run_continuous_diagnostic,
)
from bolus_optimization.scoring import (
    DEFAULT_SCORING_CONFIGURATION,
    calculate_score_components,
    load_scoring_configuration,
)


PACKAGE = PREDICTION_ROOT / "bolus_optimization"
HISTORICAL_POLICY = PACKAGE / "historical_migrated_selected_configuration_v1.json"


class DefaultBolusConfigurationTests(unittest.TestCase):
    def test_all_default_loaders_resolve_the_canonical_policy(self):
        canonical = DEFAULT_RESEARCH_CONFIGURATION.resolve()
        for path in (
            DEFAULT_MIGRATED_CONFIGURATION,
            DEFAULT_SEARCH_CONFIGURATION,
            DEFAULT_SCORING_CONFIGURATION,
            DEFAULT_TRIGGER_CONFIGURATION,
            DEFAULT_CONSUMPTION_CONFIGURATION,
        ):
            self.assertEqual(path.resolve(), canonical)

        policy = load_migrated_configuration()
        search, _ = load_search_configuration()
        scoring, _ = load_scoring_configuration()
        trigger, _ = load_trigger_configuration()
        consumption, _ = load_consumption_configuration()
        self.assertEqual(search, policy.search)
        self.assertEqual(scoring, policy.scoring)
        self.assertEqual(trigger, policy.trigger)
        self.assertEqual(consumption, policy.consumption)

    def test_default_grid_is_exactly_zero_through_twenty_by_half_units(self):
        search, _ = load_search_configuration()
        doses = [item.bolus_u for item in generate_bolus_candidates(search)]
        self.assertEqual(doses, [index * 0.5 for index in range(41)])
        self.assertEqual(search.maximum_candidate_count, 41)

    def test_zero_insulin_penalty_reaches_actual_score_calculation(self):
        scoring, _ = load_scoring_configuration()
        components = calculate_score_components(
            torch.full((48,), 200.0, dtype=torch.float32), 20.0, scoring
        )
        self.assertGreater(components.insulin_component, 0.0)
        self.assertEqual(scoring.insulin_weight, 0.0)
        self.assertEqual(components.weighted_insulin, 0.0)
        self.assertEqual(
            components.total_score,
            components.weighted_low
            + components.weighted_high
            + components.weighted_severe_low
            + components.weighted_terminal,
        )

    def test_runtime_optimizer_passes_raw_search_directly_to_scoring(self):
        search_configuration, _ = load_search_configuration()
        scoring, _ = load_scoring_configuration()
        expected_search = object()
        expected_selection = object()
        event = mock.Mock(event_id="event")
        with mock.patch(
            "bolus_optimization.run_paired_episodes.create_decision_snapshot",
            return_value=object(),
        ), mock.patch(
            "bolus_optimization.run_paired_episodes.simulate_bolus_candidates",
            return_value=expected_search,
        ), mock.patch(
            "bolus_optimization.run_paired_episodes.score_and_select_candidates",
            return_value=expected_selection,
        ) as score:
            result = _run_optimizer(
                mock.Mock(), mock.Mock(), event, mock.Mock(),
                search_configuration, scoring,
                weight_kg=70.0, substeps=5,
                search_configuration_hash="hash",
            )
        score.assert_called_once_with(expected_search, search_configuration, scoring)
        self.assertIs(result.search, expected_search)
        self.assertIs(result.selection, expected_selection)

    def test_gated_and_residual_scoring_corrections_are_disabled(self):
        policy = load_migrated_configuration()
        candidate_scoring = policy.source_payload["candidate_scoring"]
        self.assertEqual(candidate_scoring["trajectory_source"], "raw_hovorka")
        self.assertIs(candidate_scoring["gated_endpoint_enabled"], False)
        self.assertIs(candidate_scoring["residual_correction_enabled"], False)
        residual = policy.source_payload["residual"]
        self.assertIs(residual["enabled"], False)
        self.assertIs(residual["affects_candidate_scoring"], False)
        self.assertIs(residual["affects_state_propagation"], False)

    def test_unspecified_settings_match_previous_migrated_policy(self):
        current = load_migrated_configuration()
        historical = load_migrated_configuration(HISTORICAL_POLICY)
        self.assertEqual(current.trigger, historical.trigger)
        self.assertEqual(current.consumption, historical.consumption)
        self.assertEqual(current.refresh, historical.refresh)
        self.assertEqual(
            current.search.bolus_increment_u,
            historical.search.bolus_increment_u,
        )
        self.assertEqual(
            current.search.candidate_batch_size,
            historical.search.candidate_batch_size,
        )
        current_score = dataclasses.asdict(current.scoring)
        historical_score = dataclasses.asdict(historical.scoring)
        for field in ("insulin_weight", "intended_use"):
            current_score.pop(field)
            historical_score.pop(field)
        self.assertEqual(current_score, historical_score)
        for section in ("source_selection", "simulator", "residual"):
            self.assertEqual(
                current.source_payload[section], historical.source_payload[section]
            )

    def test_standalone_runner_defaults_and_explicit_cli_overrides(self):
        canonical = str(DEFAULT_RESEARCH_CONFIGURATION)
        defaults = run_continuous_diagnostic.__kwdefaults__
        self.assertEqual(str(defaults["trigger_configuration_path"]), canonical)
        self.assertEqual(str(defaults["consumption_configuration_path"]), canonical)
        self.assertEqual(str(defaults["search_configuration_path"]), canonical)
        self.assertEqual(str(defaults["scoring_configuration_path"]), canonical)

        parser = build_argument_parser()
        default_args = parser.parse_args(["dataset.parquet"])
        self.assertEqual(default_args.trigger_configuration, canonical)
        self.assertEqual(default_args.consumption_configuration, canonical)
        self.assertEqual(default_args.search_configuration, canonical)
        self.assertEqual(default_args.scoring_configuration, canonical)
        overridden = parser.parse_args([
            "dataset.parquet",
            "--search-configuration", "custom-search.json",
            "--scoring-configuration", "custom-scoring.json",
        ])
        self.assertEqual(overridden.search_configuration, "custom-search.json")
        self.assertEqual(overridden.scoring_configuration, "custom-scoring.json")

    def test_explicit_standalone_component_files_still_load(self):
        historical_search, _ = load_search_configuration(
            PACKAGE / "bolus_search_configuration_v1.json"
        )
        historical_scoring, _ = load_scoring_configuration(
            PACKAGE / "scoring_configuration_v1.json"
        )
        self.assertEqual(historical_search.maximum_bolus_u, 2.0)
        self.assertEqual(historical_scoring.insulin_weight, 0.05)

    def test_arbitrary_explicit_component_override_still_loads(self):
        search, _ = load_search_configuration()
        scoring, _ = load_scoring_configuration()
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            search_path = directory / "search.json"
            scoring_path = directory / "scoring.json"
            search_payload = dataclasses.asdict(search)
            search_payload.update({"maximum_bolus_u": 1.0, "maximum_candidate_count": 3})
            scoring_payload = dataclasses.asdict(scoring)
            scoring_payload["insulin_weight"] = 0.25
            search_path.write_text(json.dumps(search_payload))
            scoring_path.write_text(json.dumps(scoring_payload))
            explicit_search, _ = load_search_configuration(search_path)
            explicit_scoring, _ = load_scoring_configuration(scoring_path)
        self.assertEqual(
            [item.bolus_u for item in generate_bolus_candidates(explicit_search)],
            [0.0, 0.5, 1.0],
        )
        self.assertEqual(explicit_scoring.insulin_weight, 0.25)

    def test_dataset_provenance_remains_strict_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong.parquet"
            path.write_bytes(b"not the protected dataset")
            with self.assertRaisesRegex(ValueError, "dataset SHA-256 mismatch"):
                verify_dataset(path)


if __name__ == "__main__":
    unittest.main()
