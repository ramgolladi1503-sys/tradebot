"""Causal read-only market snapshot producer backed by canonical SQLite."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.market_snapshot_builder import build_market_snapshot
from core.market_snapshot_store import write_market_snapshot_atomic
from core.market_snapshot_schema import validate_market_snapshot


DEFAULT_INDEX_TOKENS = {"NIFTY": 256265, "BANKNIFTY": 260105, "SENSEX": 265}


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat().replace("+00:00", "Z")


def _bar(rows: list[tuple[Any, ...]]) -> dict[str, float | None]:
    prices = [float(r[0]) for r in rows if r[0] is not None]
    if not prices:
        return {"open": None, "high": None, "low": None, "close": None}
    return {"open": prices[0], "high": max(prices), "low": min(prices), "close": prices[-1]}


def build_live_market_snapshot(*, db_path: str | Path, output_path: str | Path,
                               session_id: str, session_date: str, source_sha: str,
                               now_epoch: float | None = None) -> dict[str, Any]:
    """Build a snapshot solely from current-session persisted index ticks.

    Missing analytical features remain explicit.  No values are defaulted to zero.
    """
    now = float(now_epoch) if now_epoch is not None else datetime.now(timezone.utc).timestamp()
    conn = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True, timeout=1.0)
    try:
        symbols: dict[str, dict[str, Any]] = {}
        max_input = None
        for symbol, token in DEFAULT_INDEX_TOKENS.items():
            latest = conn.execute(
                "SELECT last_price, volume, timestamp_epoch FROM ticks "
                "WHERE instrument_token=? AND timestamp_epoch IS NOT NULL "
                "AND timestamp_epoch <= ? ORDER BY timestamp_epoch DESC LIMIT 1",
                (token, now),
            ).fetchone()
            if latest is None:
                continue
            ts = float(latest[2])
            max_input = ts if max_input is None else max(max_input, ts)
            minute_rows = conn.execute(
                "SELECT last_price, volume, timestamp_epoch FROM ticks "
                "WHERE instrument_token=? AND timestamp_epoch >= ? "
                "AND timestamp_epoch <= ? ORDER BY timestamp_epoch ASC",
                (token, ts - 60.0, ts),
            ).fetchall()
            symbols[symbol] = {
                "spot": float(latest[0]), "ltp": float(latest[0]),
                "ohlc": _bar(minute_rows),
                "regime": {"trend": None, "volatility_state": None, "confidence": None},
                "cross_asset": {"available": False, "signals": {}},
                "option_chain_summary": {"atm_strike": None, "pcr": None, "max_pain": None, "chain_quality": None},
                "feed_health": {"underlying_quote_age_sec": max(0.0, now - ts), "option_quote_age_sec": None, "status": "LIVE"},
                "quote_truth": {"symbol": symbol, "ltp": float(latest[0]), "bid": None, "ask": None, "spread": None, "last_tick_ts": _iso(ts), "tick_age_seconds": max(0.0, now - ts), "quote_truth": "LTP_ONLY", "is_fresh": now - ts <= 10.0, "is_executable_quote": False, "source": "canonical_sqlite.ticks"},
                "_feature_availability": {"vwap": False, "volume": False, "option_surface": False},
            }
    finally:
        conn.close()
    if not symbols or max_input is None:
        raise RuntimeError("CANONICAL_MARKET_SNAPSHOT_INPUTS_UNAVAILABLE")
    feature_availability = {symbol: payload.pop("_feature_availability") for symbol, payload in symbols.items()}
    snapshot = build_market_snapshot(generated_at=_iso(now), market_open=True, symbols_payload=symbols, warnings=["option_surface_unavailable", "cross_asset_unavailable"], loop_id=session_id)
    snapshot["producer_meta"].update({"session_id": session_id, "session_date": session_date, "source_sha": source_sha, "max_input_timestamp": _iso(max_input), "input_sources": [str(Path(db_path).resolve())], "causal_cutoff": _iso(max_input), "feature_availability": feature_availability, "vwap_status": "UNAVAILABLE_UNTRUSTWORTHY_VOLUME"})
    ok, errors = validate_market_snapshot(snapshot)
    if not ok:
        raise ValueError("CANONICAL_MARKET_SNAPSHOT_INVALID:" + "|".join(errors))
    write_market_snapshot_atomic(snapshot, output_path)
    return snapshot
