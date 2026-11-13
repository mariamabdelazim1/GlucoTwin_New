"""Shared loading primitives for the canonical research bolus policy.

The canonical default is a complete policy document. Component loaders also
accept their historical standalone JSON documents when callers pass an
explicit path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_RESEARCH_CONFIGURATION = Path(__file__).with_name(
    "migrated_selected_configuration.json"
)


def load_component_payload(
    path: str | Path, component: str,
) -> tuple[Path, bytes, dict[str, Any], str]:
    """Load a canonical-policy component or an explicit standalone payload."""

    resolved = Path(path)
    raw = resolved.read_bytes()
    document = json.loads(raw)
    payload = document.get(component, document)
    if not isinstance(payload, dict):
        raise ValueError(f"Configuration component {component!r} must be an object")
    return resolved, raw, payload, hashlib.sha256(raw).hexdigest()
