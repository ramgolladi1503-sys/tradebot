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
from core.runtime_status_overlay import derive_feed_ok
from core.fs_utils import ensure_parent_dir
from core.runtime_truth_integrity import build_truth_integrity_payload
from core.runtime_boot_identity import stamp_runtime_payload
from core.feed.artifact_provenance import stamp_feed_runtime_provenance
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
    conn = sqlite3.connect(str(_db_path()), timeout=30.0)
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
        out["restart_suppressed"] = True
        out["reactor_not_restartable_detected"] = reconnect_blocked_reason.startswith("reactor_not_restartable")
    elif bool(out.get("process_restart_required")):
        out["restart_failure_reason"] = restart_failure_reason
    if reconnect_blocked_reason and reconnect_blocked_reason.startswith("reactor_not_restartable"):
        out["reactor_not_restartable_detected"] = True
    transport_health = derive_transport_health(
        ws_connected=out.get("ws_connected"),
        reconnect_pending=bool(out.get("reconnect_pending")),
        runtime_state=out.get("runtime_state"),
        reconnect_blocked_reason=reconnect_blocked_reason,
        last_error=out.get("last_error"),
    )
    out.setdefault("transport_state", transport_health["state"])
    out.setdefault("transport_reason", transport_health["reason"])
    out.setdefault("transport_healthy", bool(transport_health["healthy"]))
    out.setdefault("transport", dict(transport_health))
    if "feed_truth_state" not in out:
        feed_truth = classify_feed_truth_state(out, now_epoch=float(ts_epoch))
        out["feed_truth_state"] = str(feed_truth.state)
        out["feed_truth_reason_code"] = str(feed_truth.reason_code)
        out["feed_truth_reasons"] = list(feed_truth.reasons)
        out["feed_truth_strict_live"] = bool(feed_truth.strict_live)
    out = canonicalize_feed_runtime_snapshot_truth(out)
    out = attach_feed_execution_truth(out)
    # The runtime-store writer is a second persistence path for the same
    # authoritative artifact.  Always derive the required boolean from the
    # canonical runtime predicates before persistence; never let an omitted
    # field become an accidental bool(None) at a downstream consumer.
    out["feed_ok"] = bool(derive_feed_ok(out))
    if "recovery_generation_id" not in out:
        # Reuse the live feed coordinator's generation for queued writes.  A
        # missing coordinator generation is deliberately left missing so the
        # shared consumer validator rejects the artifact fail-closed.
        try:
            from core.feed_debug import get_feed_debug

            current_generation = (get_feed_debug() or {}).get("recovery_generation_id")
            if current_generation is not None:
                out["recovery_generation_id"] = int(current_generation)
        except Exception:
            pass
    truth_payload = None
    try:
        import json as _json
        from core.paths import logs_dir as _logs_dir

        truth_path = _logs_dir() / "feed_truth_latest.json"
        if truth_path.exists():
            candidate_truth = _json.loads(truth_path.read_text(encoding="utf-8"))
            if isinstance(candidate_truth, dict):
                truth_payload = candidate_truth
    except Exception:
        truth_payload = None
    out = stamp_feed_runtime_provenance(out, truth_payload=truth_payload)
    # Finalize all semantic and safety fields before hashing. The verifier
    # intentionally includes these fields, so mutating them after the hash
    # creates a false SNAPSHOT_HASH_MISMATCH on every persisted artifact.
    out["read_only"] = True
    out["append"] = False
    out["is_order_action"] = False
    out["broker_api_called"] = False
    out["source"] = str(out.get("source") or "core.feed.runtime_store.write_runtime_snapshot")
    incoming_snapshot_hash = out.get("snapshot_hash")
    out.update(
        build_truth_integrity_payload(
            source_payload=out,
            transport_state=out.get("transport_state"),
            feed_truth_state=out.get("feed_truth_state"),
            reason_code=out.get("feed_truth_reason_code"),
            heartbeat_epoch=ts_epoch,
        )
    )
    if incoming_snapshot_hash and incoming_snapshot_hash != out["snapshot_hash"]:
        out["truth_integrity_alerts"] = [
            {
                "code": "SNAPSHOT_HASH_MISMATCH",
                "message": "Feed runtime snapshot hash does not match the canonical recomputation.",
                "details": {
                    "snapshot_hash": incoming_snapshot_hash,
                    "expected_snapshot_hash": out["snapshot_hash"],
                },
            }
        ]
        out["truth_integrity_alert_count"] = 1
        out["truth_integrity_status"] = "ALERT"
    return out


    out.update(build_truth_integrity_payload(source_payload=out, transport_state=out.get("transport_state"), feed_truth_state=out.get("feed_truth_state"), reason_code=out.get("feed_truth_reason_code"), heartbeat_epoch=ts_epoch))
    return out


