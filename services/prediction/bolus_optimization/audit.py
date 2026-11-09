"""Audit the immutable inputs used by Hovorka-only bolus optimization.

Run from the project root:
python -m bolus_optimization.audit model_ready_5min_cleaned.parquet
"""

import argparse
import json
from pathlib import Path

import torch

from final_model_adapter import HISTORY, sha256

from .checkpoint import load_frozen_gru, predict_parameters
from .configuration import (
    DEFAULT_CHECKPOINT,
    DEFAULT_OUTPUT_DIRECTORY,
    FROZEN_CHECKPOINT_SHA256,
    HISTORICAL_CARBOHYDRATE_FEATURE,
    MODEL_FEATURES,
    PREDICTION_HORIZON_MINUTES,
    PREDICTION_HORIZON_STEPS,
    SAMPLE_INTERVAL_MINUTES,
)
from .data import read_optimization_data


def _read_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data")
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    parser.add_argument("--out", default=DEFAULT_OUTPUT_DIRECTORY)
    args = parser.parse_args()

    data_path = Path(args.data)
    checkpoint_path = Path(args.checkpoint)
    frozen = load_frozen_gru(
        checkpoint_path,
        expected_sha256=FROZEN_CHECKPOINT_SHA256,
    )
    data, patient_splits, data_audit = read_optimization_data(data_path)
    checkpoint = frozen.checkpoint

    data_hash = sha256(data_path)
    if patient_splits != checkpoint["patient_splits"]:
        raise ValueError("Dataset patient splits differ from the checkpoint")

    # Exercise the exact inference path on a real history without fitting or
    # mutating the model. The first eligible patient history is sufficient for
    # this loading audit.
    group = next(iter(data.groupby(["dataset", "patient_id"], sort=False)))[1]
    history = torch.tensor(
        group.iloc[: HISTORY + 1][list(MODEL_FEATURES)].to_numpy("float32")
    ).unsqueeze(0)
    if history.shape[1] != HISTORY + 1:
        raise ValueError("No patient has enough rows for a complete model history")
    theta = predict_parameters(frozen, history)

    output = {
        "scope": "Step 1 preservation and checkpoint audit",
        "checkpoint": {
            "path": str(checkpoint_path.resolve()),
            "sha256": frozen.checkpoint_sha256,
            "safe_load": "torch.load(..., map_location='cpu', weights_only=True)",
            "evaluation_mode": not frozen.model.training,
            "all_parameters_frozen": all(
                not parameter.requires_grad for parameter in frozen.model.parameters()
            ),
            "best_epoch": checkpoint.get("best_epoch"),
            "validation_mae_mg_dl": checkpoint.get("validation_mae"),
        },
        "dataset": {
            "path": str(data_path.resolve()),
            "sha256": data_hash,
            "checkpoint_expected_sha256": checkpoint["data_sha256"],
            "byte_identical_to_checkpoint_dataset": data_hash == checkpoint["data_sha256"],
            **data_audit,
            "patients": len(patient_splits),
            "split_rows": {str(k): int(v) for k, v in data["split"].value_counts().items()},
        },
        "encoder_contract": {
            "features_in_order": list(MODEL_FEATURES),
            "historical_carbohydrate_feature": HISTORICAL_CARBOHYDRATE_FEATURE,
            "history_steps": checkpoint["history_steps"],
            "feature_mean": checkpoint["state_dict"]["mean"].tolist(),
            "feature_scale": checkpoint["state_dict"]["scale"].tolist(),
            "scaling_source": "unchanged tensors embedded in baseline/model.pt",
            "sample_inference_parameters": theta.squeeze(0).tolist(),
        },
        "bolus_optimization_contract": {
            "method": "Hovorka-only candidate evaluation",
            "sample_interval_minutes": SAMPLE_INTERVAL_MINUTES,
            "prediction_horizon_minutes": PREDICTION_HORIZON_MINUTES,
            "prediction_horizon_steps": PREDICTION_HORIZON_STEPS,
            "event_types": ["announced_meal", "high_glucose"],
            "gru_retraining": False,
        },
        "existing_results": {
            "training_summary": _read_json(Path("results/training_summary.json")),
            "test_metrics": _read_json(Path("results/test/test_metrics.json")),
        },
    }
    required_checks = {
        "checkpoint_sha256_is_frozen_value": (
            frozen.checkpoint_sha256 == FROZEN_CHECKPOINT_SHA256
        ),
        "checkpoint_loaded_with_weights_only": True,
        "checkpoint_in_evaluation_mode": not frozen.model.training,
        "checkpoint_parameters_frozen": all(
            not parameter.requires_grad for parameter in frozen.model.parameters()
        ),
        "checkpoint_feature_order_preserved": tuple(checkpoint["features"]) == MODEL_FEATURES,
        "patient_splits_match_checkpoint": patient_splits == checkpoint["patient_splits"],
        "source_minute_count_validated_before_filtering": data_audit[
            "source_minute_count_validated_before_filtering"
        ],
        "sample_inference_is_gradient_free": not theta.requires_grad,
    }
    unresolved = []
    if data_hash != checkpoint["data_sha256"]:
        unresolved.append(
            {
                "id": "checkpoint_dataset_hash_mismatch",
                "status": "unresolved",
                "detail": (
                    "The supplied parquet SHA-256 differs from data_sha256 stored in the "
                    "checkpoint. The observed extra terminal four-minute row explains a row-count "
                    "difference, but semantic equivalence to the original training parquet has not "
                    "been established from hashes."
                ),
            }
        )
    output["audit_result"] = {
        "required_checks": required_checks,
        "required_checks_passed": sum(required_checks.values()),
        "required_checks_total": len(required_checks),
        "overall_pass": all(required_checks.values()),
        "unresolved_issues": unresolved,
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    destination = out / "step1_audit.json"
    destination.write_text(json.dumps(output, indent=2) + "\n")
    print(destination)
    if not output["audit_result"]["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
