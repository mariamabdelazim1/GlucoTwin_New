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

from basal_optimization.preparation import (
    BasalPreparationError,
    PatientIdentity,
    build_historical_windows,
    prepare_basal_snapshot,
)
from bolus_optimization.physiology import initialize_state


IDENTITY = PatientIdentity("synthetic", "patient-1")
DECISION = pd.Timestamp("2027-01-04 12:35:00")
PARAMETERS = torch.tensor(
    [0.00512, 0.00082, 0.052, 55.0, 40.0, 0.0161, 0.0097],
    dtype=torch.float32,
)
CHECKPOINT_METADATA = {
    "fixed_parameters": {"weight_kg": 70.0},
    "config": {"weight_kg": 70.0, "data": "model_ready_5min_cleaned.parquet"},
}


def fixture() -> pd.DataFrame:
    timestamps = pd.date_range(DECISION - pd.Timedelta(hours=72), DECISION, freq="5min")
    count = len(timestamps)
    return pd.DataFrame({
        "dataset": [IDENTITY.dataset] * count,
        "patient_id": [IDENTITY.patient_id] * count,
        "split": ["development"] * count,
        "timestamp": timestamps,
        "cgm_mg_dl": 110.0 + np.sin(np.arange(count) / 50.0),
        "basal_rate_u_per_hour": 0.8 + (np.arange(count) % 12 == 0) * 0.1,
        "bolus_u": np.where(np.arange(count) % 96 == 0, 1.0, 0.0),
        "carbs_g": np.where(np.arange(count) % 144 == 0, 30.0, 0.0),
        "consumed_carbs_g": np.where(np.arange(count) % 144 == 0, 30.0, 0.0),
        "source_minute_count": [5] * count,
        "source_run_id": ["continuous-run"] * count,
    })


def estimator(history: torch.Tensor) -> torch.Tensor:
    return PARAMETERS.unsqueeze(0).expand(len(history), -1).clone()


def prepare(frame: pd.DataFrame):
    return prepare_basal_snapshot(
        frame,
        IDENTITY,
        DECISION,
        estimator,
        dataset_path="services/prediction/model_ready_5min.parquet",
        checkpoint_sha256="checkpoint-test-identity",
        checkpoint_metadata=CHECKPOINT_METADATA,
    )


class BasalWindowTests(unittest.TestCase):
    def test_exact_lengths_boundaries_and_decision_row_exclusion(self):
        windows = build_historical_windows(fixture(), IDENTITY, DECISION)
        self.assertEqual(len(windows.initialization_intervals), 288)
        self.assertEqual(len(windows.replay_intervals), 576)
        self.assertEqual(windows.simulation_start, DECISION - pd.Timedelta(hours=48))
        self.assertEqual(windows.initialization_intervals.timestamp.iloc[-1], windows.simulation_start - pd.Timedelta(minutes=5))
        self.assertEqual(windows.boundary_row.timestamp, windows.simulation_start)
        self.assertEqual(windows.replay_intervals.timestamp.iloc[0], windows.simulation_start)
        self.assertEqual(windows.replay_intervals.timestamp.iloc[-1], DECISION - pd.Timedelta(minutes=5))
        self.assertNotIn(DECISION, set(windows.replay_intervals.timestamp))
        self.assertEqual(windows.outcome_row_at_decision.timestamp, DECISION)

    def test_non_midnight_aligned_decision_is_supported(self):
        windows = build_historical_windows(fixture(), IDENTITY, DECISION)
        self.assertEqual(windows.decision_timestamp.hour, 12)
        self.assertEqual(windows.decision_timestamp.minute, 35)

    def test_missing_duplicate_partial_and_discontinuous_intervals_are_rejected(self):
        cases = []
        missing = fixture().drop(index=10)
        cases.append((missing, "coverage"))
        duplicate = pd.concat((fixture(), fixture().iloc[[10]]), ignore_index=True)
        cases.append((duplicate, "duplicate timestamps"))
        partial = fixture()
        partial.loc[10, "source_minute_count"] = 4
        cases.append((partial, "partial or discontinuous"))
        discontinuous = fixture()
        discontinuous.loc[500:, "source_run_id"] = "another-run"
        cases.append((discontinuous, "source_run_id"))
        for frame, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(BasalPreparationError, message):
                    build_historical_windows(frame, IDENTITY, DECISION)

    def test_invalid_values_and_missing_are_rejected_but_zero_is_valid(self):
        valid = fixture()
        valid.loc[:, "bolus_u"] = 0.0
        valid.loc[:, "consumed_carbs_g"] = 0.0
        windows = build_historical_windows(valid, IDENTITY, DECISION)
        self.assertEqual(float(windows.replay_intervals.bolus_u.sum()), 0.0)
        self.assertEqual(float(windows.replay_intervals.consumed_carbs_g.sum()), 0.0)
        for column, value, message in (
            ("bolus_u", np.nan, "bolus_u is missing"),
            ("consumed_carbs_g", -1.0, "consumed_carbs_g must be nonnegative"),
            ("cgm_mg_dl", 0.0, "cgm_mg_dl must be strictly positive"),
        ):
            invalid = fixture()
            invalid.loc[100, column] = value
            with self.subTest(column=column):
                with self.assertRaisesRegex(BasalPreparationError, message):
                    build_historical_windows(invalid, IDENTITY, DECISION)

    def test_unaligned_and_timezone_reinterpreted_decisions_are_rejected(self):
        with self.assertRaisesRegex(BasalPreparationError, "five-minute grid"):
            build_historical_windows(fixture(), IDENTITY, DECISION + pd.Timedelta(minutes=1))
        with self.assertRaisesRegex(BasalPreparationError, "timezone convention"):
            build_historical_windows(fixture(), IDENTITY, DECISION.tz_localize("UTC"))

    def test_missing_or_ambiguous_identity_and_mixed_split_are_rejected(self):
        with self.assertRaisesRegex(BasalPreparationError, "patient identity not found"):
            build_historical_windows(fixture(), PatientIdentity("synthetic", "absent"), DECISION)
        mixed = fixture()
        mixed.loc[100, "split"] = "testing"
        with self.assertRaisesRegex(BasalPreparationError, "split"):
            build_historical_windows(mixed, IDENTITY, DECISION)


