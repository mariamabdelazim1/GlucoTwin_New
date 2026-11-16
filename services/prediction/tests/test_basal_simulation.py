from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

import pandas as pd
import torch


PREDICTION_ROOT = Path(__file__).resolve().parents[1]
if str(PREDICTION_ROOT) not in sys.path:
    sys.path.insert(0, str(PREDICTION_ROOT))

from basal_optimization.candidate_inputs import (
    PHYSIOLOGICAL_INPUT_UNITS,
    BasalCandidateInputBatch,
    CandidatePhysiologicalInputs,
)
from basal_optimization.preparation import PatientIdentity
from basal_optimization.simulation import simulate_candidate_batch
from bolus_optimization.physiology import initialize_state, predict_from_state


PARAMETERS = torch.tensor(
    [0.00512, 0.00082, 0.052, 55.0, 40.0, 0.0161, 0.0097],
    dtype=torch.float32,
)


def initial_state() -> torch.Tensor:
    glucose = torch.full((73,), 110.0, dtype=torch.float32)
    history = torch.zeros((72, 3), dtype=torch.float32)
    history[:, 0] = 0.8
    initialized = initialize_state(glucose, history, PARAMETERS, weight_kg=70.0, substeps=5)
    if not initialized.validity.all_valid:
        raise RuntimeError(initialized.validity.failures)
    return initialized.state


def input_batch(rates=(0.75, 0.8, 0.85)) -> BasalCandidateInputBatch:
    start = pd.Timestamp("2027-01-02 00:00:00")
    input_timestamps = tuple(pd.date_range(start, periods=576, freq="5min"))
    output_timestamps = tuple(timestamp + pd.Timedelta(minutes=5) for timestamp in input_timestamps)
    state = initial_state()
    candidates = []
    baseline_index = 1 if len(rates) > 1 else 0
    for index, rate in enumerate(rates):
        inputs = torch.zeros((576, 3), dtype=torch.float32)
        inputs[:, 0] = rate
        inputs[0, 1] = 0.5
        inputs[0, 2] = 10.0
        inputs[144, 1] = 1.0
        inputs[144, 2] = 20.0
        inputs[432, 1] = 0.75
        inputs[432, 2] = 15.0
        candidates.append(CandidatePhysiologicalInputs(
            candidate_id=f"basal_{index:04d}",
            rate_u_per_hour=rate,
            is_recorded_baseline=index == baseline_index,
            interval_inputs=inputs,
            initial_state=state.clone(),
            parameters=PARAMETERS.clone(),
            basal_total_u=float(rate * 48),
            bolus_total_u=float(inputs[:, 1].sum()),
            consumed_carbs_total_g=float(inputs[:, 2].sum()),
        ))
    return BasalCandidateInputBatch(
        identity=PatientIdentity("synthetic", "patient-1"),
        decision_timestamp=pd.Timestamp("2027-01-04 00:00:00"),
        replay_start_timestamp=start,
        replay_end_timestamp=pd.Timestamp("2027-01-04 00:00:00"),
        input_names=("basal_rate_u_per_hour", "bolus_u", "consumed_carbs_g"),
        input_units=PHYSIOLOGICAL_INPUT_UNITS,
        input_timestamps=input_timestamps,
        expected_output_timestamps=output_timestamps,
        configuration_version="simulation-test-v1",
        configuration_hash="simulation-test-hash",
        baseline_candidate_id=f"basal_{baseline_index:04d}",
        candidate_count=len(candidates),
        candidates=tuple(candidates),
        baseline_replacement_note="synthetic fixture",
    )


