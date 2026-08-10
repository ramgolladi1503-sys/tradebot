from __future__ import annotations

import json
import sqlite3
import queue
import threading
import time
import logging
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from config import config as cfg
from core.events import write_json_atomic
from core.feed_execution_truth import attach_feed_execution_truth
from core.feed_startup_lifecycle import record_feed_startup_event
from core.feed_truth_state import classify_feed_truth_state
from core.feed.ws_lifecycle_shell import derive_transport_health
from core.fs_utils import ensure_parent_dir
from core.runtime_truth_integrity import build_truth_integrity_payload
from core.paths import repo_root, trade_db_path
from core.time_utils import now_utc_epoch
from core.persistence_durability import record_degradation

logger = logging.getLogger(__name__)

_RUNTIME_WRITE_QUEUE = queue.Queue(maxsize=2048)
_RUNTIME_STOP = threading.Event()
_RUNTIME_LOCK = threading.Lock()
_RUNTIME_WORKER = None
_RUNTIME_ENQUEUED = 0
_RUNTIME_REJECTED = 0
_RUNTIME_FAILURES = 0
_RUNTIME_DEGRADED = False
_RUNTIME_PERSISTED = 0
_RUNTIME_SHUTDOWN = False


def _db_path() -> Path:
    raw = str(getattr(cfg, "TRADE_DB_PATH", "") or "").strip()
    if raw:
        return ensure_parent_dir(Path(raw).expanduser())
    desk_id = str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
    return ensure_parent_dir(trade_db_path(desk_id))


@contextmanager
def _conn():
    conn = sqlite3.connect(str(_db_path()), timeout=30.0, check_same_thread=False)
    try:
        try:
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        with conn:
            yield conn
    finally:
        conn.close()


