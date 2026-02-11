import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from config import config as cfg
from core.depth_store import depth_store
from core.tick_store import last_tick_epoch as _mem_last_tick_epoch
from core.time_utils import is_market_open_ist, normalize_epoch_seconds, now_ist
from core.paths import logs_dir

LOG_PATH = logs_dir() / "freshness_sla.jsonl"
TOKEN_MAP_PATH = logs_dir() / "token_resolution.json"

_CACHE: Dict[str, Any] = {}


def _log_event(payload: Dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(exist_ok=True)
    try:
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def _load_token_map() -> Dict[str, List[int]]:
    if not TOKEN_MAP_PATH.exists():
        return {}
    try:
        data = json.loads(TOKEN_MAP_PATH.read_text())
    except Exception:
        return {}
    if isinstance(data, dict):
        return {k: list(v or []) for k, v in data.items()}
    if isinstance(data, list):
        out: Dict[str, List[int]] = {}
        for row in data:
            symbol = row.get("symbol")
            tokens = row.get("tokens") or []
            if symbol:
                out[symbol] = list(tokens)
        return out
    return {}


def _conn(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def _query_max_epoch(
    conn: sqlite3.Connection, table: str, token_filter: Optional[Sequence[int]] = None
) -> Optional[float]:
    try:
        if token_filter:
            q_marks = ",".join(["?"] * len(token_filter))
            row = conn.execute(
                f"SELECT MAX(timestamp_epoch) FROM {table} WHERE instrument_token IN ({q_marks})",
                token_filter,
            ).fetchone()
        else:
            row = conn.execute(f"SELECT MAX(timestamp_epoch) FROM {table}").fetchone()
        if not row:
            return None
        return normalize_epoch_seconds(row[0])
    except Exception:
        return None


def _query_max_epoch_chunked(
    conn: sqlite3.Connection, table: str, token_filter: Sequence[int], chunk_size: int = 900
) -> Optional[float]:
    if not token_filter:
        return None
    latest = None
    for i in range(0, len(token_filter), chunk_size):
        chunk = token_filter[i : i + chunk_size]
        val = _query_max_epoch(conn, table, chunk)
        if val is None:
            continue
        if latest is None or val > latest:
            latest = val
    return latest


def _latest_depth_epoch_from_store() -> Optional[float]:
    latest = None
    for book in depth_store.books.values():
        ts = book.get("ts_epoch") or book.get("ts")
        ts_norm = normalize_epoch_seconds(ts)
        if ts_norm is None:
            continue
        if latest is None or ts_norm > latest:
            latest = ts_norm
    return latest


def _depth_store_tokens() -> List[int]:
    tokens: List[int] = []
    for key in depth_store.books.keys():
        try:
            tokens.append(int(key))
        except Exception:
            continue
    return tokens


def get_freshness_status(force: bool = False) -> Dict[str, Any]:
    now_epoch = time.time()
    ttl_sec = float(getattr(cfg, "FEED_FRESHNESS_TTL_SEC", 5.0))
    if not force and _CACHE.get("ts_epoch") and (now_epoch - float(_CACHE["ts_epoch"])) <= ttl_sec:
        return dict(_CACHE["payload"])

    market_open = bool(is_market_open_ist())
    max_ltp_age = float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5))
    max_depth_age = float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 6.0))

    ltp_last_epoch = None
    depth_last_epoch = None
    ltp_source = "none"
    depth_source = "none"

    db_path = Path(cfg.TRADE_DB_PATH)
    if db_path.exists():
        try:
            with _conn(db_path) as conn:
                token_map = _load_token_map()
                nifty_tokens = [int(t) for t in (token_map.get("NIFTY") or []) if t is not None]
                store_tokens = _depth_store_tokens()
                tokens_for_ltp: List[int] = []
                if store_tokens:
                    if nifty_tokens:
                        intersect = [t for t in store_tokens if t in set(nifty_tokens)]
                        if intersect:
                            tokens_for_ltp = intersect
                            ltp_source = "depth_tokens_nifty"
                        else:
                            tokens_for_ltp = store_tokens
                            ltp_source = "depth_tokens_all"
                    else:
                        tokens_for_ltp = store_tokens
                        ltp_source = "depth_tokens_all"
                elif nifty_tokens:
                    tokens_for_ltp = nifty_tokens
                    ltp_source = "token_map_nifty"

                if tokens_for_ltp:
                    ltp_last_epoch = _query_max_epoch_chunked(conn, "ticks", tokens_for_ltp)
                if ltp_last_epoch is None:
                    ltp_last_epoch = _query_max_epoch(conn, "ticks")
                    if ltp_last_epoch is not None:
                        ltp_source = "ticks_any"
                depth_last_epoch = _query_max_epoch(conn, "depth_snapshots")
                if depth_last_epoch is not None:
                    depth_source = "depth_snapshots"
        except Exception:
            ltp_last_epoch = None
            depth_last_epoch = None

    depth_store_epoch = _latest_depth_epoch_from_store()
    if depth_store_epoch is not None:
        depth_last_epoch = max(depth_last_epoch or 0.0, depth_store_epoch)
        depth_source = "depth_store"

    mem_tick_epoch = normalize_epoch_seconds(_mem_last_tick_epoch())
    if mem_tick_epoch is not None:
        if ltp_last_epoch is None or mem_tick_epoch > ltp_last_epoch:
            ltp_last_epoch = mem_tick_epoch
            ltp_source = "tick_store_memory"

    ltp_age = (now_epoch - ltp_last_epoch) if ltp_last_epoch is not None else None
    depth_age = (now_epoch - depth_last_epoch) if depth_last_epoch is not None else None
    if ltp_age is not None and ltp_age < 0:
        ltp_age = 0.0
    if depth_age is not None and depth_age < 0:
        depth_age = 0.0

    reasons: List[str] = []

    ltp_ok = ltp_age is not None and ltp_age <= max_ltp_age
    depth_ok = depth_age is not None and depth_age <= max_depth_age

    if market_open:
        if ltp_age is None:
            reasons.append("ltp_missing")
        elif ltp_age > max_ltp_age:
            reasons.append(f"ltp_stale:NIFTY age={ltp_age:.2f} max={max_ltp_age:.2f}")

        if depth_age is None:
            reasons.append("depth_missing")
        elif depth_age > max_depth_age:
            reasons.append(f"depth_stale age={depth_age:.2f} max={max_depth_age:.2f}")

    if not market_open:
        state = "MARKET_CLOSED"
        ok = True
    else:
        if ltp_ok and depth_ok:
            state = "OK"
        elif ltp_ok or depth_ok:
            state = "DEGRADED"
        else:
            state = "STALE"
        ok = state == "OK"

    payload = {
        "ok": ok,
        "state": state,
        "market_open": market_open,
        "ts_epoch": now_epoch,
        "ltp": {
            "ok": ltp_ok if market_open else True,
            "age_sec": ltp_age,
            "max_age_sec": max_ltp_age,
            "symbol": "NIFTY",
            "source": ltp_source,
        },
        "depth": {
            "ok": depth_ok if market_open else True,
            "age_sec": depth_age,
            "max_age_sec": max_depth_age,
            "scope": "options",
            "source": depth_source,
        },
        "reasons": reasons,
    }

    _CACHE["ts_epoch"] = now_epoch
    _CACHE["payload"] = payload

    _log_event(
        {
            "ts_epoch": now_epoch,
            "ts_ist": now_ist().isoformat(),
            "state": state,
            "ok": ok,
            "market_open": market_open,
            "reasons": reasons,
            "ltp_age_sec": ltp_age,
            "depth_age_sec": depth_age,
            "ltp_source": ltp_source,
            "depth_source": depth_source,
        }
    )

    return payload


def _reset_cache_for_tests() -> None:
    _CACHE.clear()
