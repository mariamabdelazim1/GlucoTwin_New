from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import torch


PREDICTION_ROOT = Path(__file__).resolve().parents[1]
if str(PREDICTION_ROOT) not in sys.path:
    sys.path.insert(0, str(PREDICTION_ROOT))

from basal_optimization.development_reliability import select_development_windows
from basal_optimization.preparation import PatientIdentity
from basal_optimization.reliability import ReliabilityCriteria, assess_baseline_reliability
from basal_optimization.simulation import (
    BasalCandidateSimulationResult,
    BasalSimulationBatchResult,
)


def fixture(*, errors=None, timezone=None, timestamp_unit="ns", outcome=True):
    start = pd.Timestamp("2027-01-02 00:00:00", tz=timezone)
    decision = start + pd.Timedelta(hours=48)
    replay_times = pd.date_range(start, periods=576, freq="5min").as_unit(timestamp_unit)
    outputs = pd.date_range(start + pd.Timedelta(minutes=5), periods=576, freq="5min")
    observations = np.arange(576, dtype=np.float64) / 10.0 + 100.0
    error = np.zeros(576) if errors is None else np.asarray(errors, dtype=np.float64)
    predictions = observations + error
    replay = pd.DataFrame({
        "timestamp": replay_times,
        "cgm_mg_dl": np.concatenate(([77.0], observations[:-1])),
        "cgm_measurement_timestamp": replay_times,
    })
    outcome_row = None
    if outcome:
        outcome_row = pd.Series({
            "timestamp": pd.Timestamp(decision).as_unit(timestamp_unit),
            "cgm_mg_dl": observations[-1],
            "cgm_measurement_timestamp": pd.Timestamp(decision).as_unit(timestamp_unit),
        })
    identity = PatientIdentity("synthetic", "p1")
    snapshot = SimpleNamespace(
        identity=identity,
        decision_timestamp=decision,
        simulation_start=start,
        replay_intervals=replay,
        outcome_row_at_decision=outcome_row,
    )
    candidate = BasalCandidateSimulationResult(
        candidate_id="baseline", rate_u_per_hour=0.8, is_recorded_baseline=True,
        simulation_status="simulation_valid",
        expected_output_timestamps=tuple(outputs),
        predicted_glucose_mg_dl=torch.tensor(predictions, dtype=torch.float32),
        final_state=torch.ones(10), fixed_parameters=torch.ones(7), failure=None,
        available_prediction_steps=576, roundoff_corrections=0,
        minimum_glucose_mg_dl=float(predictions.min()),
        maximum_glucose_mg_dl=float(predictions.max()),
        endpoint_glucose_mg_dl=float(predictions[-1]),
    )
    simulation = BasalSimulationBatchResult(
        identity=identity, decision_timestamp=decision, replay_start_timestamp=start,
        replay_end_timestamp=decision, configuration_version="test-v1",
        configuration_hash="hash", baseline_candidate_id="baseline", weight_kg=70.0,
        dtype="torch.float32", device="cpu", interval_minutes=5.0, substeps=5,
        candidate_batch_size=1, output_timestamps=tuple(outputs), candidates=(candidate,),
        candidate_count=1, valid_candidate_count=1, failed_candidate_count=0,
        runtime_seconds=0.0, numerical_scope_note="test",
    )
    return snapshot, simulation, observations


def criteria(limit=1000.0):
    return ReliabilityCriteria(
        "pilot-v1", "provisional_development", "synthetic tests only",
        limit, limit, limit, limit, limit, limit,
    )


