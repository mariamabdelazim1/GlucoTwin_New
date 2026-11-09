"""Generate the Step 3 stateful-simulator verification report."""

from __future__ import annotations

import argparse
import io
import json
import unittest
from pathlib import Path

import torch

from final_model_adapter import NOMINAL, advance as original_advance, sha256

from .configuration import DEFAULT_OUTPUT_DIRECTORY, FROZEN_CHECKPOINT_SHA256
from .data import read_optimization_data
from .physiology import (
    MG_DL_PER_MMOL_L,
    PHYSIOLOGICAL_INPUT_NAMES,
    STATE_NAMES,
    VG_L_PER_KG,
    initialize_state,
    physiological_inputs_from_frame,
    predict_from_state,
)


EXPECTED_SOURCE_HASHES = {
    "final_model_adapter.py": "22522d4f3cb12169b0a57192844c7126293be13aaedc33085ce8e7566732b154",
    "optimize.py": "7b2dfb7850b846ae8c480cccf58b968ea4e54a8953d5b7a66aaaea808dbe9c28",
    "test.py": "6cc4770aa148247f20fa1ebd06cea7eb8c87cc1da9a9554a80cd4dea89f0bd3c",
}
PARITY_TOLERANCE = 3e-5


def _flatten_tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten_tests(item)
        else:
            yield item


def _run_tests() -> dict:
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_stateful_hovorka")
    names = [test.id() for test in _flatten_tests(suite)]
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return {
        "passed": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "test_names": names,
        "failures": [test.id() for test, _ in result.failures],
        "errors": [test.id() for test, _ in result.errors],
        "runner_output": stream.getvalue(),
    }


def _original_initialization(glucose, inputs, theta, weight_kg=70.0, substeps=5):
    si1, si2, si3, tmax_i, _, _, _ = theta
    basal_m_u_min = inputs[0, 0] * 1000 / 60
    insulin = basal_m_u_min / (0.138 * 0.12 * weight_kg)
    x1, x2, x3 = si1 * insulin, si2 * insulin, si3 * insulin
    q1 = glucose[0] / MG_DL_PER_MMOL_L * (VG_L_PER_KG * weight_kg)
    zero = torch.zeros_like(q1)
    state = torch.stack(
        (
            q1,
            x1 * q1 / (0.066 + x2),
            basal_m_u_min * tmax_i,
            basal_m_u_min * tmax_i,
            insulin,
            x1,
            x2,
            x3,
            zero,
            zero,
        )
    )
    for interval in range(72):
        state = original_advance(
            state.unsqueeze(0), theta.unsqueeze(0), inputs[interval].unsqueeze(0),
            weight_kg, substeps,
        )[0]
        state = state.clone()
        state[0] = glucose[interval + 1] / MG_DL_PER_MMOL_L * (
            VG_L_PER_KG * weight_kg
        )
    return state


def _numerical_parity(data) -> dict:
    group = next(
        part for _, part in data.groupby(["dataset", "patient_id"], sort=False)
        if len(part) >= 120
    ).reset_index(drop=True)
    theta = torch.tensor(NOMINAL, dtype=torch.float32)
    glucose = torch.tensor(group.loc[:72, "cgm_mg_dl"].to_numpy("float32"))
    historical_inputs = physiological_inputs_from_frame(group.iloc[:72])
    future_inputs = physiological_inputs_from_frame(group.iloc[72:120])

    initialized = initialize_state(glucose, historical_inputs, theta)
    original_state = _original_initialization(glucose, historical_inputs, theta)
    initialization_difference = float(torch.max(torch.abs(initialized.state - original_state)))

    prediction = predict_from_state(initialized.state, theta, future_inputs)
    original_predictions = []
    original_final = original_state.clone()
    for interval in range(48):
        original_final = original_advance(
            original_final.unsqueeze(0), theta.unsqueeze(0),
            future_inputs[interval].unsqueeze(0), 70.0, 5,
        )[0]
        original_predictions.append(
            original_final[0] / (VG_L_PER_KG * 70.0) * MG_DL_PER_MMOL_L
        )
    original_glucose = torch.stack(original_predictions)
    return {
        "patient": {
            "dataset": str(group.loc[0, "dataset"]),
            "patient_id": str(group.loc[0, "patient_id"]),
        },
        "carbohydrate_parity_rule": (
            "consumed_carbs_g was explicitly supplied to both new and original equations"
        ),
        "initialization_max_abs_state_difference": initialization_difference,
        "forecast_max_abs_glucose_difference_mg_dl": float(
            torch.max(torch.abs(prediction.glucose_mg_dl - original_glucose))
        ),
        "forecast_max_abs_final_state_difference": float(
            torch.max(torch.abs(prediction.final_state - original_final))
        ),
        "tolerance": PARITY_TOLERANCE,
        "passed": bool(
            initialized.validity.all_valid
            and prediction.validity.all_valid
            and initialization_difference <= PARITY_TOLERANCE
            and torch.max(torch.abs(prediction.glucose_mg_dl - original_glucose)).item()
            <= PARITY_TOLERANCE
            and torch.max(torch.abs(prediction.final_state - original_final)).item()
            <= PARITY_TOLERANCE
        ),
    }


