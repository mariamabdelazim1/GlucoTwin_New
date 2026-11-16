from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pandas as pd
import torch


PREDICTION_ROOT = Path(__file__).resolve().parents[1]
if str(PREDICTION_ROOT) not in sys.path:
    sys.path.insert(0, str(PREDICTION_ROOT))

from basal_optimization.candidate_generation import (
    BasalSearchConfiguration,
    generate_basal_candidates,
)
import basal_optimization.candidate_inputs as candidate_inputs_module
from basal_optimization.candidate_inputs import build_candidate_inputs
from basal_optimization.preparation import PatientIdentity


def configuration() -> BasalSearchConfiguration:
    return BasalSearchConfiguration(
        configuration_version="input-test-v1",
        maximum_decrease_u_per_hour=0.1,
        maximum_increase_u_per_hour=0.1,
        absolute_minimum_u_per_hour=0.0,
        absolute_maximum_u_per_hour=3.0,
        increment_u_per_hour=0.1,
        maximum_candidate_count=3,
        intended_use="Synthetic input-construction test only",
    )


def snapshot():
    start = pd.Timestamp("2027-01-02 00:00:00")
    timestamps = pd.date_range(start, periods=576, freq="5min")
    replay = pd.DataFrame({
        "timestamp": timestamps,
        "basal_rate_u_per_hour": np.full(576, 0.8, dtype=np.float64),
        "bolus_u": np.zeros(576, dtype=np.float64),
        "consumed_carbs_g": np.zeros(576, dtype=np.float64),
        "carbs_g": np.zeros(576, dtype=np.float64),
    })
    replay.loc[0, ["bolus_u", "consumed_carbs_g"]] = [1.25, 12.0]
    replay.loc[100, "bolus_u"] = 2.5
    replay.loc[200, "consumed_carbs_g"] = 30.0
    replay.loc[575, ["bolus_u", "consumed_carbs_g"]] = [0.75, 8.0]
    prepared = SimpleNamespace(
        identity=PatientIdentity("synthetic", "patient-1"),
        simulation_start=start,
        decision_timestamp=pd.Timestamp("2027-01-04 00:00:00"),
        replay_intervals=replay,
        initialization_intervals=pd.DataFrame({
            "bolus_u": [99.0], "consumed_carbs_g": [99.0]
        }),
        outcome_row_at_decision=pd.Series({
            "timestamp": pd.Timestamp("2027-01-04 00:00:00"),
            "bolus_u": 88.0,
            "consumed_carbs_g": 88.0,
        }),
        physiological_state=torch.arange(10, dtype=torch.float32),
        parameters=torch.arange(7, dtype=torch.float32),
    )
    prepared.clone_initial_conditions = lambda: SimpleNamespace(
        physiological_state=prepared.physiological_state.detach().clone(),
        parameters=prepared.parameters.detach().clone(),
    )
    return prepared


def build(prepared=None, candidate_set=None):
    prepared = snapshot() if prepared is None else prepared
    candidate_set = (
        generate_basal_candidates(prepared, configuration())
        if candidate_set is None
        else candidate_set
    )
    return prepared, candidate_set, build_candidate_inputs(prepared, candidate_set)


