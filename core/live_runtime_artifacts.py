"""Truthful startup artifacts for current-session observation health."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_pending_runtime_artifacts(
    output_root: str | Path, *, session_id: str, source_sha: str,
    include_instrument_authority: bool = True,
) -> None:
    """Declare startup identity without claiming feed, persistence, or readiness."""
    if not session_id or not source_sha:
        raise ValueError("runtime_artifact_identity_missing")
    identity = {"session_id": session_id, "source_sha": source_sha}
    authority = {
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_execution_authorized": False,
        "orders_placed": 0,
        "orders_modified": 0,
        "orders_cancelled": 0,
    }
    root = Path(output_root)
    _write(root / "feed_health.json", {**identity, "verdict": "PENDING", "websocket_connected": False, **authority})
    _write(root / "heartbeat.json", {**identity, "verdict": "PENDING", "state": "STARTING", **authority})
    # The canonical composition root leaves this absent until current-session
    # acquisition, while legacy callers may request the explicit PENDING marker.
    if include_instrument_authority:
        _write(root / "instrument_authority_manifest.json", {**identity, "verdict": "PENDING", "instrument_master_sha": None, **authority})
    _write(root / "session_exit_gate.json", {**identity, "verdict": "PENDING", "live_observation_e2e_ready": False, **authority})
