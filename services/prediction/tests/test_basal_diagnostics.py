from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import torch


PREDICTION_ROOT = Path(__file__).resolve().parents[1]
if str(PREDICTION_ROOT) not in sys.path:
    sys.path.insert(0, str(PREDICTION_ROOT))

from basal_optimization.candidate_generation import BasalCandidateSet, BasalRateCandidate
from basal_optimization.development_reliability import select_development_windows
from basal_optimization.diagnostics import (
    PREFIX_STEPS,
    _dataframe_fingerprint,
    _markdown_report,
    _model_state_unchanged,
    analyze_error_development,
    baseline_only_candidate_set,
)
from basal_optimization.preparation import PatientIdentity
from basal_optimization.reliability import (
    AlignedGlucoseObservation,
    BaselineReliabilityAssessment,
    CoverageDiagnostics,
)


def assessment(*, missing_index=None, numerical_failure=False):
    start = pd.Timestamp("2027-01-02 00:05:00")
    timestamps = pd.date_range(start, periods=576, freq="5min")
    error = np.concatenate((np.ones(288), np.full(288, 3.0)))
    aligned = []
    for index, timestamp in enumerate(timestamps):
        valid = index != missing_index
        predicted = 100.0 + error[index]
        if numerical_failure and index >= 10:
            predicted = float("nan")
        aligned.append(AlignedGlucoseObservation(
            timestamp, timestamp, predicted, 100.0 if valid else None, valid,
            None if valid else "missing observation",
        ))
    matched = 576 - int(missing_index is not None)
    return BaselineReliabilityAssessment(
        identity=PatientIdentity("synthetic", "p1"),
        decision_timestamp=timestamps[-1],
        replay_start_timestamp=timestamps[0] - pd.Timedelta(minutes=5),
        replay_end_timestamp=timestamps[-1],
        baseline_candidate_id="baseline",
        baseline_rate_u_per_hour=0.8,
        baseline_simulation_status=(
            "simulation_failed" if numerical_failure else "simulation_valid"
        ),
        coverage=CoverageDiagnostics(
            576, matched, 576 - matched, 0, 0, matched == 576
        ),
        aligned_observations=tuple(aligned),
        full_window_metrics=None,
        day0_metrics=None,
        day1_metrics=None,
        endpoint_error_mg_dl=None,
        criteria=None,
        criteria_configuration_hash=None,
        criterion_results=(),
        status="criteria_not_calibrated",
        future_selection_authorized=False,
        reasons=(),
        interpretation="synthetic",
    )


def report_payload(*, windows=(), failures=(), exclusions=()):
    empty_distribution = {
        "count": 0, "minimum": None, "median": None, "mean": None, "maximum": None,
    }
    return {
        "selection": {
            "selected_reference_count": len(windows) + len(failures),
            "exclusion_reasons": tuple(exclusions),
        },
        "windows": list(windows),
        "failures": list(failures),
        "source_immutability": {
            "dataframe_unchanged": True,
            "frozen_model_state_unchanged": True,
        },
        "aggregate": {
            "window_count": len(windows),
            "complete_coverage_count": sum(
                item["error_development"]["cumulative"][-1]["status"] == "complete"
                for item in windows
            ),
            "numerical_failure_count": sum(
                item["assessment"]["baseline_simulation_status"] != "simulation_valid"
                for item in windows
            ),
            "equally_weighted_patient_prefix_metrics": {
                str(steps): {
                    field: dict(empty_distribution)
                    for field in (
                        "mae_mg_dl", "rmse_mg_dl", "mean_signed_error_mg_dl",
                        "maximum_absolute_error_mg_dl",
                    )
                }
                for steps in PREFIX_STEPS
            },
        },
    }


