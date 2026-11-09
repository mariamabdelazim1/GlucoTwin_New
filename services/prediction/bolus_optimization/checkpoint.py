"""Safe, frozen access to the trained GRU parameter encoder."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import torch

from final_model_adapter import (
    HISTORY,
    FINAL_DATASET_SHA256,
    PARAM_NAMES,
    LOWER,
    UPPER,
    ParameterGRU,
    sha256,
    validate_checkpoint_metadata,
)

from .configuration import MODEL_FEATURES


@dataclass(frozen=True)
class FrozenGRU:
    """A validated checkpoint and its inference-only model."""

    model: ParameterGRU
    checkpoint: Mapping[str, Any]
    checkpoint_sha256: str


def load_frozen_gru(
    checkpoint_path: str | Path,
    *,
    expected_sha256: str | None = None,
) -> FrozenGRU:
    """Load the parameter encoder without permitting arbitrary pickle code.

    The returned module is in evaluation mode and every parameter has
    ``requires_grad=False``.  Call :func:`predict_parameters` for inference so
    autograd is also disabled around the forward pass.
    """

    path = Path(checkpoint_path)
    checkpoint_hash = sha256(path)
    if expected_sha256 is not None and checkpoint_hash != expected_sha256:
        raise ValueError(
            f"Checkpoint SHA-256 mismatch: expected {expected_sha256}, "
            f"found {checkpoint_hash}"
        )

    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    required = {"state_dict", "features", "history_steps", "config"}
    missing = required.difference(checkpoint)
    if missing:
        raise ValueError(f"Checkpoint is missing required fields: {sorted(missing)}")
    if tuple(checkpoint["features"]) != MODEL_FEATURES:
        raise ValueError(
            "Checkpoint feature order differs from the frozen optimization "
            f"interface: {checkpoint['features']!r}"
        )
    if checkpoint["history_steps"] != HISTORY:
        raise ValueError(
            f"Checkpoint history is {checkpoint['history_steps']} steps; "
            f"expected {HISTORY}"
        )

    validate_checkpoint_metadata(checkpoint)
    if checkpoint["data_sha256"] != FINAL_DATASET_SHA256:
        raise ValueError("Checkpoint dataset hash differs from the final model provenance")
    if tuple(checkpoint["parameter_names"]) != PARAM_NAMES:
        raise ValueError("Checkpoint parameter order differs from the final model")
    if tuple(checkpoint["lower_bounds"]) != LOWER or tuple(checkpoint["upper_bounds"]) != UPPER:
        raise ValueError("Checkpoint parameter bounds differ from the final model")
    state = checkpoint["state_dict"]
    if "mean" not in state or "scale" not in state:
        raise ValueError("Checkpoint does not contain its training feature scaling")
    model = ParameterGRU(
        state["mean"], state["scale"],
        recent_raw=bool(checkpoint["config"].get("recent_raw", False)),
    )
    model.load_state_dict(state, strict=True)
    model.eval()
    model.requires_grad_(False)
    return FrozenGRU(model, checkpoint, checkpoint_hash)


@torch.inference_mode()
def predict_parameters(frozen: FrozenGRU, history: torch.Tensor) -> torch.Tensor:
    """Estimate Hovorka parameters from one or more 24-hour histories."""

    expected_shape = (HISTORY + 1, len(MODEL_FEATURES))
    if history.ndim != 3 or tuple(history.shape[1:]) != expected_shape:
        raise ValueError(
            "History must have shape (batch, "
            f"{expected_shape[0]}, {expected_shape[1]}); got {tuple(history.shape)}"
        )
    if not torch.isfinite(history).all():
        raise ValueError("History contains nonfinite values")
    return frozen.model(history)