def _write_canonical_runtime_artifacts(payload: dict[str, Any], *, ts_epoch: float) -> None:
    artifact = _canonical_runtime_artifact_payload(payload, ts_epoch=ts_epoch)
    root = repo_root()
    from core.paths import logs_dir
    for path in (logs_dir() / "feed_runtime_latest.json", root / ".runtime" / "feed_runtime_latest.json"):
        try:
            write_json_atomic(path, artifact)
        except Exception:
            pass


def _write_runtime_snapshot_sync(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    init_feed_runtime_table()
    ts_epoch = _coerce_epoch(payload.get("ts_epoch"))
    if ts_epoch is None:
        ts_epoch = float(now_utc_epoch())
    ws_connected_raw = payload.get("ws_connected")
    ws_connected = None
    if ws_connected_raw is True:
        ws_connected = 1
    elif ws_connected_raw is False:
        ws_connected = 0
    tokens_count = int(payload.get("subscribed_tokens_count") or 0)
    intended_tokens_count = int(payload.get("intended_tokens_count") or 0)
    sample = payload.get("subscribed_tokens_sample") or []
    if not isinstance(sample, list):
        sample = []
    sample_json = json.dumps(sample[:25], default=str)
    last_ws_tick_epoch = _coerce_epoch(payload.get("last_ws_tick_epoch"))
    last_depth_epoch = _coerce_epoch(payload.get("last_depth_epoch"))
    source = str(payload.get("source") or "unknown")[:120]
    runtime_state = str(payload.get("runtime_state") or "").strip().upper()[:64]
    last_error = str(payload.get("last_error") or "")[:1000]
    try:
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO feed_runtime (
                    ts_epoch,
                    ws_connected,
                    subscribed_tokens_count,
                    intended_tokens_count,
                    subscribed_tokens_sample,
                    last_ws_tick_epoch,
                    last_depth_epoch,
                    source,
                    runtime_state,
                    last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts_epoch,
                    ws_connected,
                    tokens_count,
                    intended_tokens_count,
                    sample_json,
                    last_ws_tick_epoch,
                    last_depth_epoch,
                    source,
                    runtime_state,
                    last_error,
                ),
            )
    except Exception:
        return False
    _write_canonical_runtime_artifacts(payload, ts_epoch=float(ts_epoch))
    lifecycle_details = {
        "source": source,
        "ws_connected": payload.get("ws_connected"),
        "runtime_state": runtime_state,
        "subscribed_tokens_count": tokens_count,
        "intended_tokens_count": intended_tokens_count,
    }
    startup_event = _startup_event_for_runtime_source(source, runtime_state)
    if startup_event:
        record_feed_startup_event(
            startup_event,
            source="core.feed.runtime_store.write_runtime_snapshot",
            details=lifecycle_details,
            error=last_error,
            now_epoch=ts_epoch,
        )
    record_feed_startup_event(
        "FEED_RUNTIME_SNAPSHOT_WRITTEN",
        source="core.feed.runtime_store.write_runtime_snapshot",
        details=lifecycle_details,
        now_epoch=ts_epoch,
    )
    return True


def _runtime_write_loop() -> None:
    global _RUNTIME_FAILURES, _RUNTIME_DEGRADED, _RUNTIME_PERSISTED
    while not _RUNTIME_STOP.is_set() or not _RUNTIME_WRITE_QUEUE.empty():
        try:
            payload = _RUNTIME_WRITE_QUEUE.get(timeout=0.1)
        except queue.Empty:
            continue
        try:
            if not _write_runtime_snapshot_sync(payload):
                with _RUNTIME_LOCK:
                    _RUNTIME_FAILURES += 1
                    _RUNTIME_DEGRADED = True
                    record_degradation("runtime", "RUNTIME_PERSISTENCE_FAILURE")
                logger.warning("feed_runtime_snapshot_persist_failed")
            else:
                with _RUNTIME_LOCK:
                    _RUNTIME_PERSISTED += 1
        finally:
            _RUNTIME_WRITE_QUEUE.task_done()


def _ensure_runtime_worker() -> None:
    global _RUNTIME_WORKER
    with _RUNTIME_LOCK:
        if _RUNTIME_WORKER is None or not _RUNTIME_WORKER.is_alive():
            _RUNTIME_STOP.clear()
            _RUNTIME_WORKER = threading.Thread(target=_runtime_write_loop, name="feed-runtime-persistence", daemon=True)
            _RUNTIME_WORKER.start()


