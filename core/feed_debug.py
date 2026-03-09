from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Any, Optional, Tuple

from config import config as cfg
from core.depth_store import depth_store
from core.fs_utils import ensure_parent_dir
from core.paths import logs_dir, trade_db_path
from core.feed.runtime_store import read_latest_runtime_snapshot, init_feed_runtime_table
from core.tick_store import get_max_tick_epoch, init_ticks as init_tick_schema
from core.tick_store import last_tick_epoch as mem_last_tick_epoch
from core.time_utils import compute_age_sec, now_utc_epoch


def _coerce_epoch(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        val = float(value)
        if val > 1e12:
            val = val / 1000.0
        return val
    except Exception:
        return None


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return bool(row and row[0])
    except Exception:
        return False


def _query_max_epoch(conn: sqlite3.Connection, table: str) -> Optional[float]:
    try:
        row = conn.execute(f"SELECT MAX(timestamp_epoch) FROM {table}").fetchone()
    except Exception:
        return None
    if not row:
        return None
    return _coerce_epoch(row[0])


def _ensure_ticks_schema(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticks (
                timestamp TEXT,
                instrument_token INTEGER,
                last_price REAL,
                volume INTEGER,
                oi INTEGER,
                timestamp_epoch REAL,
                timestamp_iso TEXT
            )
            """
        )
        return True
    except Exception:
        return False


def _resolve_db_epochs(db_path: Path) -> tuple[Optional[float], Optional[float], bool, bool]:
    if not db_path.exists():
        return None, None, False, False
    try:
        conn = sqlite3.connect(str(db_path))
    except Exception:
        return None, None, False, False
    tick_epoch = None
    depth_epoch = None
    ticks_table_exists = False
    ticks_table_auto_created = False
    try:
        ticks_table_exists = _table_exists(conn, "ticks")
        if not ticks_table_exists:
            ticks_table_auto_created = _ensure_ticks_schema(conn)
            ticks_table_exists = _table_exists(conn, "ticks")
        if ticks_table_exists:
            tick_epoch = _coerce_epoch(get_max_tick_epoch(conn))
        if _table_exists(conn, "depth_snapshots"):
            depth_epoch = _query_max_epoch(conn, "depth_snapshots")
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return tick_epoch, depth_epoch, ticks_table_exists, ticks_table_auto_created


def _recent_distinct_tokens(db_path: Path, now_ts: float, window_sec: float) -> int:
    if not db_path.exists():
        return 0
    since_epoch = max(0.0, float(now_ts) - max(1.0, float(window_sec)))
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT instrument_token) FROM ticks WHERE timestamp_epoch >= ?",
                (since_epoch,),
            ).fetchone()
    except Exception:
        return 0
    try:
        return int((row or [0])[0] or 0)
    except Exception:
        return 0


def _latest_depth_epoch_from_store() -> Optional[float]:
    latest = None
    for book in depth_store.books.values():
        ts = book.get("ts_epoch") or book.get("ts")
        ts_val = _coerce_epoch(ts)
        if ts_val is None:
            continue
        if latest is None or ts_val > latest:
            latest = ts_val
    return latest


def _ws_state() -> Tuple[Optional[bool], list[int]]:
    try:
        import core.kite_depth_ws as ws
    except Exception:
        return None, []

    tokens = []
    try:
        tokens = list(getattr(ws, "_LAST_TOKENS", []) or [])
    except Exception:
        tokens = []

    ticker = getattr(ws, "_KITE_TICKER", None)
    if ticker is None:
        return None, tokens
    try:
        attr = getattr(ticker, "is_connected", None)
        if callable(attr):
            return bool(attr()), tokens
        if isinstance(attr, bool):
            return attr, tokens
    except Exception:
        return None, tokens
    return None, tokens


def _ws_last_tick_epoch() -> Optional[float]:
    try:
        import core.kite_depth_ws as ws
    except Exception:
        return None
    return _coerce_epoch(getattr(ws, "_LAST_WS_TICK_EPOCH", None))


def _resolve_db_path() -> Path:
    raw_cfg = str(getattr(cfg, "TRADE_DB_PATH", "") or "").strip()
    if raw_cfg:
        return ensure_parent_dir(Path(raw_cfg).expanduser())
    desk_id = str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
    try:
        return ensure_parent_dir(Path(trade_db_path(desk_id)))
    except Exception:
        return ensure_parent_dir(logs_dir() / "desks" / "DEFAULT" / "trades.db")


def _feed_runtime_snapshot(now_ts: float, max_age_sec: float = 10.0) -> tuple[dict[str, Any] | None, float | None]:
    path = logs_dir() / "feed_runtime_latest.json"
    if not path.exists():
        return None, None
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    snap_ts = _coerce_epoch(payload.get("ts_epoch"))
    snap_age = compute_age_sec(snap_ts, now_ts) if snap_ts else None
    if snap_age is None or snap_age > float(max_age_sec):
        return None, snap_age
    payload["_snapshot_path"] = str(path)
    payload["_snapshot_age_sec"] = snap_age
    return payload, snap_age


def _token_resolution_stats() -> tuple[bool, int]:
    path = logs_dir() / "token_resolution.json"
    if not path.exists():
        return False, 0
    try:
        raw = path.read_text()
    except Exception:
        return True, 0
    count = 0
    try:
        import json

        data = json.loads(raw)
        if isinstance(data, dict):
            count = len(data.keys())
        elif isinstance(data, list):
            count = len(data)
    except Exception:
        count = 0
    return True, int(count)


def get_feed_debug(now_epoch: Optional[float] = None) -> dict[str, Any]:
    now_ts = float(now_epoch if now_epoch is not None else now_utc_epoch())
    snapshot_payload, snapshot_age = _feed_runtime_snapshot(now_ts=now_ts, max_age_sec=10.0)
    token_present, token_count = _token_resolution_stats()
    db_path = _resolve_db_path()

    mem_tick_epoch = _coerce_epoch(mem_last_tick_epoch())
    if mem_tick_epoch is None:
        mem_tick_epoch = _ws_last_tick_epoch()
    mem_tick_age = compute_age_sec(mem_tick_epoch, now_ts) if mem_tick_epoch else None

    try:
        init_tick_schema()
    except Exception:
        pass
    try:
        init_feed_runtime_table()
    except Exception:
        pass

    db_tick_epoch, db_depth_epoch, ticks_table_exists, ticks_table_auto_created = _resolve_db_epochs(db_path)
    db_tick_age = compute_age_sec(db_tick_epoch, now_ts) if db_tick_epoch else None
    distinct_tokens_recent = _recent_distinct_tokens(
        db_path=db_path,
        now_ts=now_ts,
        window_sec=float(getattr(cfg, "FEED_DB_TOKEN_WINDOW_SEC", 10.0)),
    )

    runtime_row = read_latest_runtime_snapshot() or {}
    runtime_ts = _coerce_epoch(runtime_row.get("ts_epoch"))
    runtime_age = compute_age_sec(runtime_ts, now_ts) if runtime_ts else None
    runtime_max_age = float(getattr(cfg, "FEED_RUNTIME_MAX_AGE_SEC", 15.0))
    runtime_fresh = bool(runtime_age is not None and runtime_age <= runtime_max_age)
    runtime_ws_connected = runtime_row.get("ws_connected") if runtime_fresh else None
    runtime_ws_tick_epoch = _coerce_epoch(runtime_row.get("last_ws_tick_epoch")) if runtime_fresh else None
    runtime_sub_count = int(runtime_row.get("subscribed_tokens_count") or 0) if runtime_fresh else 0
    runtime_intended_count = int(runtime_row.get("intended_tokens_count") or 0) if runtime_fresh else 0
    runtime_sub_sample = list(runtime_row.get("subscribed_tokens_sample") or []) if runtime_fresh else []
    runtime_sub_by_symbol = dict(runtime_row.get("subscribed_tokens_count_by_symbol") or {}) if runtime_fresh else {}
    runtime_missing_option_count = int(runtime_row.get("missing_option_tokens_count") or 0) if runtime_fresh else 0
    runtime_missing_option_by_symbol = dict(runtime_row.get("missing_option_tokens_count_by_symbol") or {}) if runtime_fresh else {}
    runtime_state = str(runtime_row.get("runtime_state") or "").strip().upper() if runtime_fresh else ""
    runtime_error = str(runtime_row.get("last_error") or "") if runtime_fresh else ""
    snapshot_ws_connected = snapshot_payload.get("ws_connected") if isinstance(snapshot_payload, dict) else None
    snapshot_ws_tick_epoch = _coerce_epoch(snapshot_payload.get("last_ws_tick_epoch")) if isinstance(snapshot_payload, dict) else None
    snapshot_sub_count = int(snapshot_payload.get("subscribed_tokens_count") or 0) if isinstance(snapshot_payload, dict) else 0
    snapshot_intended_count = int(snapshot_payload.get("intended_tokens_count") or 0) if isinstance(snapshot_payload, dict) else 0
    snapshot_sub_sample = list(snapshot_payload.get("subscribed_tokens_sample") or []) if isinstance(snapshot_payload, dict) else []
    snapshot_sub_by_symbol = dict(snapshot_payload.get("subscribed_tokens_count_by_symbol") or {}) if isinstance(snapshot_payload, dict) else {}
    snapshot_missing_option_count = int(snapshot_payload.get("missing_option_tokens_count") or 0) if isinstance(snapshot_payload, dict) else 0
    snapshot_missing_option_by_symbol = dict(snapshot_payload.get("missing_option_tokens_count_by_symbol") or {}) if isinstance(snapshot_payload, dict) else {}
    snapshot_option_sub_count = int(snapshot_payload.get("subscribed_option_tokens_count") or 0) if isinstance(snapshot_payload, dict) else 0
    snapshot_option_age_by_symbol = (
        dict(snapshot_payload.get("option_last_tick_age_by_symbol") or {}) if isinstance(snapshot_payload, dict) else {}
    )
    snapshot_option_resolved_by_symbol = (
        dict(snapshot_payload.get("option_tokens_resolved_count_by_symbol") or {}) if isinstance(snapshot_payload, dict) else {}
    )
    snapshot_option_subscribed_by_symbol = (
        dict(snapshot_payload.get("option_tokens_subscribed_count_by_symbol") or {}) if isinstance(snapshot_payload, dict) else {}
    )
    snapshot_option_ticks_received_by_symbol = (
        dict(snapshot_payload.get("option_ticks_received_count_by_symbol") or {}) if isinstance(snapshot_payload, dict) else {}
    )
    snapshot_last_option_tick_ts_by_symbol = (
        dict(snapshot_payload.get("last_option_tick_ts_by_symbol") or {}) if isinstance(snapshot_payload, dict) else {}
    )
    snapshot_option_feed_block_reason_by_symbol = (
        dict(snapshot_payload.get("option_feed_block_reason_by_symbol") or {}) if isinstance(snapshot_payload, dict) else {}
    )
    snapshot_option_active_blockers_by_symbol = (
        dict(snapshot_payload.get("option_active_blockers_by_symbol") or {}) if isinstance(snapshot_payload, dict) else {}
    )
    snapshot_option_tick_sample = (
        list(snapshot_payload.get("option_last_tick_sample") or []) if isinstance(snapshot_payload, dict) else []
    )
    snapshot_state = str(snapshot_payload.get("runtime_state") or "").strip().upper() if isinstance(snapshot_payload, dict) else ""
    snapshot_error = str(snapshot_payload.get("last_error") or "") if isinstance(snapshot_payload, dict) else ""

    inferred_connected = None
    if db_tick_age is not None:
        inferred_connected = bool(db_tick_age <= float(getattr(cfg, "FEED_DB_MAX_STALENESS_SEC", 8.0)))

    ws_connected = runtime_ws_connected
    ws_connected_source = "feed_runtime" if runtime_fresh else "inferred_ticks"
    if ws_connected is None and snapshot_ws_connected in (True, False):
        ws_connected = bool(snapshot_ws_connected)
        ws_connected_source = "snapshot_file"
    if ws_connected is None:
        ws_connected = inferred_connected
        ws_connected_source = "inferred_ticks"
    if ws_connected is None:
        local_ws, _local_tokens = _ws_state()
        ws_connected = local_ws
        ws_connected_source = "local_process"

    if runtime_fresh and runtime_sub_count > 0:
        subs_count = runtime_sub_count
        subs_sample = runtime_sub_sample[:10]
        subs_by_symbol = runtime_sub_by_symbol
        missing_option_count = runtime_missing_option_count
        missing_option_by_symbol = runtime_missing_option_by_symbol
    elif snapshot_sub_count > 0:
        subs_count = snapshot_sub_count
        subs_sample = snapshot_sub_sample[:10]
        subs_by_symbol = snapshot_sub_by_symbol
        missing_option_count = snapshot_missing_option_count
        missing_option_by_symbol = snapshot_missing_option_by_symbol
    else:
        subs_count = int(distinct_tokens_recent)
        subs_sample = []
        subs_by_symbol = {}
        missing_option_count = 0
        missing_option_by_symbol = {}
    intended_tokens_count = runtime_intended_count or snapshot_intended_count or int(subs_count)
    runtime_state_final = runtime_state or snapshot_state or None
    runtime_error_final = runtime_error or snapshot_error or None

    depth_store_epoch = _latest_depth_epoch_from_store()
    depth_epoch = db_depth_epoch
    if depth_store_epoch is not None and (depth_epoch is None or depth_store_epoch > depth_epoch):
        depth_epoch = depth_store_epoch
    depth_age = compute_age_sec(depth_epoch, now_ts) if depth_epoch else None

    last_tick_epoch = runtime_ws_tick_epoch
    if last_tick_epoch is None:
        last_tick_epoch = snapshot_ws_tick_epoch
    if last_tick_epoch is None:
        last_tick_epoch = mem_tick_epoch
    last_tick_age = compute_age_sec(last_tick_epoch, now_ts) if last_tick_epoch else None
    if db_tick_epoch is None and isinstance(snapshot_payload, dict):
        db_tick_epoch = _coerce_epoch(snapshot_payload.get("last_db_tick_epoch"))
        db_tick_age = _coerce_epoch(snapshot_payload.get("last_db_tick_age_sec"))
        if db_tick_age is None and db_tick_epoch is not None:
            db_tick_age = compute_age_sec(db_tick_epoch, now_ts)

    return {
        "ws_connected": ws_connected,
        "ws_connected_source": ws_connected_source,
        "subscribed_tokens_count": subs_count,
        "intended_tokens_count": intended_tokens_count,
        "subscribed_tokens_sample": subs_sample,
        "subscribed_tokens_count_by_symbol": subs_by_symbol,
        "missing_option_tokens_count": int(missing_option_count),
        "missing_option_tokens_count_by_symbol": missing_option_by_symbol,
        "subscribed_option_tokens_count": int(snapshot_option_sub_count),
        "option_last_tick_age_by_symbol": snapshot_option_age_by_symbol,
        "option_tokens_resolved_count_by_symbol": snapshot_option_resolved_by_symbol,
        "option_tokens_subscribed_count_by_symbol": snapshot_option_subscribed_by_symbol,
        "option_ticks_received_count_by_symbol": snapshot_option_ticks_received_by_symbol,
        "last_option_tick_ts_by_symbol": snapshot_last_option_tick_ts_by_symbol,
        "option_feed_block_reason_by_symbol": snapshot_option_feed_block_reason_by_symbol,
        "option_active_blockers_by_symbol": snapshot_option_active_blockers_by_symbol,
        "option_last_tick_sample": snapshot_option_tick_sample,
        "last_tick_epoch_memory": last_tick_epoch,
        "last_tick_age_sec": last_tick_age,
        "last_db_tick_epoch": db_tick_epoch,
        "last_db_tick_age_sec": db_tick_age,
        "ticks_table_exists": bool(ticks_table_exists),
        "ticks_table_auto_created": bool(ticks_table_auto_created),
        "last_depth_epoch": depth_epoch,
        "last_depth_age_sec": depth_age,
        "token_resolution_present": token_present,
        "token_resolution_symbols_count": token_count,
        "db_path": str(db_path),
        "feed_runtime_snapshot_path": str(logs_dir() / "feed_runtime_latest.json"),
        "feed_runtime_snapshot_age_sec": snapshot_age,
        "feed_runtime_db_age_sec": runtime_age,
        "feed_runtime_source": str(runtime_row.get("source") or "") if runtime_row else "",
        "feed_runtime_state": runtime_state_final,
        "feed_runtime_last_error": runtime_error_final,
        "ws_connected_inferred": inferred_connected,
        "distinct_tokens_recent": distinct_tokens_recent,
        "last_tick_epoch_memory_local": mem_tick_epoch,
        "last_tick_age_sec_local": mem_tick_age,
    }
