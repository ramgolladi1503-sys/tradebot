#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from config import config as cfg
from core.feed_debug import get_feed_debug
from core.freshness_sla import get_freshness_status
from core.kite_client import kite_client
from core.kite_depth_ws import build_subscription_tokens
from core.paths import data_root
from strategies.trade_builder import TradeBuilder


class _ExecStub:
    def spread_ok(self, bid, ask, price, **_kwargs):
        try:
            bid_f = float(bid)
            ask_f = float(ask)
            px_f = float(price)
        except Exception:
            return False
        if px_f <= 0 or ask_f < bid_f:
            return False
        return ((ask_f - bid_f) / px_f) <= float(
            getattr(cfg, "EXPIRY_LOTTO_MAX_SPREAD_PCT", 0.35)
        )

    def estimate_slippage(self, *_args, **_kwargs):
        return 0.0


def _synthetic_chain(atm: float, step: float, opt_type: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for offset in (-3, -2, -1, 0, 1, 2, 3):
        strike = float(atm + (offset * step))
        base = max(20.0, 100.0 - abs(offset) * 8.0)
        rows.append(
            {
                "type": str(opt_type).upper(),
                "strike": strike,
                "ltp": base,
                "bid": round(base * 0.98, 2),
                "ask": round(base * 1.02, 2),
                "volume": 1000,
                "instrument_token": int(strike * 10),
                "tradingsymbol": f"NIFTY-{int(strike)}-{opt_type}",
            }
        )
    return rows


def _build_synthetic_lotto_candidates(symbol: str = "NIFTY") -> int:
    cfg_prev = {
        "EXPIRY_LOTTO_MODE": getattr(cfg, "EXPIRY_LOTTO_MODE", False),
        "EXPIRY_LOTTO_REQUIRE_TREND_CONFIRM": getattr(
            cfg, "EXPIRY_LOTTO_REQUIRE_TREND_CONFIRM", True
        ),
        "EXPIRY_LOTTO_TARGET_CANDIDATES": getattr(
            cfg, "EXPIRY_LOTTO_TARGET_CANDIDATES", 4
        ),
        "EXPIRY_LOTTO_MIN_OPTION_TOKENS": getattr(
            cfg, "EXPIRY_LOTTO_MIN_OPTION_TOKENS", 12
        ),
    }
    cfg.EXPIRY_LOTTO_MODE = True
    cfg.EXPIRY_LOTTO_REQUIRE_TREND_CONFIRM = False
    cfg.EXPIRY_LOTTO_TARGET_CANDIDATES = 4
    cfg.EXPIRY_LOTTO_MIN_OPTION_TOKENS = 4
    builder = TradeBuilder(predictor=object(), execution=_ExecStub())
    builder._resolve_option_contract = (
        lambda sym, strike, opt_type, expiry, market_data: {
            "expiry": "2026-03-02",
            "tradingsymbol": f"{sym}-2026-03-02-{int(float(strike))}-{opt_type}",
            "instrument_token": int(float(strike) * 10),
        }
    )
    builder._identity_fields = lambda sym, instrument, expiry, strike, right, qty_lots: (
        "OPT",
        f"{sym}|{expiry}|{strike}|{right}",
        50,
        None,
    )
    builder.trade_intent_flags = lambda *args, **kwargs: {
        "tradable": True,
        "tradable_reasons_blocking": [],
        "planning_only": True,
        "execution_allowed": False,
        "execution_reason": "EXPIRY_LOTTO_MODE",
        "source_flags": {},
    }
    symbol_u = str(symbol or "NIFTY").upper()
    step = float(
        (getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {}) or {}).get(
            symbol_u, getattr(cfg, "STRIKE_STEP", 50)
        )
    )
    atm = (
        24700.0
        if symbol_u == "NIFTY"
        else (59600.0 if symbol_u == "BANKNIFTY" else 80000.0)
    )
    chain = _synthetic_chain(atm=atm, step=step, opt_type="CE") + _synthetic_chain(
        atm=atm, step=step, opt_type="PE"
    )
    market_data = {
        "symbol": symbol_u,
        "ltp": atm + 5.0,
        "atr": max(100.0, atm * 0.004),
        "ltp_change_window": 35.0,
        "day_type": "EXPIRY_DAY",
        "trend_state": "UP",
        "orb_bias": "UP",
        "option_chain": chain,
        "market_open": True,
    }
    try:
        out = builder.build_expiry_lotto_candidates(market_data, debug_reasons=True)
        return len(out or [])
    finally:
        for key, value in cfg_prev.items():
            setattr(cfg, key, value)


