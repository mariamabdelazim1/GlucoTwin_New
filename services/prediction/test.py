"""Evaluate baseline and residual forecasts with an explicit gated override."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import joblib
import numpy as np
import pandas as pd
import torch
from threadpoolctl import threadpool_limits

import optimize as o


def _selected_output(saved, baseline, gated, *, force_gated: bool):
    validation_enabled = bool(saved["enabled"])
    use_gated = validation_enabled or bool(force_gated)
    mode = (
        "gated_candidate_experimental_override"
        if force_gated and not validation_enabled
        else "gated_candidate_validation_selected"
        if validation_enabled
        else "baseline_validation_selected"
    )
    return (gated if use_gated else baseline).copy(), mode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data")
    parser.add_argument("--checkpoint", default="baseline/model.pt")
    parser.add_argument("--ungated", default="baseline/ungated.joblib")
    parser.add_argument("--results", default="results")
    parser.add_argument("--out")
    parser.add_argument("--compile", action="store_true")
    parser.add_argument(
        "--force-gated", action="store_true",
        help="Experimental override: use the gated candidate despite enabled=False.",
    )
    args = parser.parse_args()
    torch.set_num_threads(4)
    if args.compile:
        o.advance = torch.compile(o.advance, dynamic=True)

    residual_path = Path(args.results) / "gated.joblib"
    selection_path = Path(args.results) / "selection.json"
    saved = joblib.load(residual_path)
    old = joblib.load(args.ungated)
    for payload in (saved, old):
        if payload["checkpoint_sha256"] != o.sha256(args.checkpoint) \
                or payload["data_sha256"] != o.sha256(args.data):
            raise ValueError("Source mismatch")

    frame = o.generate(args.data, args.checkpoint, "testing")
    if set(frame.patient_id) & set(saved["calibration_patients"]):
        raise RuntimeError("Calibration patients entered testing evaluation")
    frame["gated_correction"], frame["gate"] = o.predict_candidate(saved, frame)
    frame["gated_candidate"] = frame.baseline + frame.gated_correction
    frame["selected_output"], output_mode = _selected_output(
        saved, frame.baseline, frame.gated_candidate, force_gated=args.force_gated
    )

    regressor = old["diagnostic_model"] if old.get("diagnostic_model") is not None else old["model"]
    alpha = old["diagnostic"]["alpha"] if old.get("diagnostic_model") is not None else old["alpha"]
    with threadpool_limits(limits=4):
        raw = regressor.predict(frame[old["features"]].to_numpy()) if regressor is not None else np.zeros(len(frame))
    frame["ungated_candidate"] = frame.baseline + alpha * np.clip(raw, -old["clip"], old["clip"])
    if not np.isfinite(frame.gated_candidate).all():
        raise RuntimeError("Nonfinite gated prediction")
    if not np.array_equal(
        frame.loc[frame.gate == 0, "gated_candidate"],
        frame.loc[frame.gate == 0, "baseline"],
    ):
        raise RuntimeError("Zero gate did not preserve the baseline")

    output = Path(args.out) if args.out else Path(
        "results/testing_force_gated_v1" if args.force_gated
        else "results/testing_validation_selected_v2"
    )
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite evaluation output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "patients": int(frame.patient_id.nunique()),
        "windows": len(frame),
        "horizon_minutes": 60,
        "residual_enabled_by_validation": bool(saved["enabled"]),
        "residual_override_requested": bool(args.force_gated),
        "actual_output_mode": output_mode,
        "gate_active_fraction": float((frame.gate > 0).mean()),
        "gate_mean": float(frame.gate.mean()),
        "hashes": {
            "checkpoint_sha256": o.sha256(args.checkpoint),
            "dataset_sha256": o.sha256(args.data),
            "residual_sha256": o.sha256(residual_path),
            "selection_sha256": o.sha256(selection_path),
            "test_source_sha256": o.sha256(Path(__file__)),
            "optimize_source_sha256": o.sha256(Path(o.__file__)),
            "residual_configuration_sha256": hashlib.sha256(
                json.dumps(saved["config"], sort_keys=True).encode()
            ).hexdigest(),
        },
        "methods": {},
    }
    patient_rows = []
    for name in ("baseline", "ungated_candidate", "gated_candidate", "selected_output"):
        report["methods"][name] = o.measure(frame[name], frame.target)
        for patient_id, group in frame.groupby("patient_id"):
            patient_rows.append({
                "patient_id": patient_id, "method": name,
                **o.measure(group[name], group.target),
            })
    frame.to_parquet(output / "predictions.parquet", index=False)
    pd.DataFrame(patient_rows).to_csv(output / "patient_metrics.csv", index=False)
    (output / "metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "provenance.json").write_text(json.dumps({
        key: report[key] for key in (
            "created_utc", "residual_enabled_by_validation",
            "residual_override_requested", "actual_output_mode", "hashes",
        )
    }, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
