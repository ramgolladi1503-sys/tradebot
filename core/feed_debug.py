from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional, Tuple

from config import config as cfg
from core.depth_store import depth_store
from core.paths import logs_dir
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


def _resolve_db_epochs(db_path: Path) -> tuple[Optional[float], Optional[float]]:
    if not db_path.exists():
        return None, None
    try:
        conn = sqlite3.connect(str(db_path))
    except Exception:
        return None, None
    tick_epoch = None
    depth_epoch = None
    try:
        if _table_exists(conn, "ticks"):
            tick_epoch = _query_max_epoch(conn, "ticks")
        if _table_exists(conn, "depth_snapshots"):
            depth_epoch = _query_max_epoch(conn, "depth_snapshots")
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return tick_epoch, depth_epoch


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
    ws_connected, tokens = _ws_state()
    subs_count = len(tokens)
    subs_sample = tokens[:10]

    mem_tick_epoch = _coerce_epoch(mem_last_tick_epoch())
    mem_tick_age = compute_age_sec(mem_tick_epoch, now_ts) if mem_tick_epoch else None

    db_path = Path(str(getattr(cfg, "TRADE_DB_PATH", ""))).expanduser()
    db_tick_epoch, db_depth_epoch = _resolve_db_epochs(db_path)
    db_tick_age = compute_age_sec(db_tick_epoch, now_ts) if db_tick_epoch else None

    depth_store_epoch = _latest_depth_epoch_from_store()
    depth_epoch = db_depth_epoch
    if depth_store_epoch is not None and (depth_epoch is None or depth_store_epoch > depth_epoch):
        depth_epoch = depth_store_epoch
    depth_age = compute_age_sec(depth_epoch, now_ts) if depth_epoch else None

    token_present, token_count = _token_resolution_stats()

    return {
        "ws_connected": ws_connected,
        "subscribed_tokens_count": subs_count,
        "subscribed_tokens_sample": subs_sample,
        "last_tick_epoch_memory": mem_tick_epoch,
        "last_tick_age_sec": mem_tick_age,
        "last_db_tick_epoch": db_tick_epoch,
        "last_db_tick_age_sec": db_tick_age,
        "last_depth_epoch": depth_epoch,
        "last_depth_age_sec": depth_age,
        "token_resolution_present": token_present,
        "token_resolution_symbols_count": token_count,
        "db_path": str(db_path),
    }
