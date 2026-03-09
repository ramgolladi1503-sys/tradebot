from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from config import config as cfg
from core.fs_utils import ensure_parent_dir
from core.paths import trade_db_path
from core.time_utils import now_utc_epoch


def _db_path() -> Path:
    raw = str(getattr(cfg, "TRADE_DB_PATH", "") or "").strip()
    if raw:
        return ensure_parent_dir(Path(raw).expanduser())
    desk_id = str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
    return ensure_parent_dir(trade_db_path(desk_id))


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(str(_db_path()))


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


def write_runtime_snapshot(payload: dict[str, Any]) -> bool:
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
    return True


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
