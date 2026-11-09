"""Explicit, integrity-checked adapter for the final GRU--Hovorka model.

The migrated bolus optimizer imports this module, never the ambiguous top-level
``optimize`` name.  The destination experiment remains authoritative: its
architecture, checkpoint metadata, feature scaling, parameter bounds, scalar
weight, and solver settings are validated before inference.

The saved residual is an optional 60-minute diagnostic only.  It is disabled
by the saved validation selection and is never exposed as a candidate-scoring
or physiological-state interface.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

import numpy as np
import torch


PROJECT_ROOT = Path(__file__).resolve().parent
NATIVE_MODEL_SOURCE = PROJECT_ROOT / "optimize.py"
DEFAULT_FINAL_CHECKPOINT = PROJECT_ROOT / "baseline/model.pt"
DEFAULT_RESIDUAL_PAYLOAD = PROJECT_ROOT / "results/gated.joblib"
DEFAULT_RESIDUAL_SELECTION = PROJECT_ROOT / "results/selection.json"

NATIVE_MODEL_SOURCE_SHA256 = "7b2dfb7850b846ae8c480cccf58b968ea4e54a8953d5b7a66aaaea808dbe9c28"
FINAL_CHECKPOINT_SHA256 = "0b27f4da9cf6f5f9f9e038708c4878ae6e04a6d9347085d6d860dbbefec1a8ac"
FINAL_DATASET_SHA256 = "95b201c80404e692bffb3e7b7084ae2b868f849df70bbf9712f7402e747b3d1d"
RESIDUAL_PAYLOAD_SHA256 = "1bdbfed1ba5629eb7b2791ab1267d06ab4d9d0271badf5a382f2867f733ab6f0"
RESIDUAL_SELECTION_SHA256 = "2a4d6e7f0d1e78cc6e8661729c1c7b0ea922e372e1d987abf4bf6df9f6b3fda7"


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_hash(path: str | Path, expected: str, label: str) -> Path:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Missing {label}: {resolved}")
    actual = sha256(resolved)
    if actual != expected:
        raise ValueError(
            f"{label} SHA-256 mismatch: expected {expected}, found {actual}: {resolved}"
        )
    return resolved


def _load_native() -> ModuleType:
    source = _require_hash(
        NATIVE_MODEL_SOURCE, NATIVE_MODEL_SOURCE_SHA256, "final model source"
    )
    name = "_glucotwin_final_gated_native_model"
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load final model source: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


native = _load_native()

# Explicit compatibility exports used by the migrated package.  These values
# come from the destination's protected final-model source, not the old project.
HISTORY = native.HISTORY
HORIZON = native.HORIZON
FEATURES = tuple(native.FEATURES)
PARAM_NAMES = tuple(native.PARAM_NAMES)
NOMINAL = tuple(native.NOMINAL)
LOWER = tuple(native.LOWER)
UPPER = tuple(native.UPPER)
FIXED = dict(native.FIXED)
ParameterGRU = native.ParameterGRU
advance = native.advance
simulate = native.simulate
read_data = native.read_data


@dataclass(frozen=True)
class FinalModel:
    model: torch.nn.Module
    checkpoint: Mapping[str, Any]
    checkpoint_sha256: str


def validate_checkpoint_metadata(checkpoint: Mapping[str, Any]) -> None:
    required = {
        "state_dict", "features", "parameter_names", "lower_bounds",
        "upper_bounds", "fixed_parameters", "patient_splits", "data_sha256",
        "history_steps", "horizon_steps", "config",
    }
    missing = required.difference(checkpoint)
    if missing:
        raise ValueError(f"Final checkpoint is missing fields: {sorted(missing)}")
    checks = {
        "features": tuple(checkpoint["features"]) == FEATURES,
        "parameter_names": tuple(checkpoint["parameter_names"]) == PARAM_NAMES,
        "lower_bounds": tuple(checkpoint["lower_bounds"]) == LOWER,
        "upper_bounds": tuple(checkpoint["upper_bounds"]) == UPPER,
        "history_steps": checkpoint["history_steps"] == HISTORY,
        "horizon_steps": checkpoint["horizon_steps"] == HORIZON,
        "dataset_hash": checkpoint["data_sha256"] == FINAL_DATASET_SHA256,
        "fixed_weight": checkpoint["fixed_parameters"].get("weight_kg") == 70.0,
        "configured_weight": checkpoint["config"].get("weight_kg") == 70.0,
        "substeps": checkpoint["config"].get("substeps") == 5,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError("Final checkpoint contract mismatch: " + ", ".join(failed))
    state = checkpoint["state_dict"]
    if tuple(state["mean"].shape) != (4,) or tuple(state["scale"].shape) != (4,):
        raise ValueError("Final checkpoint feature scaling must contain four values")


def load_final_model(
    checkpoint_path: str | Path = DEFAULT_FINAL_CHECKPOINT,
    *,
    expected_sha256: str = FINAL_CHECKPOINT_SHA256,
) -> FinalModel:
    path = _require_hash(checkpoint_path, expected_sha256, "final checkpoint")
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    validate_checkpoint_metadata(checkpoint)
    state = checkpoint["state_dict"]
    recent_raw = bool(checkpoint["config"].get("recent_raw", False))
    model = ParameterGRU(state["mean"], state["scale"], recent_raw=recent_raw)
    model.load_state_dict(state, strict=True)
    model.eval()
    model.requires_grad_(False)
    return FinalModel(model, checkpoint, sha256(path))


@torch.inference_mode()
def predict_parameters(final: FinalModel, history: torch.Tensor) -> torch.Tensor:
    expected = (HISTORY + 1, len(FEATURES))
    if history.ndim != 3 or tuple(history.shape[1:]) != expected:
        raise ValueError(
            f"History must have shape (batch, {expected[0]}, {expected[1]}); "
            f"got {tuple(history.shape)}"
        )
    if history.dtype != torch.float32:
        raise TypeError("History must use torch.float32")
    if not torch.isfinite(history).all():
        raise ValueError("History contains nonfinite values")
    return final.model(history)


def verify_dataset(path: str | Path, checkpoint: Mapping[str, Any] | None = None) -> str:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"Missing final-model dataset: {resolved}; required SHA-256 "
            f"{FINAL_DATASET_SHA256}"
        )
    actual = sha256(resolved)
    expected = FINAL_DATASET_SHA256
    if checkpoint is not None:
        expected = str(checkpoint["data_sha256"])
        if expected != FINAL_DATASET_SHA256:
            raise ValueError("Checkpoint dataset provenance differs from the final contract")
    if actual != expected:
        raise ValueError(
            f"Final-model dataset SHA-256 mismatch: expected {expected}, found {actual}: "
            f"{resolved}"
        )
    return actual


@dataclass(frozen=True)
class ResidualDiagnostic:
    payload: Mapping[str, Any]
    selection: Mapping[str, Any]
    enabled: bool
    payload_sha256: str
    selection_sha256: str


def load_residual_diagnostic(
    payload_path: str | Path = DEFAULT_RESIDUAL_PAYLOAD,
    selection_path: str | Path = DEFAULT_RESIDUAL_SELECTION,
) -> ResidualDiagnostic:
    import joblib

    payload_file = _require_hash(payload_path, RESIDUAL_PAYLOAD_SHA256, "residual payload")
    selection_file = _require_hash(
        selection_path, RESIDUAL_SELECTION_SHA256, "residual selection"
    )
    payload = joblib.load(payload_file)
    selection = json.loads(selection_file.read_text())
    enabled = bool(selection.get("enabled"))
    if bool(payload.get("enabled")) != enabled:
        raise ValueError("Residual payload and selection disagree on enabled status")
    if payload.get("checkpoint_sha256") != FINAL_CHECKPOINT_SHA256:
        raise ValueError("Residual payload references a different checkpoint")
    if payload.get("data_sha256") != FINAL_DATASET_SHA256:
        raise ValueError("Residual payload references a different dataset")
    return ResidualDiagnostic(
        payload, selection, enabled, sha256(payload_file), sha256(selection_file)
    )


def selected_residual_output(
    diagnostic: ResidualDiagnostic,
    baseline_60_min_mg_dl: np.ndarray,
    diagnostic_correction_mg_dl: np.ndarray | None = None,
) -> np.ndarray:
    """Return the saved selected endpoint; never a trajectory or solver state.

    With the preserved ``enabled=False`` selection this is exactly the baseline.
    Candidate scoring and state propagation have no dependency on this function.
    """

    baseline = np.asarray(baseline_60_min_mg_dl)
    if not diagnostic.enabled:
        return baseline.copy()
    if diagnostic_correction_mg_dl is None:
        raise ValueError("Enabled residual output requires an explicit diagnostic correction")
    correction = np.asarray(diagnostic_correction_mg_dl)
    if correction.shape != baseline.shape:
        raise ValueError("Residual correction shape differs from baseline endpoint")
    return baseline + correction

