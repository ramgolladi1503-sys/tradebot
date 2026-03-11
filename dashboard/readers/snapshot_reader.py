from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.runtime_snapshot_store import read_snapshot


def read_snapshot_payload(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser()
    if not target.exists():
        return {
            "state": "missing",
            "path": str(target),
            "errors": [f"missing:{target}"],
            "payload": {},
        }
    try:
        envelope = read_snapshot(target)
    except Exception as exc:
        return {
            "state": "invalid",
            "path": str(target),
            "errors": [f"read_error:{type(exc).__name__}:{exc}"],
            "payload": {},
        }
    if not isinstance(envelope, dict):
        return {
            "state": "invalid",
            "path": str(target),
            "errors": ["snapshot_envelope_not_object"],
            "payload": {},
        }
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return {
            "state": "invalid",
            "path": str(target),
            "errors": ["snapshot_payload_not_object"],
            "payload": {},
        }
    try:
        json.dumps(payload, default=str)
    except Exception as exc:
        return {
            "state": "invalid",
            "path": str(target),
            "errors": [f"payload_not_json_serializable:{type(exc).__name__}:{exc}"],
            "payload": {},
        }
    return {
        "state": "ok",
        "path": str(target),
        "errors": [],
        "payload": payload,
        "generated_at": envelope.get("generated_at"),
        "producer": envelope.get("producer"),
        "schema_version": envelope.get("schema_version"),
    }
