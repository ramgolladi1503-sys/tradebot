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


def write_session_exit_gate(
    output_root: str | Path, *, session_id: str, source_sha: str,
    auth_valid: bool, feed_current: bool, persistence_advancing: bool,
    instrument_authority_current: bool, shutdown_drain_complete: bool,
    broker_order_calls: int = 0, strategies_ran: list[str] | None = None,
    candidates_emitted: int = 0, candidates_rejected: int = 0,
    option_surface_ran: bool = False, eligibility_ran: bool = False,
    ranking_ran: bool = False, advisory_queue_healthy: bool = False,
    cas_freeze: bool = False, cas_advisory_before_1515: bool = False,
    sidecars_completed: list[str] | None = None,
) -> dict[str, Any]:
    """Write an evidence-shaped close gate without promoting unknown facts."""
    order_calls = int(broker_order_calls)
    core_ready = all((auth_valid, feed_current, persistence_advancing, instrument_authority_current))
    e2e_ready = bool(core_ready and shutdown_drain_complete and order_calls == 0 and
                     option_surface_ran and eligibility_ran and ranking_ran and
                     advisory_queue_healthy and cas_freeze and cas_advisory_before_1515)
    payload = {
        "schema_version": 1, "session_id": session_id, "source_sha": source_sha,
        "verdict": "PASS" if e2e_ready else "BLOCKED_RUNTIME_GATES_PENDING",
        "live_observation_e2e_ready": e2e_ready,
        "auth_valid": bool(auth_valid), "feed_current": bool(feed_current),
        "persistence_advancing": bool(persistence_advancing),
        "instrument_authority_current": bool(instrument_authority_current),
        "regime_healthy": False, "strategies_ran": list(strategies_ran or []),
        "candidates_emitted": int(candidates_emitted), "candidates_rejected": int(candidates_rejected),
        "option_surface_ran": bool(option_surface_ran), "eligibility_ran": bool(eligibility_ran),
        "ranking_ran": bool(ranking_ran), "advisory_queue_healthy": bool(advisory_queue_healthy),
        "cas_freeze": bool(cas_freeze), "cas_advisory_before_1515": bool(cas_advisory_before_1515),
        "sidecars_completed": list(sidecars_completed or []),
        "shutdown_drain_complete": bool(shutdown_drain_complete),
        "broker_order_calls": order_calls,
        "broker_write_authority": False, "order_authority": False,
        "paper_authorized": False, "live_execution_authorized": False,
        "orders_placed": 0, "orders_modified": 0, "orders_cancelled": 0,
    }
    _write(Path(output_root) / "session_exit_gate.json", payload)
    return payload