def _derivative_cache_stats() -> dict[str, int]:
    cache_path = Path(data_root()) / "kite_instruments.json"
    if not cache_path.exists():
        return {
            "cache_exists": 0,
            "nfo_rows": 0,
            "bfo_rows": 0,
            "nfo_opt_rows": 0,
            "bfo_opt_rows": 0,
        }
    try:
        raw = json.loads(cache_path.read_text())
    except Exception:
        return {
            "cache_exists": 1,
            "nfo_rows": 0,
            "bfo_rows": 0,
            "nfo_opt_rows": 0,
            "bfo_opt_rows": 0,
        }
    rows: list[dict[str, Any]]
    if isinstance(raw, dict):
        all_rows = raw.get("ALL")
        rows = list(all_rows) if isinstance(all_rows, list) else []
    elif isinstance(raw, list):
        rows = list(raw)
    else:
        rows = []
    nfo_rows = 0
    bfo_rows = 0
    nfo_opt_rows = 0
    bfo_opt_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        exchange = str(row.get("exchange") or "").upper()
        segment = str(row.get("segment") or "").upper()
        bucket = exchange if exchange in {"NFO", "BFO"} else segment.split("-", 1)[0]
        if bucket == "NFO":
            nfo_rows += 1
            if segment == "NFO-OPT":
                nfo_opt_rows += 1
        elif bucket == "BFO":
            bfo_rows += 1
            if segment == "BFO-OPT":
                bfo_opt_rows += 1
    return {
        "cache_exists": 1,
        "nfo_rows": int(nfo_rows),
        "bfo_rows": int(bfo_rows),
        "nfo_opt_rows": int(nfo_opt_rows),
        "bfo_opt_rows": int(bfo_opt_rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify option feed/token/lotto pipeline health."
    )
    parser.add_argument("--symbols", default="NIFTY,BANKNIFTY,SENSEX")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in str(args.symbols).split(",") if s.strip()]
    errors: list[str] = []

    resolution = []
    build_attempts = 0
    build_exception = None
    max_attempts = max(1, int(getattr(cfg, "OPTION_PIPELINE_HEALTH_RETRIES", 3)))
    for attempt in range(1, max_attempts + 1):
        build_attempts = attempt
        try:
            _tokens, resolution = build_subscription_tokens(
                symbols=symbols,
                max_tokens=int(getattr(cfg, "DEPTH_SUBSCRIPTION_MAX_TOKENS", 150)),
            )
            option_total = sum(
                int((row or {}).get("option_count") or 0)
                for row in resolution
                if isinstance(row, dict)
            )
            if option_total > 0:
                break
        except Exception as exc:
            build_exception = exc
            resolution = []
        # Warm instrument cache for both option exchanges before retrying.
        try:
            kite_client.instruments_cached("NFO", ttl_sec=0)
            kite_client.instruments_cached("BFO", ttl_sec=0)
            kite_client.instruments_cached(None, ttl_sec=0)
        except Exception:
            pass
        if attempt < max_attempts:
            time.sleep(0.35)
    if build_exception is not None and not resolution:
        errors.append(
            f"subscription_build_failed:{type(build_exception).__name__}:{build_exception}"
        )

    feed_debug = get_feed_debug()
    freshness = get_freshness_status(force=True)
    lotto_candidates = _build_synthetic_lotto_candidates(
        symbol=symbols[0] if symbols else "NIFTY"
    )
    cache_stats = _derivative_cache_stats()

    resolved_option_tokens_count = int(
        sum(
            int((row or {}).get("option_count") or 0)
            for row in resolution
            if isinstance(row, dict)
        )
    )
    live_option_tokens_count = int(resolved_option_tokens_count)
    live_option_tokens_source = "subscription_resolution"
    if live_option_tokens_count <= 0:
        recent_tokens = int(feed_debug.get("distinct_tokens_recent") or 0)
        inferred_recent_option_tokens = max(0, recent_tokens - len(symbols))
        if inferred_recent_option_tokens > 0:
            live_option_tokens_count = inferred_recent_option_tokens
            live_option_tokens_source = "recent_tick_activity"
    if live_option_tokens_count <= 0:
        subscribed_tokens_count = int(feed_debug.get("subscribed_tokens_count") or 0)
        intended_tokens_count = int(feed_debug.get("intended_tokens_count") or 0)
        inferred_runtime_option_tokens = max(
            0, max(subscribed_tokens_count, intended_tokens_count) - len(symbols)
        )
        if inferred_runtime_option_tokens > 0:
            live_option_tokens_count = inferred_runtime_option_tokens
            live_option_tokens_source = "runtime_subscription_counts"

    ws_connected = feed_debug.get("ws_connected")
    max_tick_age = feed_debug.get("last_db_tick_age_sec")
    if max_tick_age is None:
        max_tick_age = (freshness.get("ltp") or {}).get("age_sec")

    min_option_tokens = int(getattr(cfg, "MIN_OPTION_TOKENS", 12))
    if resolved_option_tokens_count < min_option_tokens:
        errors.append(
            f"resolved_option_tokens_under_min:{resolved_option_tokens_count}<{min_option_tokens}"
        )
    fail_reasons = sorted(
        {
            str((row or {}).get("option_fail_reason") or "").strip()
            for row in resolution
            if isinstance(row, dict) and (row or {}).get("option_fail_reason")
        }
    )
    if fail_reasons:
        errors.append(f"resolution_fail_reasons:{','.join(fail_reasons)}")
    if live_option_tokens_count < min_option_tokens:
        errors.append(
            f"live_option_tokens_under_min:{live_option_tokens_count}<{min_option_tokens}"
        )
    if ws_connected is False:
        errors.append("ws_disconnected")
    if args.strict and (ws_connected is None):
        errors.append("ws_status_unknown")
    if (
        cache_stats.get("cache_exists")
        and (cache_stats.get("nfo_opt_rows", 0) + cache_stats.get("bfo_opt_rows", 0))
        <= 0
    ):
        errors.append("derivative_cache_empty:nfo_bfo_opt_rows=0")
    if lotto_candidates < 3:
        errors.append(f"lotto_candidates_under_min:{lotto_candidates}<3")

    payload = {
        "symbols": symbols,
        "ws_connected": ws_connected,
        "live_option_tokens_count": live_option_tokens_count,
        "live_option_tokens_source": live_option_tokens_source,
        "resolved_option_tokens_count": int(resolved_option_tokens_count),
        "max_tick_age_sec": max_tick_age,
        "lotto_candidates_count": int(lotto_candidates),
        "derivative_cache_stats": cache_stats,
        "build_attempts": int(build_attempts),
        "resolution_summary": [
            {
                "symbol": str((row or {}).get("symbol") or ""),
                "expiry": str((row or {}).get("expiry") or ""),
                "count": int((row or {}).get("count") or 0),
                "option_count": int((row or {}).get("option_count") or 0),
                "option_fail_reason": (row or {}).get("option_fail_reason"),
                "ltp_source": (row or {}).get("ltp_source"),
                "atm": (row or {}).get("atm"),
            }
            for row in resolution
            if isinstance(row, dict)
        ],
        "feed_runtime_state": feed_debug.get("feed_runtime_state"),
        "subscribed_tokens_count": feed_debug.get("subscribed_tokens_count"),
        "intended_tokens_count": feed_debug.get("intended_tokens_count"),
        "errors": errors,
    }
    print(json.dumps(payload, indent=2, default=str))

    if args.strict and errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
