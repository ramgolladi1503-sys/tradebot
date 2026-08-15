"""Read-only Phase 1 candidate-pipeline observability.

This module records observations at the orchestrator/TradeBuilder boundary.  It
never changes candidates, gates, exceptions, or execution authority.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from typing import Any, Mapping

from core.events import write_json_atomic
from core.paths import logs_dir


PHASE1_OBSERVABILITY_SCHEMA_VERSION = 1
PHASE1_LATEST_FILENAME = "phase1_observability_latest.json"
PHASE1_EVENTS_FILENAME = "phase1_observability.jsonl"
PHASE1_RUNTIME_DIRNAME = "phase1_observability"


def _runtime_identity() -> tuple[str, str]:
    run_id = str(os.getenv("TRADEBOT_RUN_ID") or os.getenv("RUN_ID") or "unknown-run").strip()
    session_id = str(os.getenv("TRADEBOT_SESSION_ID") or os.getenv("SESSION_ID") or run_id).strip()
    return run_id, session_id


def _current_input(market_data: Mapping[str, Any]) -> bool:
    for key in ("input_current", "market_data_current", "snapshot_current"):
        if key in market_data:
            return bool(market_data.get(key))
    return True


def _safe_reason_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {str(k): max(0, int(v or 0)) for k, v in value.items() if str(k).strip()}


def build_phase1_observation(
    *,
    cycle_id: str,
    market_data: Mapping[str, Any] | None,
    scan_summary: Mapping[str, Any] | None,
    survivor_count: int,
    phase2_handoff_count: int,
    raw_input_count: int,
    strategy_evaluation_count: int,
    exception_type: str | None = None,
) -> dict[str, Any]:
    md = dict(market_data or {})
    summary = dict(scan_summary or {})
    run_id, session_id = _runtime_identity()
    exception_types = [str(exception_type)] if exception_type else []
    return {
        "schema_version": PHASE1_OBSERVABILITY_SCHEMA_VERSION,
        "source": "orchestrator.trade_builder_boundary",
        "run_id": run_id,
        "session_id": session_id,
        "cycle_id": str(cycle_id),
        "timestamp_epoch": time.time(),
        "symbol": str(md.get("symbol") or "").upper(),
        "raw_input_count": max(0, int(raw_input_count)),
        "strategy_evaluation_count": max(0, int(strategy_evaluation_count)),
        "pre_filter_count": max(0, int(summary.get("total_candidates") or 0)),
        "rejection_reason_counts": _safe_reason_counts(summary.get("rejected_by_reason")),
        "survivor_count": max(0, int(survivor_count)),
        "phase2_handoff_count": max(0, int(phase2_handoff_count)),
        "exception_count": 1 if exception_type else 0,
        "exception_types": exception_types,
        "input_current": _current_input(md),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
    }


def record_phase1_observation(payload: Mapping[str, Any]) -> None:
    """Best-effort runtime evidence; telemetry failure cannot affect runtime."""
    try:
        row = dict(payload)
        session_id = str(row.get("session_id") or "unknown-session").strip()
        session_id = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id) or "unknown-session"
        target = logs_dir() / PHASE1_RUNTIME_DIRNAME / session_id
        target.mkdir(parents=True, exist_ok=True)
        write_json_atomic(target / PHASE1_LATEST_FILENAME, row)
        with (target / PHASE1_EVENTS_FILENAME).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    except Exception:
        return


def read_phase1_session_observations(session_id: str, *, logs_root=None) -> list[dict[str, Any]]:
    """Read only the explicitly requested session's observations."""
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id or "")) or "unknown-session"
    root = logs_dir() if logs_root is None else logs_root
    path = root / PHASE1_RUNTIME_DIRNAME / safe_id / PHASE1_EVENTS_FILENAME
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(row, dict) and str(row.get("session_id") or "") == str(session_id):
            rows.append(row)
    return rows


def merge_phase1_cycle_observations(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate only supplied rows; no process-global mutable counters."""
    rows = [dict(row) for row in rows if isinstance(row, Mapping)]
    reasons: Counter[str] = Counter()
    types: set[str] = set()
    for row in rows:
        reasons.update(_safe_reason_counts(row.get("rejection_reason_counts")))
        types.update(str(v) for v in row.get("exception_types") or [])
    return {
        "invocation_count": len(rows),
        "raw_input_count": sum(int(row.get("raw_input_count") or 0) for row in rows),
        "strategy_evaluation_count": sum(int(row.get("strategy_evaluation_count") or 0) for row in rows),
        "pre_filter_count": sum(int(row.get("pre_filter_count") or 0) for row in rows),
        "survivor_count": sum(int(row.get("survivor_count") or 0) for row in rows),
        "phase2_handoff_count": sum(int(row.get("phase2_handoff_count") or 0) for row in rows),
        "rejection_reason_counts": dict(sorted(reasons.items())),
        "exception_count": sum(int(row.get("exception_count") or 0) for row in rows),
        "exception_types": sorted(types),
        "input_current": all(bool(row.get("input_current")) for row in rows) if rows else True,
    }


__all__ = ["build_phase1_observation", "merge_phase1_cycle_observations", "read_phase1_session_observations", "record_phase1_observation"]