def report_window(*, basal_difference=0.01, announced=10.0, consumed=8.0,
                  event_adjacent=5.0, event_outside=4.0, status="complete"):
    metric = {
        "label": "0-48h", "status": status,
        "mae_mg_dl": 2.0 if status == "complete" else None,
        "rmse_mg_dl": 3.0 if status == "complete" else None,
        "mean_signed_error_mg_dl": 1.0 if status == "complete" else None,
        "maximum_absolute_error_mg_dl": 5.0 if status == "complete" else None,
        "endpoint_error_mg_dl": 1.5 if status == "complete" else None,
    }
    return {
        "identity": {"dataset": "synthetic", "patient_id": "p1"},
        "decision_timestamp": pd.Timestamp("2027-01-04"),
        "assessment": {
            "baseline_simulation_status": (
                "simulation_valid" if status != "numerical_failure" else "simulation_failed"
            ),
            "coverage": {"matched_observation_count": 576, "expected_observation_count": 576},
        },
        "error_development": {"cumulative": [metric], "four_hour_blocks": []},
        "audit": {
            "basal": {
                "maximum_absolute_rate_difference_after_float32_u_per_hour": basal_difference,
                "source_column_comparison": {
                    "maximum_absolute_difference_from_rate_times_interval": basal_difference / 2,
                },
            },
            "bolus": {"event_intervals_exactly_preserved": True},
            "carbohydrates": {
                "announced_total_g": announced, "consumed_total_g": consumed,
                "announcement_event_count": 1, "consumption_event_count": 2,
                "consumption_intervals_exactly_preserved": True,
            },
            "timestamps_and_cgm": {
                "measurement_age": {
                    "count": 576, "minimum": 0.0, "median": 1.0, "maximum": 2.0,
                },
                "event_error_comparison": {
                    "within_30_minutes_after_event": {
                        "count": 10,
                        "mean_absolute_error_mg_dl": event_adjacent,
                    },
                    "outside_30_minutes_after_event": {
                        "count": 566,
                        "mean_absolute_error_mg_dl": event_outside,
                    },
                },
            },
            "weight": {
                "patient_specific_weight_columns": [],
                "trusted_patient_specific_weight_available": False,
            },
        },
    }