class BasalSimulationTests(unittest.TestCase):
    def test_valid_candidates_have_576_aligned_outputs_and_metadata(self):
        batch = input_batch()
        result = simulate_candidate_batch(batch, candidate_batch_size=2)
        self.assertEqual(result.candidate_count, 3)
        self.assertEqual(result.valid_candidate_count, 3)
        self.assertEqual(result.failed_candidate_count, 0)
        self.assertEqual(result.weight_kg, 70.0)
        self.assertEqual(result.substeps, 5)
        self.assertEqual(result.interval_minutes, 5.0)
        self.assertEqual(result.output_timestamps[0], pd.Timestamp("2027-01-02 00:05:00"))
        self.assertEqual(result.output_timestamps[-1], pd.Timestamp("2027-01-04 00:00:00"))
        self.assertFalse(result.state_trajectory_returned)
        for candidate in result.candidates:
            self.assertEqual(candidate.simulation_status, "simulation_valid")
            self.assertEqual(tuple(candidate.predicted_glucose_mg_dl.shape), (576,))
            self.assertEqual(candidate.available_prediction_steps, 576)
            self.assertEqual(tuple(candidate.final_state.shape), (10,))
            self.assertEqual(tuple(candidate.fixed_parameters.shape), (7,))
            self.assertIsNone(candidate.failure)
            self.assertIsNotNone(candidate.minimum_glucose_mg_dl)
            self.assertIsNotNone(candidate.maximum_glucose_mg_dl)
            self.assertIsNotNone(candidate.endpoint_glucose_mg_dl)

    def test_results_match_direct_authoritative_simulator_call(self):
        batch = input_batch()
        result = simulate_candidate_batch(batch, candidate_batch_size=2)
        source = batch.candidates[0]
        direct = predict_from_state(
            source.initial_state,
            source.parameters,
            source.interval_inputs,
            weight_kg=70.0,
            substeps=5,
        )
        self.assertTrue(torch.equal(result.candidates[0].predicted_glucose_mg_dl, direct.glucose_mg_dl))
        self.assertTrue(torch.equal(result.candidates[0].final_state, direct.final_state))

    def test_continuous_48_hours_matches_two_sequential_days(self):
        batch = input_batch((0.8,))
        source = batch.candidates[0]
        full = simulate_candidate_batch(
            replace(batch, baseline_candidate_id="basal_0000"), candidate_batch_size=1
        ).candidates[0]
        first_day = predict_from_state(
            source.initial_state, source.parameters, source.interval_inputs[:288],
            weight_kg=70.0, substeps=5,
        )
        second_day = predict_from_state(
            first_day.final_state, source.parameters, source.interval_inputs[288:],
            weight_kg=70.0, substeps=5,
        )
        sequential = torch.cat((first_day.glucose_mg_dl, second_day.glucose_mg_dl))
        self.assertTrue(torch.equal(full.predicted_glucose_mg_dl, sequential))
        self.assertTrue(torch.equal(full.final_state, second_day.final_state))

    def test_parameters_and_source_tensors_are_unchanged(self):
        batch = input_batch()
        before = tuple(
            (candidate.interval_inputs.clone(), candidate.initial_state.clone(), candidate.parameters.clone())
            for candidate in batch.candidates
        )
        result = simulate_candidate_batch(batch)
        for candidate, original, simulated in zip(batch.candidates, before, result.candidates):
            self.assertTrue(torch.equal(candidate.interval_inputs, original[0]))
            self.assertTrue(torch.equal(candidate.initial_state, original[1]))
            self.assertTrue(torch.equal(candidate.parameters, original[2]))
            self.assertTrue(torch.equal(simulated.fixed_parameters, original[2]))

    def test_only_materialized_three_column_inputs_determine_trajectory(self):
        batch = input_batch()
        first = simulate_candidate_batch(batch)
        unrelated_recorded_cgm = torch.linspace(40.0, 400.0, 576)
        unrelated_recorded_cgm.add_(123.0)
        second = simulate_candidate_batch(batch)
        for left, right in zip(first.candidates, second.candidates):
            self.assertTrue(torch.equal(left.predicted_glucose_mg_dl, right.predicted_glucose_mg_dl))
        self.assertEqual(
            batch.input_names,
            ("basal_rate_u_per_hour", "bolus_u", "consumed_carbs_g"),
        )

    def test_events_at_s_are_applied_once(self):
        batch = input_batch((0.8,))
        batch = replace(batch, baseline_candidate_id="basal_0000")
        with_event = simulate_candidate_batch(batch).candidates[0]
        source = batch.candidates[0]
        no_event_inputs = source.interval_inputs.clone()
        no_event_inputs[0, 1:] = 0.0
        direct_without = predict_from_state(
            source.initial_state, source.parameters, no_event_inputs,
            weight_kg=70.0, substeps=5,
        )
        self.assertFalse(torch.equal(with_event.predicted_glucose_mg_dl, direct_without.glucose_mg_dl))
        direct_once = predict_from_state(
            source.initial_state, source.parameters, source.interval_inputs,
            weight_kg=70.0, substeps=5,
        )
        self.assertTrue(torch.equal(with_event.predicted_glucose_mg_dl, direct_once.glucose_mg_dl))

    def test_results_have_independent_mutable_storage(self):
        result = simulate_candidate_batch(input_batch())
        first, second = result.candidates[:2]
        self.assertNotEqual(first.predicted_glucose_mg_dl.data_ptr(), second.predicted_glucose_mg_dl.data_ptr())
        self.assertNotEqual(first.final_state.data_ptr(), second.final_state.data_ptr())
        self.assertNotEqual(first.fixed_parameters.data_ptr(), second.fixed_parameters.data_ptr())
        second_before = second.predicted_glucose_mg_dl.clone()
        first.predicted_glucose_mg_dl[0] += 1
        first.final_state[0] += 1
        first.fixed_parameters[0] += 1
        self.assertTrue(torch.equal(second.predicted_glucose_mg_dl, second_before))

    def test_invalid_candidate_is_isolated_and_reported(self):
        batch = input_batch()
        malformed = list(batch.candidates)
        bad_state = malformed[1].initial_state.clone()
        bad_state[1] = -1.0
        malformed[1] = replace(malformed[1], initial_state=bad_state)
        result = simulate_candidate_batch(replace(batch, candidates=tuple(malformed)))
        self.assertEqual(result.valid_candidate_count, 2)
        self.assertEqual(result.failed_candidate_count, 1)
        failed = result.candidates[1]
        self.assertEqual(failed.simulation_status, "simulation_failed")
        self.assertEqual(failed.available_prediction_steps, 0)
        self.assertEqual(failed.failure.first_failing_interval, -1)
        self.assertIn("negative_state_compartments", failed.failure.reason)
        self.assertTrue(torch.isnan(failed.predicted_glucose_mg_dl).all())
        self.assertEqual(result.candidates[0].simulation_status, "simulation_valid")
        self.assertEqual(result.candidates[2].simulation_status, "simulation_valid")

    def test_candidate_batch_sizes_preserve_numerical_results(self):
        batch = input_batch()
        one = simulate_candidate_batch(batch, candidate_batch_size=1)
        three = simulate_candidate_batch(batch, candidate_batch_size=3)
        for left, right in zip(one.candidates, three.candidates):
            self.assertTrue(torch.allclose(
                left.predicted_glucose_mg_dl, right.predicted_glucose_mg_dl,
                rtol=1e-6, atol=1e-5, equal_nan=True,
            ))
            self.assertTrue(torch.allclose(
                left.final_state, right.final_state,
                rtol=1e-6, atol=1e-5, equal_nan=True,
            ))

    def test_malformed_shapes_timestamps_dtypes_devices_and_inputs_are_rejected(self):
        batch = input_batch()
        first = batch.candidates[0]
        cases = (
            (replace(first, interval_inputs=first.interval_inputs[:-1]), "shape"),
            (replace(first, interval_inputs=first.interval_inputs.double()), "torch.float32"),
            (replace(first, interval_inputs=torch.full_like(first.interval_inputs, torch.nan)), "nonfinite"),
        )
        for malformed, message in cases:
            candidates = (malformed, *batch.candidates[1:])
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    simulate_candidate_batch(replace(batch, candidates=candidates))

        shifted = list(batch.expected_output_timestamps)
        shifted[10] += pd.Timedelta(minutes=1)
        with self.assertRaisesRegex(ValueError, "output timestamps"):
            simulate_candidate_batch(replace(batch, expected_output_timestamps=tuple(shifted)))

        meta_state = torch.empty((10,), dtype=torch.float32, device="meta")
        device_mismatch = replace(first, initial_state=meta_state)
        with self.assertRaisesRegex(ValueError, "share a device"):
            simulate_candidate_batch(
                replace(batch, candidates=(device_mismatch, *batch.candidates[1:]))
            )


if __name__ == "__main__":
    unittest.main()
