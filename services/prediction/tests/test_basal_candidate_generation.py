from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import torch


PREDICTION_ROOT = Path(__file__).resolve().parents[1]
if str(PREDICTION_ROOT) not in sys.path:
    sys.path.insert(0, str(PREDICTION_ROOT))

from basal_optimization.candidate_generation import (
    EXAMPLE_CONFIGURATION_PATH,
    BasalSearchConfiguration,
    configuration_hash,
    extract_constant_baseline_rate,
    generate_basal_candidates,
    load_search_configuration,
)
from basal_optimization.preparation import PatientIdentity


def configuration(**overrides) -> BasalSearchConfiguration:
    values = {
        "configuration_version": "test-v1",
        "maximum_decrease_u_per_hour": 0.2,
        "maximum_increase_u_per_hour": 0.2,
        "absolute_minimum_u_per_hour": 0.0,
        "absolute_maximum_u_per_hour": 3.0,
        "increment_u_per_hour": 0.05,
        "maximum_candidate_count": 9,
        "intended_use": "Synthetic research test only",
    }
    values.update(overrides)
    return BasalSearchConfiguration(**values)


def snapshot(rate: float = 0.83):
    replay_start = pd.Timestamp("2027-01-02 00:00:00")
    replay = pd.DataFrame({
        "timestamp": pd.date_range(replay_start, periods=576, freq="5min"),
        "basal_rate_u_per_hour": np.full(576, rate, dtype=np.float64),
    })
    return SimpleNamespace(
        identity=PatientIdentity("synthetic", "patient-1"),
        simulation_start=replay_start,
        decision_timestamp=pd.Timestamp("2027-01-04 00:00:00"),
        replay_intervals=replay,
        physiological_state=torch.arange(10, dtype=torch.float32),
        parameters=torch.arange(7, dtype=torch.float32),
    )


def rates(result) -> list[float]:
    return [item.rate_u_per_hour for item in result.candidates]


