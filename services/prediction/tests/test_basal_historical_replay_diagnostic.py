from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import torch

PREDICTION_ROOT = Path(__file__).resolve().parents[1]
if str(PREDICTION_ROOT) not in sys.path:
    sys.path.insert(0, str(PREDICTION_ROOT))

from basal_optimization.historical_replay_diagnostic import (
    EVALUATION_STEPS, HORIZON_HOURS, TARGET_PATIENTS, aggregate_results,
    assemble_segment_inputs, build_segment_plan, complete_protocol,
    estimate_parameters, evaluate_patient, markdown_report, paired_difference,
    simulate_segment, timestamp_index_equal,
)
from basal_optimization.preparation import PatientIdentity, prepare_basal_snapshot
from bolus_optimization.physiology import initialize_state


PARAMETERS = torch.tensor(
    [0.00512, 0.00082, 0.052, 55.0, 40.0, 0.0161, 0.0097],
    dtype=torch.float32,
)
IDENTITY = PatientIdentity("synthetic", "patient-1")
START = pd.Timestamp("2027-01-02 00:00:00")
DECISION = pd.Timestamp("2027-01-04 00:00:00")


def patient_frame(split="development"):
    timestamps = pd.date_range("2027-01-01", periods=865, freq="5min").as_unit("us")
    count = len(timestamps)
    frame = pd.DataFrame({
        "dataset": IDENTITY.dataset, "patient_id": IDENTITY.patient_id,
        "split": split, "timestamp": timestamps,
        "cgm_mg_dl": 110.0 + np.sin(np.arange(count) / 30),
        "basal_rate_u_per_hour": np.full(count, 0.8),
        "bolus_u": np.zeros(count), "carbs_g": np.zeros(count),
        "consumed_carbs_g": np.zeros(count),
        "source_run_id": "run-1", "continuous_record_id": "record-1",
    })
    frame.loc[300::100, "bolus_u"] = 0.5
    frame.loc[300::100, "carbs_g"] = 10.0
    frame.loc[300::100, "consumed_carbs_g"] = 10.0
    return frame


def snapshot(frame=None, estimator=lambda _: PARAMETERS[None]):
    return prepare_basal_snapshot(
        patient_frame() if frame is None else frame, IDENTITY, DECISION, estimator,
        dataset_path="synthetic.parquet", checkpoint_sha256="synthetic",
        checkpoint_metadata={"fixed_parameters": {"weight_kg": 70.0},
                             "config": {"weight_kg": 70.0}},
    )


def completed_segments(horizon):
    plan = build_segment_plan(START, horizon)
    segments = []
    for origin in plan.origins:
        outputs = tuple(pd.date_range(origin + pd.Timedelta(minutes=5),
                                      periods=plan.steps_per_segment, freq="5min"))
        observed = [110.0] * plan.steps_per_segment
        segments.append({
            "status": "complete", "runtime_seconds": 0.1,
            "output_timestamps": outputs, "predictions": observed.copy(),
            "observed": observed, "metrics": {}, "failure": None,
        })
    return segments


