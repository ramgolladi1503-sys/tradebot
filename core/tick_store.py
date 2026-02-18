import sqlite3
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from collections import deque
from config import config as cfg
from core.paths import logs_dir
from core.log_writer import get_jsonl_writer

_tick_window = deque(maxlen=200000)
_LAST_TICK_EPOCH = None
_ERROR_LOG_PATH = logs_dir() / "tick_store_errors.jsonl"
_ERROR_LOGGER = get_jsonl_writer(_ERROR_LOG_PATH)

def _conn():
    Path(cfg.TRADE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(cfg.TRADE_DB_PATH)

def init_ticks():
    with _conn() as conn:
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
        try:
            conn.execute("ALTER TABLE ticks ADD COLUMN timestamp_epoch REAL")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE ticks ADD COLUMN timestamp_iso TEXT")
        except Exception:
            pass

def _to_epoch(ts):
    if ts is None or ts == "" or ts == "None":
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        if hasattr(ts, "timestamp"):
            return float(ts.timestamp())
    except Exception:
        pass
    try:
        return float(ts)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(str(ts)).timestamp()
    except Exception:
        return None


def _parse_ts_epoch(ts):
    if ts is None or ts == "" or ts == "None":
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        if hasattr(ts, "timestamp"):
            return float(ts.timestamp())
    except Exception:
        pass
    try:
        return float(ts)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(str(ts)).timestamp()
    except Exception:
        return None


def record_tick_epoch(ts_epoch):
    if ts_epoch is None:
        return
    global _LAST_TICK_EPOCH
    try:
        ts_val = float(ts_epoch)
    except Exception:
        return
    _LAST_TICK_EPOCH = ts_val
    _tick_window.append(ts_val)


def insert_tick(ts, token, last_price, volume, oi):
    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    ts_epoch = _parse_ts_epoch(ts)
    skew = None
    if ts_epoch is not None:
        skew = abs(ts_epoch - now_epoch)
    if ts_epoch is None or (skew is not None and skew > getattr(cfg, "MAX_CLOCK_SKEW_SEC", 5.0)):
        ts_epoch = now_epoch
        ts_iso = now_iso
        if skew is not None:
            try:
                log_path = logs_dir() / "clock_skew.jsonl"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a") as f:
                    f.write(
                        json.dumps(
                            {
                                "ts": now_iso,
                                "event": "CLOCK_SKEW",
                                "stream": "ticks",
                                "skew_sec": skew,
                                "instrument_token": token,
                            }
                        )
                        + "\n"
                    )
            except Exception:
                pass
    else:
        ts_iso = datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    record_tick_epoch(ts_epoch)
    try:
        init_ticks()
        with _conn() as conn:
            conn.execute(
                """
            INSERT INTO ticks (timestamp, instrument_token, last_price, volume, oi, timestamp_epoch, timestamp_iso)
            VALUES (?,?,?,?,?,?,?)
            """,
                (ts_iso, token, last_price, volume, oi, ts_epoch, ts_iso),
            )
    except Exception as exc:
        try:
            _ERROR_LOGGER.write(
                {
                    "ts_epoch": now_epoch,
                    "event": "TICK_STORE_ERROR",
                    "instrument_token": token,
                    "error": str(exc),
                }
            )
        except Exception:
            pass
        return False
    return True


def msgs_last_min() -> int:
    now = time.time()
    while _tick_window and now - _tick_window[0] > 60:
        _tick_window.popleft()
    return len(_tick_window)


def last_tick_epoch():
    return _LAST_TICK_EPOCH