class BasalDiagnosticTests(unittest.TestCase):
    def test_report_handles_empty_and_all_failed_pilots(self):
        empty = _markdown_report(report_payload(exclusions=("no eligible windows",)))
        self.assertIn("No window completed", empty)
        self.assertIn("no eligible windows", empty)
        failed = _markdown_report(report_payload(failures=("p1: preparation failed",)))
        self.assertIn("No window completed", failed)
        self.assertIn("preparation failed", failed)
        self.assertNotIn("Completed windows: 1", failed)

    def test_report_handles_partial_success_and_numerical_failure(self):
        successful = report_window()
        numerical = report_window(status="numerical_failure")
        numerical["identity"]["patient_id"] = "p2"
        text = _markdown_report(report_payload(
            windows=(successful, numerical), failures=("p3: execution failed",)
        ))
        self.assertIn("Window records produced: 2", text)
        self.assertIn("Numerical failures among window records: 1", text)
        self.assertIn("execution failed", text)
        self.assertIn("unavailable", text)

    def test_report_handles_missing_event_metrics(self):
        window = report_window()
        comparison = window["audit"]["timestamps_and_cgm"]["event_error_comparison"]
        comparison["within_30_minutes_after_event"]["mean_absolute_error_mg_dl"] = None
        text = _markdown_report(report_payload(windows=(window,)))
        self.assertIn("Event-error comparisons available for 0 of 1", text)

    def test_report_findings_are_derived_from_payload(self):
        first = _markdown_report(report_payload(windows=(report_window(
            basal_difference=0.01, announced=10.0, consumed=8.0,
        ),)))
        second = _markdown_report(report_payload(windows=(report_window(
            basal_difference=0.25, announced=30.0, consumed=12.0,
        ),)))
        self.assertIn("0.01 U/hour", first)
        self.assertIn("0.25 U/hour", second)
        self.assertIn("10.000 g", first)
        self.assertIn("30.000 g", second)
        self.assertNotEqual(first, second)

    def test_prefix_lengths_and_four_hour_partitions(self):
        result = analyze_error_development(assessment())
        self.assertEqual(
            [item.expected_count for item in result.cumulative], list(PREFIX_STEPS)
        )
        self.assertEqual(len(result.four_hour_blocks), 12)
        self.assertTrue(all(item.expected_count == 48 for item in result.four_hour_blocks))
        self.assertEqual(
            [(item.start_output_index, item.end_output_index_exclusive)
             for item in result.four_hour_blocks],
            [(start, start + 48) for start in range(0, 576, 48)],
        )

    def test_analytic_metrics_and_day_change(self):
        result = analyze_error_development(assessment())
        self.assertAlmostEqual(result.cumulative[0].mae_mg_dl, 1.0)
        self.assertAlmostEqual(result.cumulative[4].rmse_mg_dl, 1.0)
        self.assertAlmostEqual(result.cumulative[-1].mae_mg_dl, 2.0)
        self.assertAlmostEqual(result.cumulative[-1].rmse_mg_dl, np.sqrt(5.0))
        self.assertAlmostEqual(result.cumulative[-1].mean_signed_error_mg_dl, 2.0)
        self.assertAlmostEqual(result.cumulative[-1].maximum_absolute_error_mg_dl, 3.0)
        self.assertAlmostEqual(result.cumulative[-1].endpoint_error_mg_dl, 3.0)
        self.assertAlmostEqual(result.four_hour_blocks[5].mae_mg_dl, 1.0)
        self.assertAlmostEqual(result.four_hour_blocks[6].mae_mg_dl, 3.0)

    def test_missing_observation_is_reported_without_partial_metric(self):
        result = analyze_error_development(assessment(missing_index=30))
        self.assertEqual(result.cumulative[0].status, "complete")
        self.assertEqual(
            result.cumulative[1].status, "incomplete_observation_coverage"
        )
        self.assertEqual(result.cumulative[1].matched_count, 47)
        self.assertIsNone(result.cumulative[1].mae_mg_dl)

    def test_numerical_failure_is_explicit(self):
        result = analyze_error_development(assessment(numerical_failure=True))
        self.assertTrue(all(item.status == "numerical_failure" for item in result.cumulative))
        self.assertEqual(result.numerical_status, "simulation_failed")

    def test_analysis_does_not_mutate_source_assessment(self):
        source = assessment()
        before = tuple(
            (item.predicted_glucose_mg_dl, item.observed_glucose_mg_dl, item.valid)
            for item in source.aligned_observations
        )
        analyze_error_development(source)
        after = tuple(
            (item.predicted_glucose_mg_dl, item.observed_glucose_mg_dl, item.valid)
            for item in source.aligned_observations
        )
        self.assertEqual(before, after)

    def test_source_dataframe_and_model_mutation_checks(self):
        frame = pd.DataFrame({"value": [1.0, 2.0]})
        frame_before = frame.copy(deep=True)
        fingerprint = _dataframe_fingerprint(frame)
        model = torch.nn.Linear(2, 1)
        state = {name: value.detach().clone() for name, value in model.state_dict().items()}
        with torch.inference_mode():
            model(torch.ones((1, 2)))
        self.assertEqual(_dataframe_fingerprint(frame), fingerprint)
        pd.testing.assert_frame_equal(frame, frame_before)
        self.assertTrue(_model_state_unchanged(model, state))
        with torch.no_grad():
            model.weight.add_(1.0)
        self.assertFalse(_model_state_unchanged(model, state))

    def test_baseline_only_candidate_execution_metadata(self):
        candidates = (
            BasalRateCandidate("low", 0.75, False),
            BasalRateCandidate("baseline", 0.8, True),
            BasalRateCandidate("high", 0.85, False),
        )
        candidate_set = BasalCandidateSet(
            PatientIdentity("synthetic", "p1"), pd.Timestamp("2027-01-04"),
            pd.Timestamp("2027-01-02"), pd.Timestamp("2027-01-04"), 576,
            0.8, "test", 1e-9, 0.75, 0.85, candidates, "baseline",
            "test-v1", "hash", 3,
        )
        reduced = baseline_only_candidate_set(candidate_set)
        self.assertEqual(reduced.candidate_count, 1)
        self.assertEqual(reduced.candidates, (candidates[1],))
        self.assertEqual(candidate_set.candidate_count, 3)

    def test_development_selection_remains_deterministic_and_split_safe(self):
        rows = []
        for patient, split in (("a", "development"), ("b", "testing")):
            rows.append(pd.DataFrame({
                "dataset": "set", "patient_id": patient, "split": split,
                "timestamp": pd.date_range("2027-01-01", periods=865, freq="5min"),
                "source_run_id": "record",
            }))
        data = pd.concat(rows, ignore_index=True).sample(frac=1, random_state=11)
        first = select_development_windows(data, maximum_patients=1)
        second = select_development_windows(data, maximum_patients=1)
        self.assertEqual(first.windows, second.windows)
        self.assertEqual(first.windows[0].patient_id, "a")
        self.assertEqual(first.excluded_nondevelopment_patient_count, 1)


if __name__ == "__main__":
    unittest.main()