class BasalInitializationTests(unittest.TestCase):
    def test_gru_boundary_contract_and_s_event_exclusion(self):
        frame = fixture()
        simulation_start = DECISION - pd.Timedelta(hours=48)
        at_s = frame.index[frame.timestamp.eq(simulation_start)][0]
        frame.loc[at_s, ["bolus_u", "consumed_carbs_g", "carbs_g"]] = [9.0, 80.0, 45.0]
        snapshot = prepare(frame)
        self.assertEqual(tuple(snapshot.gru_input.shape), (289, 4))
        self.assertEqual(float(snapshot.gru_input[-1, 2]), 0.0)
        self.assertEqual(float(snapshot.gru_input[-1, 3]), 45.0)
        self.assertEqual(float(snapshot.replay_intervals.iloc[0].bolus_u), 9.0)
        self.assertEqual(float(snapshot.replay_intervals.iloc[0].consumed_carbs_g), 80.0)
        self.assertNotEqual(float(snapshot.physiological_initialization_inputs[-1, 1]), 9.0)

    def test_replay_after_s_cannot_change_estimate_or_initial_state(self):
        original = prepare(fixture())
        changed = fixture()
        s = DECISION - pd.Timedelta(hours=48)
        later = changed.timestamp.gt(s) & changed.timestamp.lt(DECISION)
        changed.loc[later, "cgm_mg_dl"] += 50.0
        changed.loc[later, "basal_rate_u_per_hour"] += 2.0
        changed.loc[later, "bolus_u"] += 3.0
        changed.loc[later, "consumed_carbs_g"] += 4.0
        altered = prepare(changed)
        self.assertTrue(torch.equal(original.gru_input, altered.gru_input))
        self.assertTrue(torch.equal(original.parameters, altered.parameters))
        self.assertTrue(torch.equal(original.physiological_state, altered.physiological_state))

    def test_state_matches_existing_initializer(self):
        snapshot = prepare(fixture())
        direct = initialize_state(
            snapshot.physiological_initialization_glucose,
            snapshot.physiological_initialization_inputs,
            snapshot.parameters,
            weight_kg=70.0,
            substeps=5,
        )
        self.assertTrue(torch.equal(snapshot.physiological_state, direct.state))

    def test_clones_have_independent_storage(self):
        snapshot = prepare(fixture())
        first = snapshot.clone_initial_conditions()
        second = snapshot.clone_initial_conditions()
        self.assertNotEqual(first.physiological_state.data_ptr(), second.physiological_state.data_ptr())
        self.assertNotEqual(first.parameters.data_ptr(), second.parameters.data_ptr())
        first.physiological_state[0] += 1
        first.parameters[0] += 1
        self.assertFalse(torch.equal(first.physiological_state, second.physiological_state))
        self.assertFalse(torch.equal(first.parameters, second.parameters))
        self.assertTrue(torch.equal(snapshot.parameters, PARAMETERS))

    def test_weight_contract_mismatch_is_explicit(self):
        bad = {
            "fixed_parameters": {"weight_kg": 80.0},
            "config": {"weight_kg": 70.0},
        }
        with self.assertRaisesRegex(BasalPreparationError, "weight contract mismatch"):
            prepare_basal_snapshot(
                fixture(), IDENTITY, DECISION, estimator,
                dataset_path="services/prediction/model_ready_5min.parquet",
                checkpoint_sha256="checkpoint-test-identity",
                checkpoint_metadata=bad,
            )


if __name__ == "__main__":
    unittest.main()