def _markdown(report: dict) -> str:
    tests = report["tests"]
    parity = report["numerical_parity"]
    preservation = report["preservation"]
    return f"""# Step 3 — Stateful Hovorka simulator verification

Overall result: **{'PASS' if report['overall_pass'] else 'FAIL'}**

## Verification

- Stateful simulator tests: **{'PASS' if tests['passed'] else 'FAIL'}** ({tests['tests_run']} run)
- Original-equation parity: **{'PASS' if parity['passed'] else 'FAIL'}**
- Initialization maximum absolute state difference: `{parity['initialization_max_abs_state_difference']}`
- Four-hour glucose maximum absolute difference: `{parity['forecast_max_abs_glucose_difference_mg_dl']}` mg/dL
- Final-state maximum absolute difference: `{parity['forecast_max_abs_final_state_difference']}`
- Numerical tolerance: `{parity['tolerance']}`
- Frozen checkpoint preserved: **{preservation['checkpoint_sha256_matches']}**
- `optimize.py` preserved: **{preservation['source_files']['optimize.py']['matches']}**
- `test.py` preserved: **{preservation['source_files']['test.py']['matches']}**

## Contracts

State order: `{', '.join(report['contracts']['state_order'])}`.

Parameter order: `{', '.join(report['contracts']['parameter_order'])}`.

Physiological input order: `{', '.join(report['contracts']['physiological_input_order'])}`. The simulator uses `consumed_carbs_g`; announced `carbs_g` remains a separate GRU/decision input and is not added to gut compartments.

Forecasts accept one `(T, 3)` sequence or batched `(B, T, 3)` candidates. The four-hour contract is 48 five-minute intervals labeled +5 through +240 minutes. Parameters remain fixed within a forecast, and no future CGM is accepted or used.

## Failure behavior

Shape/device/dtype and integration-setting errors are batch-wide exceptions. State, parameter, input and integration failures are recorded per candidate with its zero-based index and first failing interval/substep; `-1` denotes failure before interval zero. Failed output points and final states remain NaN; valid candidates continue. Tiny negatives in `[-1e-7, 0)` are explicitly zeroed and counted as roundoff corrections.

## Assumptions

Initialization retains the original empty-gut and first-basal equilibrium assumptions. It replays 72 prior five-minute intervals from 73 CGM boundaries, corrects Q1 only at each historical boundary, and returns the decision-time state before new inputs. Five-minute aggregated bolus and consumption are applied once at interval start; their original within-bin minute is unavailable, so that timing remains an explicit assumption.

Passing Step 3 establishes implementation parity and state management, not four-hour predictive accuracy or dosing safety.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data")
    parser.add_argument("--checkpoint", default="baseline/model.pt")
    parser.add_argument("--out", default=DEFAULT_OUTPUT_DIRECTORY)
    args = parser.parse_args()

    data, _, data_audit = read_optimization_data(args.data)
    tests = _run_tests()
    parity = _numerical_parity(data)
    source_files = {}
    for name, expected in EXPECTED_SOURCE_HASHES.items():
        actual = sha256(name)
        source_files[name] = {"expected_sha256": expected, "actual_sha256": actual, "matches": actual == expected}
    checkpoint_hash = sha256(args.checkpoint)
    preservation = {
        "checkpoint_expected_sha256": FROZEN_CHECKPOINT_SHA256,
        "checkpoint_actual_sha256": checkpoint_hash,
        "checkpoint_sha256_matches": checkpoint_hash == FROZEN_CHECKPOINT_SHA256,
        "source_files": source_files,
        "training_or_gru_modification_performed": False,
    }
    report = {
        "scope": "Step 3 stateful Hovorka simulator verification",
        "tests": tests,
        "numerical_parity": parity,
        "contracts": {
            "state_order": list(STATE_NAMES),
            "state_units": ["mmol", "mmol", "mU", "mU", "mU/L", "1/min", "1/min", "dimensionless", "mmol", "mmol"],
            "parameter_order": ["si1", "si2", "si3", "tmax_i", "tmax_g", "egp0", "f01"],
            "physiological_input_order": list(PHYSIOLOGICAL_INPUT_NAMES),
            "gru_historical_carbohydrate_feature": "carbs_g",
            "physiological_carbohydrate_feature": "consumed_carbs_g",
            "history_boundary_observations": 73,
            "historical_intervals_replayed": 72,
            "forecast_intervals": 48,
            "forecast_horizon_minutes": list(range(5, 241, 5)),
            "default_substeps": 5,
            "default_substep_minutes": 1.0,
        },
        "failure_handling": {
            "interface_errors": "raise batch-wide TypeError or ValueError",
            "candidate_failures": "isolated and recorded by candidate/interval/substep/reason",
            "failure_indexing": "zero-based; -1 means before forecast interval zero",
            "failed_outputs": "NaN from first failure onward; final state NaN",
            "negative_roundoff_tolerance": 1e-7,
        },
        "assumptions": [
            "empty gut at the start of six-hour initialization",
            "insulin equilibrium with the first historical basal rate",
            "Q1-only correction at historical CGM boundaries",
            "aggregated bolus and consumed carbohydrate applied at interval start",
            "common 70 kg fallback unless explicitly replaced",
        ],
        "data_loader_audit": data_audit,
        "preservation": preservation,
    }
    report["overall_pass"] = bool(
        tests["passed"]
        and parity["passed"]
        and preservation["checkpoint_sha256_matches"]
        and all(item["matches"] for item in source_files.values())
    )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "step3_simulator_verification.json"
    markdown_path = out / "step3_simulator_verification.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    markdown_path.write_text(_markdown(report))
    print(json_path)
    if not report["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