class BasalReliabilityTests(unittest.TestCase):
    def test_exact_alignment_exposes_one_interval_shift_and_uses_t(self):
        snapshot, simulation, observations = fixture()
        result = assess_baseline_reliability(snapshot, simulation, criteria())
        self.assertAlmostEqual(result.full_window_metrics.mae_mg_dl, 0.0, places=5)
        self.assertEqual(result.aligned_observations[0].availability_timestamp,
                         snapshot.simulation_start + pd.Timedelta(minutes=5))
        self.assertEqual(result.aligned_observations[-1].observed_glucose_mg_dl, observations[-1])
        shifted = replace(simulation.candidates[0], predicted_glucose_mg_dl=torch.tensor(
            np.concatenate(([77.0], observations[:-1])), dtype=torch.float32))
        shifted_result = assess_baseline_reliability(
            snapshot, replace(simulation, candidates=(shifted,)), criteria())
        self.assertGreater(shifted_result.full_window_metrics.mae_mg_dl, 0.09)

    def test_missing_t_is_explicitly_insufficient(self):
        snapshot, simulation, _ = fixture(outcome=False)
        result = assess_baseline_reliability(snapshot, simulation, criteria())
        self.assertEqual(result.coverage.matched_observation_count, 575)
        self.assertEqual(result.coverage.missing_observation_count, 1)
        self.assertEqual(result.status, "insufficient_model_reliability")
        self.assertFalse(result.future_selection_authorized)

    def test_gap_duplicate_invalid_cgm_and_late_measurement_are_rejected(self):
        for mutation in ("gap", "duplicate", "invalid", "late"):
            with self.subTest(mutation=mutation):
                snapshot, simulation, _ = fixture()
                replay = snapshot.replay_intervals.copy(deep=True)
                if mutation == "gap":
                    replay = replay.drop(index=20)
                elif mutation == "duplicate":
                    replay.loc[20, "timestamp"] = replay.loc[19, "timestamp"]
                elif mutation == "invalid":
                    replay.loc[20, "cgm_mg_dl"] = np.nan
                else:
                    replay.loc[20, "cgm_measurement_timestamp"] = (
                        replay.loc[20, "timestamp"] + pd.Timedelta(minutes=1))
                snapshot.replay_intervals = replay
                result = assess_baseline_reliability(snapshot, simulation, criteria())
                self.assertFalse(result.coverage.complete)
                self.assertEqual(result.status, "insufficient_model_reliability")
                if mutation == "gap":
                    self.assertIsNotNone(result.endpoint_error_mg_dl)

    def test_inconsistent_identity_and_baseline_metadata_are_rejected(self):
        snapshot, simulation, _ = fixture()
        with self.assertRaisesRegex(ValueError, "identity"):
            assess_baseline_reliability(
                snapshot, replace(simulation, identity=PatientIdentity("other", "p1")))
        with self.assertRaisesRegex(ValueError, "exactly one"):
            assess_baseline_reliability(
                snapshot, replace(simulation, candidates=(replace(
                    simulation.candidates[0], is_recorded_baseline=False),)))

    def test_microsecond_nanosecond_compatibility_and_timezone_preservation(self):
        for unit in ("us", "ns"):
            snapshot, simulation, _ = fixture(timezone="UTC", timestamp_unit=unit)
            result = assess_baseline_reliability(snapshot, simulation, criteria())
            self.assertTrue(result.coverage.complete)
            self.assertEqual(str(result.aligned_observations[0].availability_timestamp.tz), "UTC")

    def test_metrics_day_partition_and_endpoint_are_analytic(self):
        errors = np.concatenate((np.tile([-1.0, 1.0], 144), np.full(288, 3.0)))
        snapshot, simulation, _ = fixture(errors=errors)
        result = assess_baseline_reliability(snapshot, simulation, criteria())
        self.assertAlmostEqual(result.day0_metrics.mae_mg_dl, 1.0, places=5)
        self.assertAlmostEqual(result.day0_metrics.rmse_mg_dl, 1.0, places=5)
        self.assertAlmostEqual(result.day0_metrics.mean_signed_error_mg_dl, 0.0, places=5)
        self.assertAlmostEqual(result.day1_metrics.mae_mg_dl, 3.0, places=5)
        self.assertEqual(result.day0_metrics.matched_count, 288)
        self.assertEqual(result.day1_metrics.matched_count, 288)
        self.assertAlmostEqual(result.endpoint_error_mg_dl, 3.0, places=5)

    def test_poor_day_one_fails_even_when_pooled_limit_passes(self):
        errors = np.concatenate((np.zeros(288), np.full(288, 10.0)))
        snapshot, simulation, _ = fixture(errors=errors)
        configured = ReliabilityCriteria(
            "pilot-v1", "provisional_development", "synthetic", 6, 8, 1, 1, 9, 11)
        result = assess_baseline_reliability(snapshot, simulation, configured)
        self.assertTrue(next(r for r in result.criterion_results
                             if r.criterion == "full_mae_limit_mg_dl").passed)
        self.assertFalse(next(r for r in result.criterion_results
                              if r.criterion == "day1_mae_limit_mg_dl").passed)
        self.assertEqual(result.status, "insufficient_model_reliability")

    def test_threshold_boundary_is_inclusive(self):
        snapshot, simulation, _ = fixture(errors=np.ones(576))
        measured = assess_baseline_reliability(snapshot, simulation)
        configured = ReliabilityCriteria(
            "boundary-v1", "provisional_development", "synthetic",
            measured.full_window_metrics.mae_mg_dl,
            measured.full_window_metrics.rmse_mg_dl,
            measured.day0_metrics.mae_mg_dl,
            measured.day0_metrics.rmse_mg_dl,
            measured.day1_metrics.mae_mg_dl,
            measured.day1_metrics.rmse_mg_dl,
        )
        result = assess_baseline_reliability(snapshot, simulation, configured)
        self.assertTrue(all(item.passed for item in result.criterion_results))
        self.assertEqual(result.status, "reliable_under_experimental_criteria")
        self.assertTrue(result.future_selection_authorized)

    def test_numerical_failure_is_insufficient(self):
        snapshot, simulation, _ = fixture()
        failed = replace(
            simulation.candidates[0], simulation_status="simulation_failed",
            predicted_glucose_mg_dl=torch.full((576,), float("nan")),
            available_prediction_steps=0)
        result = assess_baseline_reliability(snapshot, replace(simulation, candidates=(failed,)), criteria())
        self.assertEqual(result.status, "insufficient_model_reliability")
        self.assertIsNone(result.full_window_metrics)

    def test_missing_or_uncalibrated_criteria_never_authorizes(self):
        snapshot, simulation, _ = fixture()
        for configured in (None, ReliabilityCriteria("none-v1", "not_calibrated", "diagnostic")):
            result = assess_baseline_reliability(snapshot, simulation, configured)
            self.assertEqual(result.status, "criteria_not_calibrated")
            self.assertFalse(result.future_selection_authorized)

    def test_development_selection_is_deterministic_and_excludes_other_splits(self):
        frames = []
        for split, patient in (("testing", "a"), ("development", "b"),
                               ("validation", "c"), ("development", "d")):
            frames.append(pd.DataFrame({
                "dataset": "set", "patient_id": patient, "split": split,
                "timestamp": pd.date_range("2027-01-01", periods=865, freq="5min"),
                "continuous_record_id": "record-1",
            }))
        crossing = pd.DataFrame({
            "dataset": "set", "patient_id": "e", "split": "development",
            "timestamp": pd.date_range("2027-01-01", periods=865, freq="5min"),
            "continuous_record_id": np.where(np.arange(865) < 400, "record-1", "record-2"),
        })
        frames.append(crossing)
        data = pd.concat(frames, ignore_index=True).sample(frac=1, random_state=8)
        first = select_development_windows(data, maximum_patients=3)
        second = select_development_windows(data, maximum_patients=3)
        self.assertEqual(first.windows, second.windows)
        self.assertEqual([item.patient_id for item in first.windows], ["b", "d"])
        self.assertEqual(first.excluded_nondevelopment_patient_count, 2)
        self.assertIn("no complete 72-hour window", first.exclusion_reasons[0])

    def test_inputs_are_not_mutated(self):
        snapshot, simulation, _ = fixture()
        replay_before = snapshot.replay_intervals.copy(deep=True)
        prediction_before = simulation.candidates[0].predicted_glucose_mg_dl.clone()
        assess_baseline_reliability(snapshot, simulation, criteria())
        pd.testing.assert_frame_equal(snapshot.replay_intervals, replay_before)
        self.assertTrue(torch.equal(
            simulation.candidates[0].predicted_glucose_mg_dl, prediction_before))


if __name__ == "__main__":
    unittest.main()