class HistoricalReplayDiagnosticTests(unittest.TestCase):
    def test_origin_counts_and_segment_lengths(self):
        expected = {2: (24, 24), 4: (12, 48), 6: (8, 72)}
        for horizon, (count, steps) in expected.items():
            plan = build_segment_plan(START, horizon)
            self.assertEqual((len(plan.origins), plan.steps_per_segment), (count, steps))

    def test_all_horizons_have_exactly_576_unique_aligned_outputs(self):
        expected = pd.date_range(START + pd.Timedelta(minutes=5), periods=576, freq="5min")
        for horizon in HORIZON_HOURS:
            protocol = complete_protocol(completed_segments(horizon), expected)
            self.assertEqual(protocol["status"], "complete")
            self.assertEqual(protocol["coverage"]["matched"], EVALUATION_STEPS)
            self.assertTrue(protocol["coverage"]["timestamps_exact_unique"])
            self.assertEqual(protocol["output_timestamps"][-1], DECISION)

    def test_missing_or_duplicated_boundary_outputs_remain_incomplete(self):
        expected = pd.date_range(START + pd.Timedelta(minutes=5), periods=576, freq="5min")
        missing = completed_segments(2)
        missing[-1]["output_timestamps"] = missing[-1]["output_timestamps"][:-1]
        missing[-1]["predictions"] = missing[-1]["predictions"][:-1]
        missing[-1]["observed"] = missing[-1]["observed"][:-1]
        self.assertEqual(complete_protocol(missing, expected)["status"], "incomplete")
        duplicate = completed_segments(2)
        values = list(duplicate[1]["output_timestamps"])
        values[0] = duplicate[0]["output_timestamps"][-1]
        duplicate[1]["output_timestamps"] = tuple(values)
        self.assertEqual(complete_protocol(duplicate, expected)["status"], "incomplete")

    def test_first_segment_parity_for_identical_initial_conditions(self):
        segment = assemble_segment_inputs(patient_frame(), IDENTITY, START, 2)
        initialized = initialize_state(segment.initialization_glucose,
                                       segment.initialization_inputs, PARAMETERS,
                                       weight_kg=70.0, substeps=5)
        left, _ = simulate_segment(segment, PARAMETERS, initialized.state)
        right, _ = simulate_segment(segment, PARAMETERS, initialized.state)
        self.assertEqual(left["status"], "complete")
        self.assertEqual(left["predictions"], right["predictions"])

    def test_b_parameters_fixed_and_c_history_never_exceeds_origin(self):
        frame = patient_frame()
        calls = []
        def estimator(history):
            calls.append(history.detach().clone())
            return PARAMETERS[None]
        result = evaluate_patient(frame, snapshot(frame, estimator), estimator)
        for horizon in HORIZON_HOURS:
            steps = horizon * 12
            first_b = result["protocols"][f"B_{horizon}h"]["segments"][0]
            first_c = result["protocols"][f"C_{horizon}h"]["segments"][0]
            self.assertEqual(first_b["predictions"],
                             result["protocols"]["A"]["predictions"][:steps])
            self.assertEqual(first_c["predictions"], first_b["predictions"])
            for item in result["protocols"][f"B_{horizon}h"]["segments"]:
                self.assertEqual(item["parameters"], PARAMETERS.tolist())
            for item in result["protocols"][f"C_{horizon}h"]["segments"]:
                if item["parameter_change_from_A"] is not None:
                    self.assertEqual(item["parameter_change_from_A"]["future_rows_used"], 0)
                    self.assertEqual(item["parameter_change_from_A"]["history_latest_timestamp"],
                                     item["origin"])
        self.assertGreater(len(calls), 1)

    def test_initialization_uses_observations_but_forecast_does_not(self):
        frame = patient_frame()
        segment = assemble_segment_inputs(frame, IDENTITY, START, 2)
        self.assertAlmostEqual(float(segment.initialization_glucose[-1]),
                               float(frame.loc[frame.timestamp.eq(START), "cgm_mg_dl"].iloc[0]),
                               places=4)
        changed = frame.copy(deep=True)
        changed.loc[changed.timestamp.gt(START), "cgm_mg_dl"] += 50
        changed_segment = assemble_segment_inputs(changed, IDENTITY, START, 2)
        self.assertTrue(torch.equal(segment.initialization_glucose,
                                    changed_segment.initialization_glucose))
        left, _ = simulate_segment(segment, PARAMETERS)
        right, _ = simulate_segment(changed_segment, PARAMETERS)
        self.assertEqual(left["predictions"], right["predictions"])
        self.assertNotEqual(segment.targets.tolist(), changed_segment.targets.tolist())

    def test_paired_comparison_requires_identical_timestamps(self):
        expected = pd.date_range(START + pd.Timedelta(minutes=5), periods=576, freq="5min")
        left = complete_protocol(completed_segments(2), expected)
        right = copy.deepcopy(left)
        self.assertEqual(paired_difference(left, right)["mae_mg_dl"], 0.0)
        right["output_timestamps"][0] += pd.Timedelta(minutes=1)
        with self.assertRaisesRegex(ValueError, "timestamps differ"):
            paired_difference(left, right)

    def test_numerical_failure_and_incomplete_coverage_remain_visible(self):
        segment = assemble_segment_inputs(patient_frame(), IDENTITY, START, 2)
        failed, _ = simulate_segment(segment, torch.zeros(7))
        self.assertNotEqual(failed["status"], "complete")
        self.assertIsNotNone(failed["failure"])
        expected = pd.date_range(START + pd.Timedelta(minutes=5), periods=576, freq="5min")
        segments = completed_segments(2)
        segments[3].update(status="forecast_failed", predictions=None,
                           failure={"reason": "synthetic"})
        protocol = complete_protocol(segments, expected)
        self.assertEqual(protocol["status"], "incomplete")
        self.assertEqual(protocol["segments"][3]["failure"]["reason"], "synthetic")

    def test_selection_is_fixed_development_only_and_source_is_immutable(self):
        self.assertEqual([item.patient_id for item in TARGET_PATIENTS],
                         ["adolescent#001", "adolescent#002", "adolescent#004",
                          "adolescent#005", "adult#004"])
        frame = patient_frame()
        before = frame.copy(deep=True)
        assemble_segment_inputs(frame, IDENTITY, START, 2)
        pd.testing.assert_frame_equal(frame, before)

    def test_empty_and_failed_reports_are_safe(self):
        empty = {"configuration": {"patients": []}, "patients": [],
                 "failures": [], "aggregate": aggregate_results([])}
        self.assertIn("metrics are unavailable", markdown_report(empty))
        failed = {"configuration": {"patients": [{"patient_id": "p"}]},
                  "patients": [], "failures": ["p: failed"],
                  "aggregate": aggregate_results([])}
        report = markdown_report(failed)
        self.assertIn("p: failed", report)
        self.assertIn("Completed patient evaluations: 0", report)

    def test_timestamp_precision_and_timezone_semantics(self):
        us = pd.date_range("2027-01-01", periods=3, freq="5min", tz="UTC").as_unit("us")
        ns = us.as_unit("ns")
        self.assertTrue(timestamp_index_equal(us, ns))
        self.assertFalse(timestamp_index_equal(us, ns.tz_convert("Africa/Cairo")))


if __name__ == "__main__":
    unittest.main()