def write_runtime_snapshot(payload: dict[str, Any]) -> bool:
    global _RUNTIME_ENQUEUED, _RUNTIME_REJECTED, _RUNTIME_DEGRADED, _RUNTIME_SHUTDOWN
    if not isinstance(payload, dict):
        return False
    with _RUNTIME_LOCK:
        if _RUNTIME_SHUTDOWN:
            _RUNTIME_REJECTED += 1
            _RUNTIME_DEGRADED = True
            record_degradation('runtime', 'RUNTIME_PERSISTENCE_SHUTDOWN')
            return False
    _ensure_runtime_worker()
    try:
        _RUNTIME_WRITE_QUEUE.put_nowait(deepcopy(payload))
    except queue.Full:
        with _RUNTIME_LOCK:
            _RUNTIME_REJECTED += 1
            _RUNTIME_DEGRADED = True
            record_degradation("runtime", "RUNTIME_QUEUE_FULL")
        logger.error("feed_runtime_snapshot_queue_full")
        return False
    with _RUNTIME_LOCK:
        _RUNTIME_ENQUEUED += 1
    return True


def shutdown_runtime_persistence(deadline_seconds: float = 2.0) -> dict:
    global _RUNTIME_SHUTDOWN
    with _RUNTIME_LOCK:
        _RUNTIME_SHUTDOWN = True
    deadline = time.monotonic() + max(0.0, float(deadline_seconds))
    while _RUNTIME_WRITE_QUEUE.unfinished_tasks and time.monotonic() < deadline:
        time.sleep(0.01)
    _RUNTIME_STOP.set()
    worker = _RUNTIME_WORKER
    if worker is not None:
        worker.join(max(0.0, deadline - time.monotonic()))
    with _RUNTIME_LOCK:
        state = {"queue_depth": _RUNTIME_WRITE_QUEUE.qsize(), "worker_alive": bool(worker and worker.is_alive()),
                 "enqueued": _RUNTIME_ENQUEUED, "rejected": _RUNTIME_REJECTED,
                 "failures": _RUNTIME_FAILURES, "durability_degraded": _RUNTIME_DEGRADED}
    state["complete"] = state["queue_depth"] == 0 and not state["worker_alive"]
    return state


def reset_runtime_persistence_for_tests() -> None:
    """Reset the terminal runtime persistence lifecycle between tests only."""
    global _RUNTIME_WRITE_QUEUE, _RUNTIME_WORKER, _RUNTIME_ENQUEUED
    global _RUNTIME_REJECTED, _RUNTIME_FAILURES, _RUNTIME_DEGRADED
    global _RUNTIME_PERSISTED, _RUNTIME_SHUTDOWN
    result = shutdown_runtime_persistence(deadline_seconds=1.0)
    if result.get('worker_alive'):
        raise RuntimeError('runtime persistence worker did not stop for test reset')
    with _RUNTIME_LOCK:
        _RUNTIME_WRITE_QUEUE = queue.Queue(maxsize=2048)
        _RUNTIME_STOP.clear()
        _RUNTIME_WORKER = None
        _RUNTIME_ENQUEUED = 0
        _RUNTIME_REJECTED = 0
        _RUNTIME_FAILURES = 0
        _RUNTIME_DEGRADED = False
        _RUNTIME_PERSISTED = 0
        _RUNTIME_SHUTDOWN = False


def runtime_persistence_state() -> dict:
    with _RUNTIME_LOCK:
        return {
            "enqueued": _RUNTIME_ENQUEUED,
            "persisted": _RUNTIME_PERSISTED,
            "rejected": _RUNTIME_REJECTED,
            "failures": _RUNTIME_FAILURES,
            "pending": _RUNTIME_WRITE_QUEUE.qsize(),
            "worker_alive": bool(_RUNTIME_WORKER and _RUNTIME_WORKER.is_alive()),
            "worker_ident": _RUNTIME_WORKER.ident if _RUNTIME_WORKER else None,
            "shutdown": bool(_RUNTIME_SHUTDOWN),
        }


def read_latest_runtime_snapshot() -> dict[str, Any] | None:
    try:
        init_feed_runtime_table()
        with _conn() as conn:
            row = conn.execute(
                """
                SELECT
                    ts_epoch,
                    ws_connected,
                    subscribed_tokens_count,
                    intended_tokens_count,
                    subscribed_tokens_sample,
                    last_ws_tick_epoch,
                    last_depth_epoch,
                    source,
                    runtime_state,
                    last_error
                FROM feed_runtime
                ORDER BY ts_epoch DESC
                LIMIT 1
                """
            ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    sample = []
    try:
        sample = json.loads(row[4]) if row[4] else []
    except Exception:
        sample = []
    ws_connected = None
    if row[1] == 1:
        ws_connected = True
    elif row[1] == 0:
        ws_connected = False
    return {
        "ts_epoch": _coerce_epoch(row[0]),
        "ws_connected": ws_connected,
        "subscribed_tokens_count": int(row[2] or 0),
        "intended_tokens_count": int(row[3] or 0),
        "subscribed_tokens_sample": sample if isinstance(sample, list) else [],
        "last_ws_tick_epoch": _coerce_epoch(row[5]),
        "last_depth_epoch": _coerce_epoch(row[6]),
        "source": str(row[7] or "unknown"),
        "runtime_state": str(row[8] or "").strip().upper() or None,
        "last_error": str(row[9] or "") or None,
    }
