from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from core.events import write_json_atomic
from core.paths import runtime_dir


SNAPSHOT_WRAPPER_SCHEMA_VERSION = 1

MARKET_SNAPSHOT_PATH = runtime_dir() / "market_snapshot.json"
ADVISORY_LATEST_PATH = runtime_dir() / "advisory_latest.json"
FEED_RUNTIME_LATEST_PATH = runtime_dir() / "feed_runtime_latest.json"
TOKEN_RESOLUTION_LATEST_PATH = runtime_dir() / "token_resolution_latest.json"
RISK_SNAPSHOT_PATH = runtime_dir() / "risk_snapshot.json"


def snapshot_generated_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_snapshot_envelope(
    *,
    payload: Any,
    producer: str,
    generated_at: str | None = None,
    schema_version: int = SNAPSHOT_WRAPPER_SCHEMA_VERSION,
) -> dict[str, Any]:
    return {
        "schema_version": int(schema_version),
        "generated_at": str(generated_at or snapshot_generated_at()),
        "producer": str(producer or "unknown"),
        "payload": payload,
    }


def write_snapshot_atomic(
    path: str | Path,
    *,
    payload: Any,
    producer: str,
    generated_at: str | None = None,
    schema_version: int = SNAPSHOT_WRAPPER_SCHEMA_VERSION,
) -> Path:
    target = Path(path).expanduser()
    envelope = build_snapshot_envelope(
        payload=payload,
        producer=producer,
        generated_at=generated_at,
        schema_version=schema_version,
    )
    return write_json_atomic(target, envelope)


def read_snapshot(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser()
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("snapshot_envelope_not_object")
    return raw