class BasalCandidateInputTests(unittest.TestCase):
    def test_shape_dtype_device_order_units_and_metadata(self):
        prepared, candidates, batch = build()
        self.assertEqual(batch.identity, prepared.identity)
        self.assertEqual(batch.candidate_count, 3)
        self.assertEqual(
            batch.input_names,
            ("basal_rate_u_per_hour", "bolus_u", "consumed_carbs_g"),
        )
        self.assertEqual(batch.input_units, ("U/hour", "U/interval", "g/interval"))
        self.assertEqual(batch.configuration_version, candidates.configuration_version)
        self.assertEqual(batch.configuration_hash, candidates.configuration_hash)
        for candidate in batch.candidates:
            self.assertEqual(tuple(candidate.interval_inputs.shape), (576, 3))
            self.assertEqual(candidate.interval_inputs.dtype, torch.float32)
            self.assertEqual(candidate.interval_inputs.device, prepared.physiological_state.device)
            self.assertEqual(tuple(candidate.initial_state.shape), (10,))
            self.assertEqual(tuple(candidate.parameters.shape), (7,))

    def test_input_and_output_timestamp_boundaries_are_exact(self):
        prepared, _, batch = build()
        self.assertEqual(batch.input_timestamps[0], prepared.simulation_start)
        self.assertEqual(
            batch.input_timestamps[-1], prepared.decision_timestamp - pd.Timedelta(minutes=5)
        )
        self.assertEqual(
            batch.expected_output_timestamps[0],
            prepared.simulation_start + pd.Timedelta(minutes=5),
        )
        self.assertEqual(batch.expected_output_timestamps[-1], prepared.decision_timestamp)
        self.assertNotIn(prepared.decision_timestamp, batch.input_timestamps)

    def test_constant_candidate_basal_and_event_timing_are_preserved(self):
        prepared, candidate_set, batch = build()
        for metadata, candidate in zip(candidate_set.candidates, batch.candidates):
            self.assertTrue(
                torch.equal(
                    candidate.interval_inputs[:, 0],
                    torch.full((576,), metadata.rate_u_per_hour, dtype=torch.float32),
                )
            )
            self.assertEqual(float(candidate.interval_inputs[0, 1]), 1.25)
            self.assertEqual(float(candidate.interval_inputs[0, 2]), 12.0)
            self.assertEqual(float(candidate.interval_inputs[100, 1]), 2.5)
            self.assertEqual(float(candidate.interval_inputs[200, 2]), 30.0)
            self.assertEqual(float(candidate.interval_inputs[575, 1]), 0.75)
            self.assertEqual(float(candidate.interval_inputs[575, 2]), 8.0)

    def test_s_events_occur_once_and_t_or_initialization_events_are_excluded(self):
        _, _, batch = build()
        candidate = batch.candidates[0]
        self.assertEqual(int((candidate.interval_inputs[:, 1] == 1.25).sum()), 1)
        self.assertEqual(int((candidate.interval_inputs[:, 2] == 12.0).sum()), 1)
        self.assertNotIn(88.0, candidate.interval_inputs[:, 1].tolist())
        self.assertNotIn(88.0, candidate.interval_inputs[:, 2].tolist())
        self.assertNotIn(99.0, candidate.interval_inputs[:, 1].tolist())
        self.assertNotIn(99.0, candidate.interval_inputs[:, 2].tolist())

    def test_announced_carbohydrate_does_not_create_ingestion(self):
        prepared = snapshot()
        prepared.replay_intervals.loc[50, "carbs_g"] = 75.0
        prepared.replay_intervals.loc[50, "consumed_carbs_g"] = 0.0
        _, _, batch = build(prepared)
        for candidate in batch.candidates:
            self.assertEqual(float(candidate.interval_inputs[50, 2]), 0.0)

    def test_microsecond_precision_passes_but_genuine_shift_fails(self):
        prepared = snapshot()
        prepared.replay_intervals["timestamp"] = pd.DatetimeIndex(
            prepared.replay_intervals["timestamp"]
        ).as_unit("us")
        build(prepared)
        before = prepared.replay_intervals.copy(deep=True)
        prepared.replay_intervals.loc[100, "timestamp"] += pd.Timedelta(microseconds=1)
        shifted = prepared.replay_intervals.copy(deep=True)
        with self.assertRaisesRegex(ValueError, "exactly cover"):
            build(prepared)
        pd.testing.assert_frame_equal(prepared.replay_intervals, shifted)
        self.assertNotEqual(before.loc[100, "timestamp"], shifted.loc[100, "timestamp"])

    def test_invalid_lengths_boundaries_and_metadata_are_rejected(self):
        prepared = snapshot()
        candidate_set = generate_basal_candidates(prepared, configuration())
        cases = (
            (prepared, replace(candidate_set, identity=PatientIdentity("other", "patient")), "identity"),
            (prepared, replace(candidate_set, decision_timestamp=pd.Timestamp("2027-01-05")), "decision"),
            (prepared, replace(candidate_set, replay_interval_count=575), "576 replay"),
            (prepared, replace(candidate_set, candidate_count=2), "Candidate count"),
            (prepared, replace(candidate_set, baseline_candidate_id="wrong"), "Baseline candidate ID"),
            (prepared, replace(candidate_set, baseline_rate_u_per_hour=0.9), "Baseline candidate rate"),
        )
        for item, metadata, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    build_candidate_inputs(item, metadata)

        shortened = snapshot()
        shortened.replay_intervals = shortened.replay_intervals.iloc[:-1].copy()
        with self.assertRaisesRegex(ValueError, "576 intervals"):
            build(shortened)

    def test_invalid_candidate_ids_and_baseline_flags_are_rejected(self):
        prepared = snapshot()
        candidate_set = generate_basal_candidates(prepared, configuration())
        duplicated = list(candidate_set.candidates)
        duplicated[1] = replace(duplicated[1], candidate_id=duplicated[0].candidate_id)
        with self.assertRaisesRegex(ValueError, "unique"):
            build_candidate_inputs(prepared, replace(candidate_set, candidates=tuple(duplicated)))

        unflagged = tuple(replace(item, is_recorded_baseline=False) for item in candidate_set.candidates)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            build_candidate_inputs(prepared, replace(candidate_set, candidates=unflagged))

        malformed_flag = list(candidate_set.candidates)
        malformed_flag[0] = replace(malformed_flag[0], is_recorded_baseline=1)
        with self.assertRaisesRegex(ValueError, "baseline flag must be Boolean"):
            build_candidate_inputs(
                prepared,
                replace(candidate_set, candidates=tuple(malformed_flag)),
            )

        for value, message in ((True, "not Boolean"), (np.inf, "finite"), (-0.1, "nonnegative")):
            malformed = list(candidate_set.candidates)
            malformed[0] = replace(malformed[0], rate_u_per_hour=value)
            with self.subTest(rate=value):
                with self.assertRaisesRegex(ValueError, message):
                    build_candidate_inputs(
                        prepared,
                        replace(candidate_set, candidates=tuple(malformed)),
                    )

    def test_invalid_recorded_inputs_are_rejected_without_mutation(self):
        cases = (
            ("bolus_u", None, "missing or nonnumeric"),
            ("bolus_u", True, "Boolean"),
            ("bolus_u", np.inf, "nonfinite"),
            ("consumed_carbs_g", -1.0, "negative"),
        )
        for column, value, message in cases:
            prepared = snapshot()
            prepared.replay_intervals[column] = prepared.replay_intervals[column].astype(object)
            prepared.replay_intervals.loc[20, column] = value
            before = prepared.replay_intervals.copy(deep=True)
            with self.subTest(column=column, value=value):
                with self.assertRaisesRegex(ValueError, message):
                    build(prepared)
            pd.testing.assert_frame_equal(prepared.replay_intervals, before)

        missing_column = snapshot()
        missing_column.replay_intervals = missing_column.replay_intervals.drop(columns="bolus_u")
        with self.assertRaisesRegex(ValueError, "missing required"):
            build(missing_column)

    def test_float64_recorded_values_overflowing_float32_are_rejected(self):
        for column in ("bolus_u", "consumed_carbs_g"):
            prepared = snapshot()
            prepared.replay_intervals.loc[20, column] = 1e40
            before = prepared.replay_intervals.copy(deep=True)
            with self.subTest(column=column):
                with self.assertRaisesRegex(
                    ValueError,
                    rf"{column} becomes nonfinite after float32 conversion.*2027-01-02 01:40:00",
                ):
                    build(prepared)
            pd.testing.assert_frame_equal(prepared.replay_intervals, before)

    def test_finite_float32_values_with_overflowing_sum_are_rejected(self):
        prepared = snapshot()
        finite_float32 = float(np.finfo(np.float32).max / 4)
        prepared.replay_intervals["bolus_u"] = finite_float32
        before = prepared.replay_intervals.copy(deep=True)
        with self.assertRaisesRegex(
            ValueError,
            "Recorded bolus_u expected total after float32 reduction is nonfinite",
        ):
            build(prepared)
        pd.testing.assert_frame_equal(prepared.replay_intervals, before)

    def test_candidate_rate_overflowing_float32_is_rejected_actionably(self):
        prepared = snapshot()
        candidate_set = generate_basal_candidates(prepared, configuration())
        malformed = list(candidate_set.candidates)
        malformed[0] = replace(malformed[0], rate_u_per_hour=1e40)
        before = prepared.replay_intervals.copy(deep=True)
        with self.assertRaisesRegex(
            ValueError,
            "Candidate basal_0000 basal_rate_u_per_hour becomes nonfinite after float32 conversion",
        ):
            build_candidate_inputs(
                prepared,
                replace(candidate_set, candidates=tuple(malformed)),
            )
        pd.testing.assert_frame_equal(prepared.replay_intervals, before)

    def test_nonfinite_expected_and_represented_basal_totals_are_rejected(self):
        prepared = snapshot()
        candidate_set = generate_basal_candidates(prepared, configuration())
        with mock.patch.object(candidate_inputs_module, "REPLAY_HOURS", float("inf")):
            with self.assertRaisesRegex(
                ValueError,
                "Candidate basal_0000 expected basal_rate_u_per_hour total is nonfinite",
            ):
                build_candidate_inputs(prepared, candidate_set)

        huge_but_float32_finite = float(np.finfo(np.float32).max / 4)
        malformed = list(candidate_set.candidates)
        malformed[0] = replace(
            malformed[0],
            rate_u_per_hour=huge_but_float32_finite,
        )
        with self.assertRaisesRegex(
            ValueError,
            "Candidate basal_0000 represented basal_rate_u_per_hour total is nonfinite",
        ):
            build_candidate_inputs(
                prepared,
                replace(candidate_set, candidates=tuple(malformed)),
            )

    def test_accounting_and_shared_recorded_columns(self):
        prepared, _, batch = build()
        expected_bolus = float(torch.tensor(
            prepared.replay_intervals["bolus_u"].to_numpy(), dtype=torch.float32
        ).sum())
        expected_carbs = float(torch.tensor(
            prepared.replay_intervals["consumed_carbs_g"].to_numpy(), dtype=torch.float32
        ).sum())
        reference_recorded = batch.candidates[0].interval_inputs[:, 1:]
        for candidate in batch.candidates:
            self.assertAlmostEqual(candidate.basal_total_u, candidate.rate_u_per_hour * 48, places=4)
            self.assertEqual(candidate.bolus_total_u, expected_bolus)
            self.assertEqual(candidate.consumed_carbs_total_g, expected_carbs)
            self.assertTrue(torch.equal(candidate.interval_inputs[:, 1:], reference_recorded))

    def test_candidate_storage_is_independent_and_source_is_unchanged(self):
        prepared = snapshot()
        replay_before = prepared.replay_intervals.copy(deep=True)
        state_before = prepared.physiological_state.clone()
        parameters_before = prepared.parameters.clone()
        _, _, batch = build(prepared)
        first, second = batch.candidates[:2]
        self.assertNotEqual(first.interval_inputs.data_ptr(), second.interval_inputs.data_ptr())
        self.assertNotEqual(first.initial_state.data_ptr(), second.initial_state.data_ptr())
        self.assertNotEqual(first.parameters.data_ptr(), second.parameters.data_ptr())
        first.interval_inputs[0, 0] += 1
        first.initial_state[0] += 1
        first.parameters[0] += 1
        self.assertNotEqual(first.interval_inputs[0, 0], second.interval_inputs[0, 0])
        self.assertNotEqual(first.initial_state[0], second.initial_state[0])
        self.assertNotEqual(first.parameters[0], second.parameters[0])
        pd.testing.assert_frame_equal(prepared.replay_intervals, replay_before)
        self.assertTrue(torch.equal(prepared.physiological_state, state_before))
        self.assertTrue(torch.equal(prepared.parameters, parameters_before))


if __name__ == "__main__":
    unittest.main()