def init_feed_runtime_table() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feed_runtime (
                ts_epoch REAL,
                ws_connected INTEGER,
                subscribed_tokens_count INTEGER,
                intended_tokens_count INTEGER,
                subscribed_tokens_sample TEXT,
                last_ws_tick_epoch REAL,
                last_depth_epoch REAL,
                source TEXT,
                runtime_state TEXT,
                last_error TEXT
            )
            """
        )
        try:
            cols = {
                str(row[1]).strip().lower()
                for row in conn.execute("PRAGMA table_info(feed_runtime)").fetchall()
            }
            if "intended_tokens_count" not in cols:
                conn.execute("ALTER TABLE feed_runtime ADD COLUMN intended_tokens_count INTEGER")
            if "runtime_state" not in cols:
                conn.execute("ALTER TABLE feed_runtime ADD COLUMN runtime_state TEXT")
            if "last_error" not in cols:
                conn.execute("ALTER TABLE feed_runtime ADD COLUMN last_error TEXT")
        except Exception:
            pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_feed_runtime_ts ON feed_runtime(ts_epoch)")


def _coerce_epoch(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out > 1e12:
            out = out / 1000.0
        return out
    except Exception:
        return None


def canonicalize_feed_runtime_snapshot_truth(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload or {})
    runtime_state = str(out.get("runtime_state") or "").strip().upper()
    feed_truth_state = str(out.get("feed_truth_state") or "").strip().upper()
    reconnect_blocked_reason = str(out.get("reconnect_blocked_reason") or "").strip().lower()
    process_restart_required = bool(out.get("process_restart_required"))
    ws_connected = out.get("ws_connected")
    blocked_snapshot = bool(
        reconnect_blocked_reason
        or process_restart_required
        or runtime_state in {"RECOVERY_BLOCKED", "DEAD", "SUBSCRIBE_FAILED", "WS_DISCONNECTED"}
        or feed_truth_state in {"DEAD", "RECOVERY_BLOCKED"}
        or ws_connected is False
    )
    if not blocked_snapshot:
        return out

    option_block_reason_by_symbol = dict(out.get("option_feed_block_reason_by_symbol") or {})
    option_tokens_subscribed_count_by_symbol = dict(out.get("option_tokens_subscribed_count_by_symbol") or {})
    option_ticks_received_count_by_symbol = dict(out.get("option_ticks_received_count_by_symbol") or {})
    option_active_blockers_by_symbol = {
        str(symbol).upper(): [str(reason).strip().upper() for reason in list(reasons or []) if str(reason).strip()]
        for symbol, reasons in dict(out.get("option_active_blockers_by_symbol") or {}).items()
    }
    tracked_symbols = (
        set(str(symbol).upper() for symbol in option_block_reason_by_symbol.keys())
        | set(str(symbol).upper() for symbol in option_tokens_subscribed_count_by_symbol.keys())
        | set(str(symbol).upper() for symbol in option_ticks_received_count_by_symbol.keys())
    )
    normalized_block_reason_by_symbol: dict[str, str] = {}
    normalized_active_blockers_by_symbol: dict[str, list[str]] = {}
    for symbol in sorted(sym for sym in tracked_symbols if sym):
        reason_text = str(option_block_reason_by_symbol.get(symbol) or "").strip().upper()
        if not reason_text or reason_text in {"NONE"}:
            reason_text = "OK"
        normalized_block_reason_by_symbol[symbol] = reason_text
        active_reasons = [
            reason
            for reason in list(option_active_blockers_by_symbol.get(symbol) or [])
            if reason not in {"", "OK", "LIVE", "FRESH", "NONE"}
        ]
        if not active_reasons:
            active_reasons = [reason_text]
        elif reason_text not in active_reasons:
            active_reasons.insert(0, reason_text)
        normalized_active_blockers_by_symbol[symbol] = list(dict.fromkeys(active_reasons))

    if normalized_block_reason_by_symbol:
        out["option_feed_block_reason_by_symbol"] = normalized_block_reason_by_symbol
    if normalized_active_blockers_by_symbol:
        out["option_active_blockers_by_symbol"] = normalized_active_blockers_by_symbol
    return out


def _startup_event_for_runtime_source(source: str, runtime_state: str) -> str | None:
    source_text = str(source or "")
    state_text = str(runtime_state or "").strip().upper()
    if source_text == "start_depth_ws:starting":
        return "START_DEPTH_WS_ENTERED"
    if source_text.startswith("start_depth_ws:auth_blocked") or state_text == "AUTH_BLOCKED":
        return "AUTH_BLOCKED"
    if source_text.startswith("start_depth_ws:connect_failed"):
        return "START_FAILED"
    if source_text.startswith("start_depth_ws:lock_blocked"):
        return "START_FAILED"
    if source_text.startswith("start_depth_ws:import_missing"):
        return "START_FAILED"
    if source_text.startswith("start_depth_ws:subscribe_failed"):
        return "START_FAILED"
    return None


def _canonical_runtime_artifact_payload(payload: dict[str, Any], *, ts_epoch: float) -> dict[str, Any]:
    out = dict(payload or {})
    out["ts_epoch"] = float(ts_epoch)
    reconnect_blocked_reason = str(out.get("reconnect_blocked_reason") or "").strip().lower() or None
    if reconnect_blocked_reason == "partial_recovery":
        reconnect_blocked_reason = None
        out["reconnect_blocked_reason"] = None
        out["restart_blocked_reason"] = None
        out["process_restart_required"] = False
        out["restart_suppressed"] = False
        out.setdefault("runtime_state", "VERIFYING_RECOVERY")
    restart_failure_reason = str(
        out.get("restart_failure_reason")
        or out.get("restart_blocked_reason")
        or reconnect_blocked_reason
        or out.get("last_error")
        or ""
    ).strip() or None
    if reconnect_blocked_reason:
        if reconnect_blocked_reason == "reactor_not_restartable":
            reconnect_blocked_reason = "reactor_not_restartable_process_restart_required"
        out["runtime_state"] = "RECOVERY_BLOCKED"
        state_machine = dict(out.get("state_machine") or {})
        state_machine["state"] = "DOWN"
        state_machine["reason"] = (
            "ws1006_process_restart_required"
            if reconnect_blocked_reason == "ws1006_process_restart_required"
            else (
                "reactor_not_restartable_process_restart_required"
                if reconnect_blocked_reason.startswith("reactor_not_restartable")
                else "reconnect_blocked"
            )
        )
        out["state_machine"] = state_machine
        out["ws_connected"] = False
        out["recovery_action"] = "process_restart_required"
        out["restart_failure_reason"] = restart_failure_reason or reconnect_blocked_reason
        out["ws_reconnect_allowed"] = False
        out["ws_reconnect_attempted"] = False
