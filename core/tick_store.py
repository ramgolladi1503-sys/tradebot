import sqlite3
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from collections import deque
from config import config as cfg
from core.fs_utils import ensure_parent_dir
from core.paths import logs_dir
from core.log_writer import get_jsonl_writer
from core.time_utils import compute_age_sec, now_utc_epoch

_tick_window = deque(maxlen=200000)
_LAST_TICK_EPOCH = None
_LAST_TICK_BY_TOKEN: dict[int, dict] = {}
_ERROR_LOG_PATH = logs_dir() / "tick_store_errors.jsonl"
_ERROR_LOGGER = get_jsonl_writer(_ERROR_LOG_PATH)

def _conn():
    db_path = ensure_parent_dir(Path(str(cfg.TRADE_DB_PATH)))
    return sqlite3.connect(str(db_path))

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


def insert_tick(ts=None, token=None, last_price=None, volume=None, oi=None, **kwargs):
    allowed_aliases = {"ts_epoch", "instrument_token"}
    unexpected = sorted(set(kwargs.keys()) - allowed_aliases)
    if unexpected:
        allowed = "ts, token, last_price, volume, oi, ts_epoch, instrument_token"
        label = "argument" if len(unexpected) == 1 else "arguments"
        raise TypeError(
            f"insert_tick() got unexpected keyword {label}: {', '.join(unexpected)}. "
            f"Allowed kwargs: {allowed}"
        )

    ts_alias = kwargs.pop("ts_epoch", None)
    token_alias = kwargs.pop("instrument_token", None)

    if ts_alias is not None:
        if ts is not None and ts != ts_alias:
            raise TypeError("insert_tick() received both ts and ts_epoch with different values")
        ts = ts_alias
    if token_alias is not None:
        if token is not None and token != token_alias:
            raise TypeError("insert_tick() received both token and instrument_token with different values")
        token = token_alias

    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    ts_epoch = _parse_ts_epoch(ts)
    if ts_epoch is None:
        ts_epoch = now_epoch
        ts_iso = now_iso
        fallback_reason = "missing_ts" if ts in (None, "", "None") else "invalid_ts"
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
                            "skew_sec": None,
                            "instrument_token": token,
                            "reason": fallback_reason,
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
        from core.market_data_monitor import record_tick

        record_tick(
            token=token,
            symbol=None,
            ts_epoch=ts_epoch,
            has_depth=False,
            is_index=False,
            now_epoch=now_epoch,
        )
    except Exception:
        pass
    try:
        if token is not None:
            _LAST_TICK_BY_TOKEN[int(token)] = {
                "ltp": float(last_price) if last_price is not None else None,
                "ts_epoch": ts_epoch,
            }
    except Exception:
        pass
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


def get_last_tick(token: int | str | None, allow_db: bool = True) -> dict | None:
    if token is None:
        return None
    try:
        token_int = int(token)
    except Exception:
        return None
    cached = _LAST_TICK_BY_TOKEN.get(token_int)
    if cached and cached.get("ts_epoch") is not None:
        return {"ltp": cached.get("ltp"), "ts_epoch": cached.get("ts_epoch"), "source": "memory"}
    if not allow_db:
        return None
    try:
        init_ticks()
        with _conn() as conn:
            row = conn.execute(
                "SELECT last_price, timestamp_epoch FROM ticks WHERE instrument_token=? ORDER BY timestamp_epoch DESC LIMIT 1",
                (token_int,),
            ).fetchone()
        if not row:
            return None
        return {"ltp": row[0], "ts_epoch": row[1], "source": "db"}
    except Exception:
        return None


def get_ltp(token: int | str | None) -> tuple[float | None, float | None]:
    tick = get_last_tick(token, allow_db=True)
    if not isinstance(tick, dict):
        return None, None
    return tick.get("ltp"), tick.get("ts_epoch")


def get_age_sec(token: int | str | None, now_epoch: float | None = None) -> float | None:
    now_epoch = float(now_epoch if now_epoch is not None else now_utc_epoch())
    _ltp, ts_epoch = get_ltp(token)
    if ts_epoch is None:
        return None
    return compute_age_sec(ts_epoch, now_epoch)
