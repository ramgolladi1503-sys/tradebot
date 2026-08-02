from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional, Tuple

from config import config as cfg
from core.depth_store import depth_store
from core.freshness_sla import get_freshness_status
from core.sqlite_query_registry import max_timestamp_query
from core.tick_store import last_tick_epoch as mem_last_tick_epoch
from core.time_utils import compute_age_sec, now_utc_epoch, is_market_open_ist


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
        row = conn.execute(max_timestamp_query(table)).fetchone()
    except (sqlite3.Error, ValueError):
        return None
    if not row:
        return None
    return _coerce_epoch(row[0])


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


def _market_open_reason(freshness: dict) -> str:
    state = str(freshness.get("state") or "")
    if state == "MARKET_CLOSED":
        return "calendar_closed"
    if state == "OFFHOURS":
        return "live_offhours"
    if state == "PLANNING":
        return "planning_mode"
    if state:
        return state.lower()
    return "unknown"


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


def run_self_test(now_epoch: Optional[float] = None) -> dict[str, Any]:
    now_ts = float(now_epoch if now_epoch is not None else now_utc_epoch())
    freshness = get_freshness_status(force=True)
    market_open = bool(freshness.get("market_open", is_market_open_ist()))
    allow_stale = bool(freshness.get("allow_stale_quotes", False))
    reason = _market_open_reason(freshness)

    ws_connected, tokens = _ws_state()
    subs_count = len(tokens)
    subs_preview = tokens[:10]

    mem_tick_epoch = _coerce_epoch(mem_last_tick_epoch())
    mem_tick_age = compute_age_sec(mem_tick_epoch, now_ts) if mem_tick_epoch else None

    db_path = Path(str(getattr(cfg, "TRADE_DB_PATH", ""))).expanduser()
    db_tick_epoch, db_depth_epoch = _resolve_db_epochs(db_path)
    db_tick_age = compute_age_sec(db_tick_epoch, now_ts) if db_tick_epoch else None
    db_depth_age = compute_age_sec(db_depth_epoch, now_ts) if db_depth_epoch else None

    depth_store_epoch = _latest_depth_epoch_from_store()
    depth_epoch = db_depth_epoch
    if depth_store_epoch is not None and (depth_epoch is None or depth_store_epoch > depth_epoch):
        depth_epoch = depth_store_epoch
    depth_age = compute_age_sec(depth_epoch, now_ts) if depth_epoch else None

    sla_state = str(freshness.get("state") or "UNKNOWN")
    sla_reasons = list(freshness.get("reasons") or [])

    verdict = "OK"
    if (not market_open) or allow_stale:
        verdict = "IDLE"
    elif sla_state == "STALE":
        verdict = "STALE"
    elif sla_state == "DEGRADED":
        verdict = "DEGRADED"
    elif mem_tick_age is None and db_tick_age is None:
        verdict = "STALE"

    hint = "OK"
    if not market_open:
        hint = "Market closed"
    elif subs_count == 0:
        hint = "No subscriptions"
    elif ws_connected is False:
        hint = "WS disconnected"
    elif mem_tick_age is None and db_tick_age is None:
        hint = "DB not writing ticks"
    elif (depth_age is None or (freshness.get("depth") or {}).get("ok") is False) and (freshness.get("ltp") or {}).get("ok"):
        hint = "Depth missing only"
    elif allow_stale:
        hint = "Planning mode (stale quotes allowed)"

    return {
        "market_open": market_open,
        "market_reason": reason,
        "ws_connected": ws_connected,
        "subscriptions_count": subs_count,
        "subscriptions_preview": subs_preview,
        "mem_tick_epoch": mem_tick_epoch,
        "mem_tick_age_sec": mem_tick_age,
        "db_tick_epoch": db_tick_epoch,
        "db_tick_age_sec": db_tick_age,
        "depth_epoch": depth_epoch,
        "depth_age_sec": depth_age,
        "sla_state": sla_state,
        "sla_reasons": sla_reasons,
        "verdict": verdict,
        "hint": hint,
        "db_path": str(db_path),
    }


def _fmt_age(age: Optional[float]) -> str:
    if age is None:
        return "N/A"
    try:
        return f"{float(age):.1f}s"
    except Exception:
        return "N/A"


def main() -> None:
    report = run_self_test()
    ws = report["ws_connected"]
    ws_text = "unknown" if ws is None else ("connected" if ws else "disconnected")
    print("FEED SELF-TEST")
    print(f"Market: {'OPEN' if report['market_open'] else 'CLOSED'} ({report['market_reason']})")
    print(f"WS: {ws_text}")
    print(f"Subs: {report['subscriptions_count']} {report['subscriptions_preview']}")
    print(f"Tick(mem): age={_fmt_age(report['mem_tick_age_sec'])} last={report['mem_tick_epoch']}")
    print(f"Tick(DB):  age={_fmt_age(report['db_tick_age_sec'])} last={report['db_tick_epoch']}")
    print(f"Depth:     age={_fmt_age(report['depth_age_sec'])} last={report['depth_epoch']}")
    print(f"SLA: {report['sla_state']} reasons={report['sla_reasons']}")
    print(f"VERDICT: {report['verdict']}")
    print(f"HINT: {report['hint']}")


if __name__ == "__main__":
    main()
