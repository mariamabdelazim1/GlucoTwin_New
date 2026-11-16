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

from basal_optimization.carbohydrate_pair_diagnostic import (
    FORECAST_STEPS,
    PairedOrigin,
    assemble_paired_window,
    evaluate_paired_window,
    select_paired_origins,
)


PARAMETERS = torch.tensor(
    [0.00512, 0.00082, 0.052, 55.0, 40.0, 0.0161, 0.0097],
    dtype=torch.float32,
)


def patient_frame(patient_id="p1", split="development", *, identical_carbs=False):
    count = 340
    timestamp = pd.date_range("2027-01-01", periods=count, freq="5min").as_unit("us")
    frame = pd.DataFrame({
        "dataset": "synthetic",
        "patient_id": patient_id,
        "split": split,
        "timestamp": timestamp,
        "cgm_mg_dl": np.full(count, 110.0),
        "cgm_measurement_timestamp": timestamp,
        "basal_rate_u_per_hour": np.full(count, 0.8),
        "bolus_u": np.zeros(count),
        "carbs_g": np.zeros(count),
        "consumed_carbs_g": np.zeros(count),
        "source_run_id": "run-1",
    })
    frame.loc[250, "carbs_g"] = 15.0
    frame.loc[250:252, "consumed_carbs_g"] = 5.0
    frame.loc[300, "carbs_g"] = 30.0
    frame.loc[300:302, "consumed_carbs_g"] = 10.0
    frame.loc[300, "bolus_u"] = 2.0
    if identical_carbs:
        frame["consumed_carbs_g"] = frame["carbs_g"]
    return frame


def origin(frame):
    initialization = frame.iloc[228:300]
    forecast = frame.iloc[300:324]
    return PairedOrigin(
        "synthetic", str(frame.patient_id.iloc[0]), pd.Timestamp(frame.timestamp.iloc[300]),
        float(initialization.carbs_g.sum()), float(initialization.consumed_carbs_g.sum()),
        float(forecast.carbs_g.sum()), float(forecast.consumed_carbs_g.sum()),
        int((forecast.carbs_g > 0).sum()), int((forecast.consumed_carbs_g > 0).sum()),
        not np.array_equal(initialization.carbs_g, initialization.consumed_carbs_g),
        not np.array_equal(forecast.carbs_g, forecast.consumed_carbs_g),
    )


class PairedCarbohydrateDiagnosticTests(unittest.TestCase):
    def test_identical_carbohydrate_inputs_produce_identical_results(self):
        frame = patient_frame(identical_carbs=True)
        window = assemble_paired_window(frame, origin(frame), lambda _: PARAMETERS[None])
        result = evaluate_paired_window(window)
        self.assertEqual(result["arm_a"]["status"], "complete")
        self.assertEqual(result["arm_c"]["status"], "complete")
        self.assertEqual(result["predictions"]["arm_a"], result["predictions"]["arm_c"])
        self.assertTrue(all(abs(value) <= 1e-12 for value in
                            result["paired_difference_A_minus_C"].values()))

    def test_shared_gru_input_parameters_basal_and_bolus(self):
        frame = patient_frame()
        calls = []

        def estimator(value):
            calls.append(value.detach().clone())
            return PARAMETERS[None]

        window = assemble_paired_window(frame, origin(frame), estimator)
        self.assertEqual(len(calls), 1)
        self.assertTrue(torch.equal(calls[0][0], window.gru_input))
        self.assertTrue(torch.equal(window.parameters, PARAMETERS))
        self.assertTrue(torch.equal(
            window.announced_initialization_inputs[:, :2],
            window.consumed_initialization_inputs[:, :2],
        ))
        self.assertTrue(torch.equal(
            window.announced_forecast_inputs[:, :2],
            window.consumed_forecast_inputs[:, :2],
        ))
        self.assertFalse(torch.equal(
            window.announced_forecast_inputs[:, 2],
            window.consumed_forecast_inputs[:, 2],
        ))

    def test_origin_events_are_applied_once_and_no_carbs_are_combined(self):
        frame = patient_frame()
        window = assemble_paired_window(frame, origin(frame), lambda _: PARAMETERS[None])
        self.assertEqual(float(window.announced_forecast_inputs[0, 2]), 30.0)
        self.assertEqual(float(window.consumed_forecast_inputs[0, 2]), 10.0)
        self.assertEqual(float(window.announced_initialization_inputs[:, 2].sum()), 15.0)
        self.assertEqual(float(window.consumed_initialization_inputs[:, 2].sum()), 15.0)
        self.assertEqual(float(window.consumed_forecast_inputs[:, 2].sum()), 30.0)
        self.assertNotEqual(
            float(window.consumed_forecast_inputs[:, 2].sum()),
            float(window.announced_forecast_inputs[:, 2].sum()
                  + window.consumed_forecast_inputs[:, 2].sum()),
        )

    def test_exact_24_output_alignment_and_native_parity(self):
        frame = patient_frame()
        window = assemble_paired_window(frame, origin(frame), lambda _: PARAMETERS[None])
        result = evaluate_paired_window(window)
        self.assertEqual(len(window.output_timestamps), FORECAST_STEPS)
        self.assertEqual(window.output_timestamps[0], window.origin_timestamp + pd.Timedelta(minutes=5))
        self.assertEqual(window.output_timestamps[-1], window.origin_timestamp + pd.Timedelta(hours=2))
        self.assertLessEqual(
            result["native_announced_simulator_parity"]["maximum_absolute_difference_mg_dl"],
            1e-4,
        )

    def test_selection_is_deterministic_outcome_independent_and_development_only(self):
        development = patient_frame("p1", "development")
        testing = patient_frame("p2", "testing")
        data = pd.concat((development, testing), ignore_index=True).sample(frac=1, random_state=3)
        first = select_paired_origins(
            data, patient_ids=("p1", "p2"), max_windows_per_patient=2
        )
        changed = data.copy(deep=True)
        changed.loc[changed.patient_id.eq("p1"), "cgm_mg_dl"] += np.linspace(0, 100, 340)
        second = select_paired_origins(
            changed, patient_ids=("p1", "p2"), max_windows_per_patient=2
        )
        self.assertEqual(first.origins, second.origins)
        self.assertTrue(all(item.patient_id == "p1" for item in first.origins))
        self.assertTrue(any("not development" in reason for reason in first.exclusions))

    def test_numerical_failures_remain_visible(self):
        frame = patient_frame()
        bad_parameters = torch.zeros(7, dtype=torch.float32)
        window = assemble_paired_window(frame, origin(frame), lambda _: bad_parameters[None])
        result = evaluate_paired_window(window)
        self.assertEqual(result["arm_a"]["status"], "initialization_failed")
        self.assertEqual(result["arm_c"]["status"], "initialization_failed")
        self.assertIsNone(result["paired_difference_A_minus_C"])
        self.assertIsNotNone(result["arm_a"]["failure"])

    def test_source_data_and_estimator_parameters_are_not_mutated(self):
        frame = patient_frame()
        before = frame.copy(deep=True)
        parameters_before = PARAMETERS.clone()
        window = assemble_paired_window(frame, origin(frame), lambda _: PARAMETERS[None])
        evaluate_paired_window(window)
        pd.testing.assert_frame_equal(frame, before)
        self.assertTrue(torch.equal(PARAMETERS, parameters_before))


if __name__ == "__main__":
    unittest.main()