class BasalCandidateGenerationTests(unittest.TestCase):
    def test_grid_is_centered_ascending_and_baseline_is_exactly_once(self):
        prepared = snapshot(0.833)
        result = generate_basal_candidates(prepared, configuration())
        self.assertEqual(
            rates(result),
            [0.633, 0.683, 0.733, 0.783, 0.833, 0.883, 0.933, 0.983, 1.033],
        )
        self.assertEqual(rates(result), sorted(rates(result)))
        baseline = [item for item in result.candidates if item.is_recorded_baseline]
        self.assertEqual(len(baseline), 1)
        self.assertEqual(baseline[0].rate_u_per_hour, 0.833)
        self.assertEqual(result.baseline_candidate_id, baseline[0].candidate_id)

    def test_relative_and_absolute_intersection_omits_non_grid_endpoints(self):
        prepared = snapshot(0.10)
        settings = configuration(
            maximum_decrease_u_per_hour=0.30,
            maximum_increase_u_per_hour=0.25,
            absolute_minimum_u_per_hour=0.02,
            absolute_maximum_u_per_hour=0.22,
            increment_u_per_hour=0.05,
            maximum_candidate_count=5,
        )
        result = generate_basal_candidates(prepared, settings)
        self.assertEqual(result.effective_lower_u_per_hour, 0.02)
        self.assertEqual(result.effective_upper_u_per_hour, 0.22)
        self.assertEqual(rates(result), [0.05, 0.10, 0.15, 0.20])
        self.assertNotIn(0.02, rates(result))
        self.assertNotIn(0.22, rates(result))

    def test_lower_clipping_prevents_negative_and_zero_baseline_is_supported(self):
        clipped = generate_basal_candidates(
            snapshot(0.03),
            configuration(
                maximum_decrease_u_per_hour=0.20,
                maximum_increase_u_per_hour=0.10,
                absolute_maximum_u_per_hour=1.0,
                increment_u_per_hour=0.05,
                maximum_candidate_count=5,
            ),
        )
        self.assertEqual(rates(clipped), [0.03, 0.08, 0.13])
        self.assertTrue(all(rate >= 0 for rate in rates(clipped)))

        zero = generate_basal_candidates(
            snapshot(0.0),
            configuration(
                maximum_decrease_u_per_hour=0.20,
                maximum_increase_u_per_hour=0.11,
                absolute_maximum_u_per_hour=1.0,
                increment_u_per_hour=0.05,
                maximum_candidate_count=3,
            ),
        )
        self.assertEqual(rates(zero), [0.0, 0.05, 0.10])
        self.assertTrue(zero.candidates[0].is_recorded_baseline)

    def test_invalid_configuration_values_are_rejected(self):
        numeric_fields = (
            "maximum_decrease_u_per_hour",
            "maximum_increase_u_per_hour",
            "absolute_minimum_u_per_hour",
            "absolute_maximum_u_per_hour",
            "increment_u_per_hour",
        )
        for field in numeric_fields:
            with self.subTest(boolean_field=field):
                with self.assertRaisesRegex(ValueError, "not Boolean"):
                    configuration(**{field: True})
        for increment in (0.0, -0.1, np.nan, np.inf):
            with self.subTest(increment=increment):
                with self.assertRaises(ValueError):
                    configuration(increment_u_per_hour=increment)
        for value in (np.nan, np.inf, -1.0):
            with self.subTest(bound=value):
                with self.assertRaises(ValueError):
                    configuration(maximum_increase_u_per_hour=value)
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            configuration(absolute_minimum_u_per_hour=2.0, absolute_maximum_u_per_hour=1.0)
        with self.assertRaisesRegex(ValueError, "positive integer"):
            configuration(maximum_candidate_count=True)
        with self.assertRaisesRegex(ValueError, "outside configured absolute bounds"):
            generate_basal_candidates(
                snapshot(0.83),
                configuration(absolute_minimum_u_per_hour=1.0),
            )

    def test_excessive_count_is_rejected_before_materialization(self):
        settings = configuration(
            maximum_decrease_u_per_hour=1.0,
            maximum_increase_u_per_hour=1_000_000_000.0,
            absolute_maximum_u_per_hour=1_000_000_001.0,
            increment_u_per_hour=1e-12,
            maximum_candidate_count=10,
        )
        with self.assertRaisesRegex(ValueError, "exceeding maximum_candidate_count=10"):
            generate_basal_candidates(snapshot(1.0), settings)

    def test_float32_candidate_collision_is_rejected(self):
        settings = configuration(
            maximum_decrease_u_per_hour=1e-8,
            maximum_increase_u_per_hour=1e-8,
            absolute_maximum_u_per_hour=2.0,
            increment_u_per_hour=1e-8,
            maximum_candidate_count=3,
        )
        with self.assertRaisesRegex(ValueError, "collapse in the simulator float32 dtype"):
            generate_basal_candidates(snapshot(1.0), settings)

    def test_recorded_constancy_tolerance_preserves_first_actual_value(self):
        prepared = snapshot(0.8330000000000001)
        prepared.replay_intervals.loc[100, "basal_rate_u_per_hour"] += 5e-10
        self.assertEqual(extract_constant_baseline_rate(prepared), 0.8330000000000001)

        varying = snapshot(0.83)
        varying.replay_intervals.loc[100, "basal_rate_u_per_hour"] += 1e-4
        with self.assertRaisesRegex(ValueError, "not constant.*varying trajectories"):
            extract_constant_baseline_rate(varying)

    def test_invalid_recorded_rates_are_rejected(self):
        cases = (
            (None, "missing or nonnumeric"),
            (np.nan, "missing or nonnumeric|nonfinite"),
            (np.inf, "nonfinite"),
            (-0.1, "negative"),
            (True, "Boolean"),
        )
        for value, message in cases:
            prepared = snapshot(0.83)
            prepared.replay_intervals["basal_rate_u_per_hour"] = prepared.replay_intervals[
                "basal_rate_u_per_hour"
            ].astype(object)
            prepared.replay_intervals.loc[100, "basal_rate_u_per_hour"] = value
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, message):
                    extract_constant_baseline_rate(prepared)

    def test_ids_and_configuration_hashes_are_deterministic(self):
        settings = configuration()
        first = generate_basal_candidates(snapshot(), settings)
        second = generate_basal_candidates(snapshot(), settings)
        self.assertEqual(first.configuration_hash, configuration_hash(settings))
        self.assertEqual(first.configuration_hash, second.configuration_hash)
        self.assertEqual(
            [item.candidate_id for item in first.candidates],
            [f"basal_{index:04d}" for index in range(9)],
        )
        self.assertEqual(first.candidates, second.candidates)

    def test_generation_does_not_mutate_prepared_snapshot(self):
        prepared = snapshot()
        replay_before = prepared.replay_intervals.copy(deep=True)
        state_before = prepared.physiological_state.clone()
        parameters_before = prepared.parameters.clone()
        generate_basal_candidates(prepared, configuration())
        pd.testing.assert_frame_equal(prepared.replay_intervals, replay_before)
        self.assertTrue(torch.equal(prepared.physiological_state, state_before))
        self.assertTrue(torch.equal(prepared.parameters, parameters_before))

    def test_explicit_example_configuration_loads_with_reproducible_hash(self):
        settings, loaded_hash = load_search_configuration(EXAMPLE_CONFIGURATION_PATH)
        self.assertEqual(loaded_hash, configuration_hash(settings))
        self.assertIn("not clinically validated", settings.intended_use)


if __name__ == "__main__":
    unittest.main()
