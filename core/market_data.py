# core/market_data.py
# Migration note:
# Runtime mode and quote strictness now flow through core.market_context.derive_market_context.

import os
import json
import time
import math
import logging
import sqlite3
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone
from datetime import datetime, timedelta
from config import config as cfg
from config.profile import get_runtime_profile
from core.option_chain import fetch_option_chain as fetch_option_chain_impl
from core.option_liquidity_cache import hydrate_option_liquidity_fields, update_option_liquidity_cache
from core.regime_prob_model import RegimeProbModel
from core.news_shock_encoder import NewsShockEncoder
from core.news_encoder import NewsEncoder
from core.news_calendar import NewsCalendar
from core.cross_asset import CrossAsset
from core.ohlc_buffer import ohlc_buffer
from core.indicators_live import compute_indicators
from core.filters import get_bias
from core.depth_store import depth_store
from core.market_context import coerce_segment_for_market_context, derive_market_context
from core.regime_session_context import resolve_canonical_session_context
from core.paths import logs_dir
from core.time_utils import (
    compute_age_sec,
    is_market_open_ist,
    normalize_epoch_seconds,
    parse_ts_ist,
    now_ist,
    now_utc_epoch,
)
from core.session_calendar import get_session, minutes_since_open as session_minutes_since_open, is_open
from core.time_sanity import check_market_data_time_sanity
from core.day_type_history import append_day_type_event
from core.auth_manager import is_auth_error

from core.kite_client import kite_client

try:
    from modules.real_time_indicators import calculate_vwap, calculate_atr, calculate_orb
except Exception:
    calculate_vwap = calculate_atr = calculate_orb = None

from collections import deque
from pathlib import Path

_DATA_CACHE = {}
_SYMBOL_TO_TOKEN_CACHE = {}

_INDEX_TRADINGSYMBOL_ALIASES = {
    "NIFTY": ("NIFTY", "NIFTY 50"),
    "BANKNIFTY": ("BANKNIFTY", "NIFTY BANK"),
    "SENSEX": ("SENSEX",),
}

def get_token_for_symbol(symbol: str) -> int | None:
    sym = symbol.upper()
    if sym in _SYMBOL_TO_TOKEN_CACHE:
        return _SYMBOL_TO_TOKEN_CACHE[sym]
    configured_token = (getattr(cfg, "INDEX_TOKEN_BY_SYMBOL", {}) or {}).get(sym)
    try:
        configured_token_int = int(configured_token or 0)
    except Exception:
        configured_token_int = 0
    if configured_token_int > 0:
        _SYMBOL_TO_TOKEN_CACHE[sym] = configured_token_int
        return configured_token_int
    try:
        instruments = kite_client.instruments() or []
        # Build the entire cache once
        for i in instruments:
            tsym = i.get("tradingsymbol")
            if tsym:
                token = int(i.get("instrument_token"))
                _SYMBOL_TO_TOKEN_CACHE[tsym] = token
                for alias, tradingsymbols in _INDEX_TRADINGSYMBOL_ALIASES.items():
                    if tsym in tradingsymbols:
                        _SYMBOL_TO_TOKEN_CACHE.setdefault(alias, token)
        if sym in _SYMBOL_TO_TOKEN_CACHE:
            return _SYMBOL_TO_TOKEN_CACHE[sym]
    except Exception:
        pass
    _SYMBOL_TO_TOKEN_CACHE[sym] = None
    return None

_LTP_HISTORY = {}
_DAYTYPE_LOCK = {}
_DAYTYPE_CONF_HISTORY = {}
_DAYTYPE_LAST = {}
_DAYTYPE_LAST_DAY = {}
_DAYTYPE_ALERT_TS = {}
_DAYTYPE_LAST_LOG = {}
_ORB_STATE = {}
# Backward-compatible alias for legacy tests and callers that still clear/read
# `_OPEN_RANGE`. ORB tracking is now candle-based, but aliasing preserves behavior.
_OPEN_RANGE = _ORB_STATE
_LAST_GOOD_LTP = {}
_REGIME_LAST_PRIMARY = {}
_REGIME_TRANSITIONS = {}
_LAST_REGIME_SNAPSHOT = {}
_INDICATOR_LAST_UPDATE_EPOCH = {}
_INSUFFICIENT_OHLC_WARNED = set()
_INDEX_REST_QUOTE_REFRESH_TS = {}
_INDEX_QUOTE_REQUEST_LOG_TS = {}
_LIVE_QUOTE_ERROR_LAST_TS = {}
_INDEX_REST_QUOTE_EXECUTOR: ThreadPoolExecutor | None = None
_INDEX_REST_QUOTE_INFLIGHT: set[str] = set()

_REGIME_MODEL = None
_NEWS_ENCODER = None
_NEWS_CAL = None
_NEWS_TEXT = None
_CROSS_ASSET = None
_STARTUP_WARMUP_DONE = False
_STARTUP_WARMUP_ROWS = []
_WARMUP_SEED_ATTEMPTS = {}
_WARMUP_SEED_DETAILS = {}
logger = logging.getLogger(__name__)


def _index_rest_quote_executor() -> ThreadPoolExecutor:
    global _INDEX_REST_QUOTE_EXECUTOR
    if _INDEX_REST_QUOTE_EXECUTOR is None:
        max_workers = int(getattr(cfg, "INDEX_REST_QUOTE_REFRESH_ASYNC_MAX_WORKERS", 1) or 1)
        # Keep this tiny. Purpose is to avoid blocking LIVE decision loop on REST.
        _INDEX_REST_QUOTE_EXECUTOR = ThreadPoolExecutor(max_workers=max(1, min(4, max_workers)))
    return _INDEX_REST_QUOTE_EXECUTOR


def _resolve_market_session_bucket(*, segment: str | None, **row: object) -> str:
    timestamp_keys = ("timestamp_ist", "timestamp", "regime_ts", "quote_ts", "quote_ts_epoch", "ltp_ts_epoch", "candle_ts_epoch")
    for key in timestamp_keys:
        value = row.get(key)
        if value is None or value == "":
            continue
        context = resolve_canonical_session_context(
            value,
            segment=segment,
            is_expiry_day=bool(row.get("is_expiry_day")),
            is_event_mode=bool(row.get("is_event_mode")),
        )
        return context.canonical_session_bucket
    return "DEFAULT"


def _coerce_event_timestamp(value: object) -> str | None:
    if value is None or value == "":
        return None
    epoch = normalize_epoch_seconds(value)
    if epoch is not None:
        try:
            return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()
        except Exception:
            return None
    dt = parse_ts_ist(value)
    if dt is not None:
        try:
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return None


def resolve_regime_event_timestamp(
    *,
    explicit_timestamp: object | None = None,
    source_timestamp: object | None = None,
    last_bar_timestamp: object | None = None,
    replay_timestamp: object | None = None,
) -> tuple[str | None, str]:
    candidates = (
        ("CANONICAL_EVENT_TIME", explicit_timestamp),
        ("SOURCE_TICK_TIME", source_timestamp),
        ("LAST_BAR_TIME", last_bar_timestamp),
        ("REPLAY_TIMESTAMP", replay_timestamp),
    )
    for source, candidate in candidates:
        ts = _coerce_event_timestamp(candidate)
        if ts is not None:
            return ts, source
    return None, "MISSING_TIMESTAMP"

# -------------------------------
# Market Data Functions
# -------------------------------


def _indicator_freshness_status(
    required_inputs_ok: bool,
    last_update_epoch: float | None,
    stale_sec: float | None = None,
    now_epoch: float | None = None,
    never_computed_age_sec: float | None = None,
):
    """
    Indicator freshness is based on last successful indicator update time.
    """
    now_epoch = float(now_epoch if now_epoch is not None else now_utc_epoch())
    stale_limit = float(stale_sec if stale_sec is not None else getattr(cfg, "INDICATOR_STALE_SEC", 120))
    never_age = float(
        never_computed_age_sec
        if never_computed_age_sec is not None
        else getattr(cfg, "INDICATORS_NEVER_COMPUTED_AGE_SEC", 1e9)
    )
    never_computed = not isinstance(last_update_epoch, (int, float))
    if never_computed:
        age_sec = max(never_age, stale_limit + 1.0)
    else:
        computed_age = compute_age_sec(last_update_epoch, now_epoch)
        age_sec = float(computed_age if computed_age is not None else max(never_age, stale_limit + 1.0))
    stale = age_sec > stale_limit
    ok = bool(required_inputs_ok) and (not never_computed) and (not stale)
    reason = "indicators_never_computed" if never_computed else ("indicators_stale" if stale else None)
    return {"age_sec": age_sec, "stale": stale, "ok": ok, "never_computed": never_computed, "reason": reason}


def _as_bar_float(value):
    try:
        val = float(value)
    except Exception:
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val


def _orb_state_from_candles(
    symbol: str,
    bars: list[dict] | None,
    *,
    now_dt: datetime,
    segment: str,
    market_open: bool,
    market_mode: str | None = None,
) -> dict:
    """
    Candle-based ORB state:
    - PENDING until the first ORB_WINDOW_MIN one-minute candles are available.
    - UP/DOWN only when a post-window candle closes beyond ORB range + buffer.
    - NEUTRAL otherwise.
    """
    if market_mode is None:
        window_min = int(getattr(cfg, "ORB_WINDOW_MIN", getattr(cfg, "ORB_LOCK_MIN", 15)))
    else:
        profile_mode = "LIVE" if str(market_mode).upper() == "LIVE" else ("PAPER" if str(market_mode).upper() == "PAPER" else "SIM")
        profile = get_runtime_profile(mode=profile_mode)
        profile_window = int(getattr(profile, "orb_candle_minutes", 0))
        if profile_window > 0:
            window_min = profile_window
        else:
            window_min = int(getattr(cfg, f"ORB_CANDLE_MINUTES_{profile_mode}", profile_window))
    window_min = max(0, int(window_min))
    break_buffer_pct = max(0.0, float(getattr(cfg, "ORB_BREAK_BUFFER_PCT", 0.0005)))
    sess = get_session(segment)
    now_local = now_dt.astimezone(sess.tz)
    day_key = now_local.date().isoformat()
    prev = dict(_ORB_STATE.get(symbol) or {})
    if str(prev.get("day_key")) != day_key:
        prev = {}

    open_dt = now_local.replace(
        hour=sess.open_time.hour,
        minute=sess.open_time.minute,
        second=0,
        microsecond=0,
    )
    window_end_dt = open_dt + timedelta(minutes=max(0, int(window_min)))

    session_bars: list[dict] = []
    for bar in list(bars or []):
        ts = bar.get("ts")
        if not hasattr(ts, "astimezone"):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=sess.tz)
        ts_local = ts.astimezone(sess.tz)
        if ts_local.date() != now_local.date():
            continue
        if ts_local < open_dt:
            continue
        if ts_local > now_local:
            continue
        row = dict(bar)
        row["ts_local"] = ts_local
        session_bars.append(row)
    session_bars.sort(key=lambda row: row.get("ts_local"))

    if window_min <= 0:
        state = {
            "symbol": symbol,
            "day_key": day_key,
            "window_min": 0,
            "required_bars": 0,
            "window_bars": 0,
            "session_bars": int(len(session_bars)),
            "open_ts": open_dt.isoformat(),
            "window_end_ts": window_end_dt.isoformat(),
            "orb_high": None,
            "orb_low": None,
            "break_buffer_pct": break_buffer_pct,
            "bias": "NEUTRAL",
            "status": "DISABLED",
            "ts_epoch": now_utc_epoch(),
            "ts_ist": now_ist().isoformat(),
        }
        _ORB_STATE[symbol] = dict(state)
        return state

    window_bars = [row for row in session_bars if row.get("ts_local") < window_end_dt]
    required_bars = int(window_min)
    orb_high = None
    orb_low = None
    if len(window_bars) >= required_bars:
        highs = [_as_bar_float(row.get("high")) for row in window_bars]
        lows = [_as_bar_float(row.get("low")) for row in window_bars]
        highs = [v for v in highs if v is not None]
        lows = [v for v in lows if v is not None]
        if highs and lows:
            orb_high = max(highs)
            orb_low = min(lows)
    if orb_high is None:
        orb_high = _as_bar_float(prev.get("orb_high"))
    if orb_low is None:
        orb_low = _as_bar_float(prev.get("orb_low"))

    if orb_high is None or orb_low is None:
        bias = "PENDING" if market_open else "NEUTRAL"
    else:
        bias = "NEUTRAL"
        post_bars = [row for row in session_bars if row.get("ts_local") >= window_end_dt]
        for row in post_bars:
            close_val = _as_bar_float(row.get("close"))
            if close_val is None:
                continue
            if close_val > (orb_high * (1.0 + break_buffer_pct)):
                bias = "UP"
            elif close_val < (orb_low * (1.0 - break_buffer_pct)):
                bias = "DOWN"
            else:
                bias = "NEUTRAL"

    state = {
        "symbol": symbol,
        "day_key": day_key,
        "window_min": int(window_min),
        "required_bars": int(required_bars),
        "window_bars": int(len(window_bars)),
        "session_bars": int(len(session_bars)),
        "open_ts": open_dt.isoformat(),
        "window_end_ts": window_end_dt.isoformat(),
        "orb_high": orb_high,
        "orb_low": orb_low,
        "break_buffer_pct": break_buffer_pct,
        "bias": str(bias),
        "status": "READY" if bias != "PENDING" else "PENDING",
        "ts_epoch": now_utc_epoch(),
        "ts_ist": now_ist().isoformat(),
    }
    _ORB_STATE[symbol] = dict(state)
    return state


def _should_require_live_ltp(
    execution_mode: str | None = None,
    require_live_quotes: bool | None = None,
    snapshot: dict | None = None,
) -> bool:
    return _effective_require_live_quotes(
        snapshot,
        require_live_quotes=require_live_quotes,
        execution_mode=execution_mode,
    )


def _effective_require_live_quotes(
    snapshot: dict | None = None,
    *,
    require_live_quotes: bool | None = None,
    execution_mode: str | None = None,
) -> bool:
    base = dict(snapshot or {})
    if execution_mode is not None:
        base["execution_mode"] = execution_mode
    explicit_market_open = "market_open" in base
    mode_hint = str(
        base.get("execution_mode")
        or getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))
    ).upper()
    if require_live_quotes is False:
        # Backward compatibility for helper-only callers that pass LIVE mode without market-open context.
        if mode_hint == "LIVE" and not explicit_market_open:
            return True
        return False
    ctx = derive_market_context(base)
    if mode_hint == "LIVE" and not explicit_market_open:
        return True
    if require_live_quotes is True:
        return bool(ctx.require_live_quotes)
    configured = bool(getattr(cfg, "REQUIRE_LIVE_QUOTES", True))
    return bool(configured and ctx.require_live_quotes)


def _apply_indicator_quote_policy(
    indicators_ok: bool,
    ltp,
    ltp_source: str | None,
    execution_mode: str | None = None,
    require_live_quotes: bool | None = None,
    snapshot: dict | None = None,
) -> bool:
    """
    Final indicator gate policy:
    - always require indicators_ok from indicator computation/freshness
    - always require positive LTP
    - require ltp_source=live only when LIVE mode OR REQUIRE_LIVE_QUOTES=true
    """
    if not bool(indicators_ok):
        return False
    try:
        if ltp is None or float(ltp) <= 0.0:
            return False
    except Exception:
        return False
    require_live_ltp = _should_require_live_ltp(
        execution_mode=execution_mode,
        require_live_quotes=require_live_quotes,
        snapshot=snapshot,
    )
    if require_live_ltp and str(ltp_source or "").lower() != "live":
        return False
    return True


def _is_finite_number(value) -> bool:
    try:
        v = float(value)
    except Exception:
        return False
    return math.isfinite(v)


def update_index_quote_snapshot(
    symbol: str,
    bid=None,
    ask=None,
    mid=None,
    ts_epoch: float | None = None,
    source: str = "ws",
    ltp=None,
    *,
    book_source: str | None = None,
    volume=None,
    last_price_source: str | None = None,
):
    """
    Update index quote cache from live sources (WS/REST) in a uniform structure:
      bid, ask, mid, ts_epoch, source, book_source, volume, last_price_source
    """
    sym = str(symbol or "").upper()
    if not sym:
        return
    ts = float(ts_epoch) if isinstance(ts_epoch, (int, float)) else now_utc_epoch()
    def _valid_price(value):
        try:
            p = float(value)
            if p > 0:
                return p
        except Exception:
            return None
        return None

    def _valid_nonnegative(value):
        try:
            resolved = float(value)
        except Exception:
            return None
        if not math.isfinite(resolved) or resolved < 0:
            return None
        return float(resolved)

    if mid is None and bid is not None and ask is not None:
        try:
            b = float(bid)
            a = float(ask)
            if b > 0 and a > 0:
                mid = (b + a) / 2.0
        except Exception:
            mid = None
    cache = _DATA_CACHE.setdefault(sym, {})
    prev = cache.get("index_quote") or {}
    try:
        prev_ts = float(prev.get("ts_epoch") or 0.0)
    except Exception:
        prev_ts = 0.0
    if prev_ts and ts < prev_ts:
        return
    resolved_bid = _valid_price(bid)
    if resolved_bid is None:
        resolved_bid = _valid_price(prev.get("bid"))
    resolved_ask = _valid_price(ask)
    if resolved_ask is None:
        resolved_ask = _valid_price(prev.get("ask"))
    resolved_last_price = _valid_price(ltp)
    if resolved_last_price is None:
        resolved_last_price = _valid_price(prev.get("last_price"))
    resolved_mid = _valid_price(mid)
    if resolved_mid is None and resolved_bid is not None and resolved_ask is not None:
        resolved_mid = (resolved_bid + resolved_ask) / 2.0
    if resolved_mid is None:
        resolved_mid = _valid_price(prev.get("mid"))
    resolved_volume = _valid_nonnegative(volume)
    if resolved_volume is None:
        resolved_volume = _valid_nonnegative(prev.get("volume"))
    resolved_book_source = str(book_source or prev.get("book_source") or "").strip() or None
    resolved_last_price_source = str(last_price_source or prev.get("last_price_source") or "").strip() or None
    snap = {
        "symbol": sym,
        "bid": resolved_bid,
        "ask": resolved_ask,
        "mid": resolved_mid,
        "last_price": resolved_last_price,
        "volume": resolved_volume,
        "ts_epoch": ts,
        "source": str(source or "unknown"),
        "book_source": resolved_book_source,
        "last_price_source": resolved_last_price_source,
    }
    cache["index_quote"] = snap
    if resolved_last_price is not None:
        cache["last_ltp"] = float(resolved_last_price)
        cache["ltp_source"] = "live"
        cache["ltp_ts_epoch"] = ts
    elif resolved_mid is not None:
        try:
            cache["last_ltp"] = float(resolved_mid)
            cache["ltp_source"] = "live"
            cache["ltp_ts_epoch"] = ts
        except Exception:
            pass


def get_index_quote_snapshot(symbol: str) -> dict:
    sym = str(symbol or "").upper()
    if not sym:
        return {}
    cached = dict((_DATA_CACHE.get(sym) or {}).get("index_quote") or {})
    use_sub = getattr(cfg, "DEPTH_WS_USE_SUBPROCESS", False) or getattr(cfg, "FEED_USE_SUBPROCESS", False)
    if use_sub or not cached:
        try:
            from core.tick_store import get_last_tick
            token = get_token_for_symbol(sym)
            if token:
                tick = get_last_tick(token)
                if tick and tick.get("ltp"):
                    return {
                        "last_price": tick.get("ltp"),
                        "ts_epoch": tick.get("ts_epoch"),
                        "source": "tick_store"
                    }
        except Exception:
            pass
    return cached


def _index_quote_keys(symbol: str) -> list[str]:
    sym = str(symbol or "").upper()
    canonical = {
        "NIFTY": "NSE:NIFTY 50",
        "BANKNIFTY": "NSE:NIFTY BANK",
        "SENSEX": "BSE:SENSEX",
    }.get(sym)
    primary = str((getattr(cfg, "PREMARKET_INDICES_LTP", {}) or {}).get(sym) or "").strip()
    aliases = {
        "NIFTY": ["NSE:NIFTY 50"],
        "BANKNIFTY": ["NSE:NIFTY BANK", "NSE:BANKNIFTY"],
        "SENSEX": ["BSE:SENSEX"],
    }.get(sym, [])
    keys = []
    if canonical:
        keys.append(canonical)
    # honor configured symbol only when it is already exchange-qualified.
    if primary and ":" in primary:
        keys.append(primary)
    keys.extend(aliases)
    deduped = []
    seen = set()
    for key in keys:
        k = str(key or "").strip()
        if not k or k in seen:
            continue
        seen.add(k)
        deduped.append(k)
    return deduped


def _log_index_quote_request(symbol: str, endpoint: str, requested_symbols: list[str]) -> None:
    sym = str(symbol or "").upper()
    symbols = [str(s).strip() for s in (requested_symbols or []) if str(s).strip()]
    if not sym or not symbols:
        return
    now_epoch = now_utc_epoch()
    key = f"{endpoint}:{sym}"
    min_interval = float(getattr(cfg, "INDEX_QUOTE_REQUEST_LOG_SEC", 60.0))
    last = float(_INDEX_QUOTE_REQUEST_LOG_TS.get(key) or 0.0)
    if last and (now_epoch - last) < min_interval:
        return
    _INDEX_QUOTE_REQUEST_LOG_TS[key] = now_epoch
    try:
        payload = {
            "event": "index_quote_request",
            "endpoint": str(endpoint),
            "symbol": sym,
            "requested_symbols": symbols,
            "ts_epoch": now_epoch,
            "ts_ist": now_ist().isoformat(),
        }
        p = logs_dir() / "index_quote_requests.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _is_index_symbol(symbol: str) -> bool:
    sym = str(symbol or "").upper()
    if not sym:
        return False
    configured = {
        str(k).upper()
        for k in (getattr(cfg, "PREMARKET_INDICES_LTP", {}) or {}).keys()
        if str(k or "").strip()
    }
    if configured:
        return sym in configured
    return sym in {"NIFTY", "BANKNIFTY", "SENSEX"}


def is_index(symbol: str) -> bool:
    """Public helper for consistent index classification."""
    return _is_index_symbol(symbol)


def _index_depth_required(
    symbol: str,
    *,
    execution_mode: str | None = None,
    market_open: bool | None = None,
) -> bool:
    if not is_index(symbol):
        return False
    effective_market_open = True if market_open is None else bool(market_open)
    ctx = derive_market_context(
        {"execution_mode": execution_mode, "market_open": effective_market_open}
    )
    if ctx.mode != "LIVE":
        return False
    return bool(getattr(cfg, "INDEX_REQUIRE_DEPTH_LIVE", False))


def _classify_index_feed_health(
    *,
    symbol: str,
    execution_mode: str | None,
    now_epoch: float,
    market_open: bool | None = None,
    ltp,
    ltp_ts_epoch,
    quote_ok: bool,
    quote_source: str | None,
    quote_ts_epoch,
) -> dict:
    """
    Canonical feed health for index underlyings:
    - STALE: LTP timestamp missing/old.
    - MISSING: bid/ask unavailable while LTP is fresh.
    - SIM/PAPER: missing depth does not become STALE and does not require depth.
    - LIVE: missing depth is MISSING (strict), not STALE.
    """
    effective_market_open = True if market_open is None else bool(market_open)
    ctx = derive_market_context(
        {"execution_mode": execution_mode, "market_open": effective_market_open}
    )
    offhours = bool(ctx.mode == "OFFHOURS")
    max_ltp_age = float(
        getattr(
            cfg,
            "OFFHOURS_SLA_MAX_LTP_AGE_SEC" if offhours else "SLA_MAX_LTP_AGE_SEC",
            900.0 if offhours else 2.5,
        )
    )
    max_depth_age = float(
        getattr(
            cfg,
            "OFFHOURS_SLA_MAX_DEPTH_AGE_SEC" if offhours else "SLA_MAX_DEPTH_AGE_SEC",
            900.0 if offhours else 6.0,
        )
    )

    ltp_age_sec = compute_age_sec(ltp_ts_epoch, now_epoch)
    depth_age_sec = compute_age_sec(quote_ts_epoch, now_epoch)

    stale_reasons = []
    missing_reasons = []
    if ltp is None or float(ltp) <= 0:
        stale_reasons.append("ltp_missing")
    elif ltp_age_sec is None:
        stale_reasons.append("ltp_timestamp_missing")
    elif float(ltp_age_sec) > max_ltp_age:
        stale_reasons.append(f"ltp_stale age={float(ltp_age_sec):.2f} max={max_ltp_age:.2f}")

    depth_required = _index_depth_required(
        symbol,
        execution_mode=execution_mode,
        market_open=effective_market_open,
    )
    if not bool(quote_ok):
        missing_reasons.append("depth_missing")
        missing_reasons.append(str(quote_source or "missing_depth"))

    if offhours:
        state = "OFFHOURS"
        feed_ok = True
    else:
        if stale_reasons:
            state = "STALE"
        elif missing_reasons:
            state = "MISSING"
        else:
            state = "OK"
        if state == "MISSING" and not depth_required:
            feed_ok = True
        else:
            feed_ok = state == "OK"

    return {
        "state": state,
        "ok": bool(feed_ok),
        "offhours_mode": bool(offhours),
        "ltp_age_sec": ltp_age_sec,
        "depth_age_sec": depth_age_sec,
        "max_ltp_age_sec": max_ltp_age,
        "max_depth_age_sec": max_depth_age,
        "depth_required": bool(depth_required),
        "stale_reasons": stale_reasons,
        "missing_reasons": missing_reasons,
        "source": str(quote_source or "none"),
    }


def _synthesize_index_bid_ask(
    mid_price,
    *,
    spread_bps: float | None = None,
) -> tuple[float | None, float | None, float | None]:
    try:
        mid = float(mid_price)
        if mid <= 0:
            return None, None, None
        if spread_bps is not None:
            spread = float(mid) * (abs(float(spread_bps)) / 10000.0)
            spread = max(spread, float(getattr(cfg, "INDEX_SYNTH_MIN_TICK", 0.05)))
        else:
            spread = max(
                float(mid) * float(getattr(cfg, "SYNTH_INDEX_SPREAD_PCT", 0.00005)),
                float(getattr(cfg, "SYNTH_INDEX_SPREAD_ABS", 0.5)),
            )
        spread_cap = float(getattr(cfg, "SYNTH_INDEX_SPREAD_CAP", 5.0))
        spread = min(spread, spread_cap)
        half = spread / 2.0
        bid = round(mid - half, 4)
        ask = round(mid + half, 4)
        return bid, ask, mid
    except Exception:
        return None, None, None


def resolve_index_quote(
    symbol: str,
    mode: str,
    ltp,
    depth,
    *,
    market_open: bool | None = None,
    ltp_age_sec: float | None = None,
    market_context: dict | None = None,
) -> dict:
    """
    Resolve index quote in a single deterministic path.

    Returns:
      {
        "bid": float|None,
        "ask": float|None,
        "mid": float|None,
        "quote_ok": bool,
        "quote_source": "depth" | "synthetic_index" | "missing_depth",
      }
    """

    def _as_price(value):
        try:
            p = float(value)
            if p > 0:
                return p
        except Exception:
            return None
        return None

    bid = None
    ask = None
    if isinstance(depth, dict):
        bid = _as_price(depth.get("bid"))
        ask = _as_price(depth.get("ask"))
        if bid is None or ask is None:
            try:
                buy_book = depth.get("buy") if isinstance(depth.get("buy"), list) else []
                sell_book = depth.get("sell") if isinstance(depth.get("sell"), list) else []
                b0 = buy_book[0].get("price") if buy_book else None
                a0 = sell_book[0].get("price") if sell_book else None
                bid = _as_price(b0) if bid is None else bid
                ask = _as_price(a0) if ask is None else ask
            except Exception:
                pass

    if bid is not None and ask is not None and ask >= bid:
        return {
            "bid": bid,
            "ask": ask,
            "mid": (bid + ask) / 2.0,
            "quote_ok": True,
            "quote_source": "depth",
        }

    ctx_payload = dict(market_context or {})
    if "execution_mode" not in ctx_payload:
        ctx_payload["execution_mode"] = mode
    if market_open is not None and "market_open" not in ctx_payload:
        ctx_payload["market_open"] = market_open
    ctx = derive_market_context(ctx_payload)
    depth_required = _index_depth_required(
        symbol,
        execution_mode=mode,
        market_open=ctx.is_market_open,
    )

    if is_index(symbol):
        ltp_price = _as_price(ltp)
        if ltp_price is None:
            return {
                "bid": None,
                "ask": None,
                "mid": None,
                "quote_ok": False,
                "quote_source": "missing_ltp" if ctx.require_live_quotes else "missing_depth",
            }

        max_ltp_age = float(
            getattr(
                cfg,
                "MAX_LTP_AGE_SEC" if ctx.mode == "LIVE" else "OFFHOURS_MAX_LTP_AGE_SEC",
                8.0 if ctx.mode == "LIVE" else 3600.0,
            )
        )
        if ltp_age_sec is None:
            age_ok = not ctx.require_live_quotes
        else:
            age_ok = float(max(0.0, ltp_age_sec)) <= max_ltp_age
        if not age_ok:
            return {
                "bid": None,
                "ask": None,
                "mid": None,
                "quote_ok": False,
                "quote_source": "stale_ltp",
            }
        if depth_required:
            return {
                "bid": None,
                "ask": None,
                "mid": None,
                "quote_ok": False,
                "quote_source": "missing_depth",
            }
        spread_bps = float(
            getattr(
                cfg,
                "INDEX_SYNTH_SPREAD_BPS_LIVE" if ctx.mode == "LIVE" else "OFFHOURS_SYNTH_INDEX_SPREAD_BPS",
                5.0 if ctx.mode == "LIVE" else 20.0,
            )
        )
        synth_bid, synth_ask, synth_mid = _synthesize_index_bid_ask(ltp_price, spread_bps=spread_bps)
        if synth_bid is not None and synth_ask is not None and synth_mid is not None:
            return {
                "bid": synth_bid,
                "ask": synth_ask,
                "mid": synth_mid,
                "quote_ok": True,
                "quote_source": "synthetic_index",
            }

    return {
        "bid": None,
        "ask": None,
        "mid": None,
        "quote_ok": False,
        "quote_source": "missing_depth",
    }


def _extract_quote_epoch(raw_ts, fallback_epoch: float) -> float:
    normalized = normalize_epoch_seconds(raw_ts)
    if normalized is not None:
        return float(normalized)
    return float(fallback_epoch)


def _refresh_index_quote_from_rest(symbol: str, force: bool = False) -> bool:
    """
    Populate index bid/ask from REST quote API when WS depth is absent.
    Returns True when bid/ask is present in cache after refresh attempt.
    """
    sym = str(symbol or "").upper()
    if not sym:
        return False
    now_epoch = now_utc_epoch()
    min_interval = float(getattr(cfg, "INDEX_REST_QUOTE_REFRESH_SEC", 5.0))
    snap = get_index_quote_snapshot(sym)
    has_cached_bidask = bool(snap.get("bid") is not None and snap.get("ask") is not None)
    snap_ts = snap.get("ts_epoch")
    snap_age = compute_age_sec(snap_ts, now_epoch)
    if snap_age is None:
        snap_age = float("inf")
    if (not force) and has_cached_bidask and snap_age <= min_interval:
        return True
    last_refresh = float(_INDEX_REST_QUOTE_REFRESH_TS.get(sym) or 0.0)
    last_refresh_age = compute_age_sec(last_refresh, now_epoch)
    if (not force) and last_refresh and last_refresh_age is not None and last_refresh_age < min_interval:
        return has_cached_bidask
    if not bool(getattr(cfg, "KITE_USE_API", True)):
        return has_cached_bidask

    # In LIVE, never block the decision loop on REST quote refresh. WS depth/ltp + synthetic index quotes
    # are sufficient for gating; REST is best-effort to improve bid/ask quality.
    if (not force) and bool(getattr(cfg, "INDEX_REST_QUOTE_REFRESH_ASYNC", True)):
        sym_key = sym
        if sym_key not in _INDEX_REST_QUOTE_INFLIGHT:
            _INDEX_REST_QUOTE_INFLIGHT.add(sym_key)

            def _task() -> None:
                try:
                    _refresh_index_quote_from_rest(sym_key, force=True)
                finally:
                    _INDEX_REST_QUOTE_INFLIGHT.discard(sym_key)

            try:
                _index_rest_quote_executor().submit(_task)
            except Exception:
                _INDEX_REST_QUOTE_INFLIGHT.discard(sym_key)
        return has_cached_bidask
    try:
        kite_client.ensure()
    except Exception:
        return has_cached_bidask
    if not kite_client.kite:
        return has_cached_bidask
    _INDEX_REST_QUOTE_REFRESH_TS[sym] = now_epoch
    request_keys = _index_quote_keys(sym)
    _log_index_quote_request(sym, "quote", request_keys)
    for key in request_keys:
        try:
            payload = kite_client.kite.quote([key]) or {}
            q = payload.get(key) or {}
            depth = q.get("depth") or {}
            buy_book = depth.get("buy") or []
            sell_book = depth.get("sell") or []
            bid = buy_book[0].get("price") if buy_book else None
            ask = sell_book[0].get("price") if sell_book else None
            if bid is None or ask is None:
                continue
            bid = float(bid)
            ask = float(ask)
            if bid <= 0 or ask <= 0:
                continue
            last_price = q.get("last_price")
            ts_epoch = _extract_quote_epoch(
                q.get("timestamp") or q.get("last_trade_time"),
                fallback_epoch=now_epoch,
            )
            update_index_quote_snapshot(
                symbol=sym,
                bid=bid,
                ask=ask,
                mid=(bid + ask) / 2.0,
                ts_epoch=ts_epoch,
                source="rest_quote",
                ltp=last_price,
            )
            return True
        except Exception:
            continue
    return bool(get_index_quote_snapshot(sym).get("bid") is not None and get_index_quote_snapshot(sym).get("ask") is not None)


def refresh_index_quote_from_rest(symbol: str, force: bool = False) -> bool:
    """
    Public self-heal hook used by orchestrator/feed recovery paths.
    Returns True if index bid/ask is available in cache after refresh attempt.
    """
    return bool(_refresh_index_quote_from_rest(symbol, force=force))


def _append_live_quote_error(
    event_code: str,
    symbol: str,
    *,
    category: str,
    level: str = "WARN",
    source: str | None = None,
    details: dict | None = None,
) -> None:
    event = str(event_code or "").strip()
    sym = str(symbol or "").upper()
    cat = str(category or "").strip().lower()
    if not event or not sym or not cat:
        return
    now_epoch = now_utc_epoch()
    min_interval = float(getattr(cfg, "LIVE_QUOTE_ERROR_MIN_LOG_SEC", 30.0))
    key = (event, sym, cat)
    last = float(_LIVE_QUOTE_ERROR_LAST_TS.get(key) or 0.0)
    if last and (now_epoch - last) < min_interval:
        return
    _LIVE_QUOTE_ERROR_LAST_TS[key] = now_epoch
    try:
        payload = {
            "ts_ist": now_ist().isoformat(),
            "ts_epoch": float(now_epoch),
            "event_code": event,
            "reason_code": event,
            "reason": event,
            "category": cat,
            "level": str(level or "WARN").upper(),
            "symbol": sym,
            "source": str(source) if source is not None else None,
            "details": details if isinstance(details, dict) else {},
        }
        p = logs_dir() / "live_quote_errors.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _log_index_bidask_missing(
    symbol: str,
    source: str | None = None,
    *,
    level: str = "WARN",
    details: dict | None = None,
):
    payload_details = {
        "missing_fields": ["bid", "ask"],
        "hint": "index often has no depth",
    }
    if isinstance(details, dict):
        payload_details.update(details)
    _append_live_quote_error(
        event_code="index_bidask_missing",
        symbol=symbol,
        category="missing",
        level=level,
        source=source,
        details=payload_details,
    )


def _should_log_index_bidask_missing(*, execution_mode: str, require_live_quotes: bool, market_open: bool) -> bool:
    ctx = derive_market_context({"execution_mode": execution_mode, "market_open": market_open})
    if ctx.mode == "OFFHOURS":
        return False
    if ctx.mode != "LIVE":
        return False
    return bool(require_live_quotes)


def _maybe_log_index_bidask_missing(
    symbol: str,
    *,
    quote_ok: bool,
    quote_source: str | None,
    ltp_source: str | None,
    market_open: bool,
    ltp=None,
    ltp_age_sec: float | None = None,
) -> None:
    if quote_ok:
        return
    execution_mode = str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper()
    ctx = derive_market_context({"execution_mode": execution_mode, "market_open": market_open})
    if ctx.mode == "OFFHOURS":
        if bool(getattr(cfg, "OFFHOURS_DEBUG_INDEX_BIDASK_MISSING", False)):
            logger.debug(
                "offhours_index_bidask_missing_suppressed symbol=%s quote_source=%s ltp_source=%s",
                symbol,
                quote_source,
                ltp_source,
            )
        return
    require_live_quotes = _effective_require_live_quotes(
        {"market_open": market_open},
        execution_mode=execution_mode,
    )
    if not _should_log_index_bidask_missing(
        execution_mode=execution_mode,
        require_live_quotes=require_live_quotes,
        market_open=market_open,
    ):
        return
    ltp_usable = False
    try:
        ltp_ok = ltp is not None and float(ltp) > 0.0
    except Exception:
        ltp_ok = False
    if ltp_ok:
        if ltp_age_sec is None:
            ltp_usable = not bool(require_live_quotes)
        else:
            max_ltp_age = float(getattr(cfg, "MAX_LTP_AGE_SEC", 8.0))
            ltp_usable = float(max(0.0, ltp_age_sec)) <= max_ltp_age
    level = "ERROR" if (require_live_quotes and (not ltp_usable)) else "WARN"
    _log_index_bidask_missing(
        symbol,
        level=level,
        source=quote_source,
        details={
            "mode": execution_mode,
            "market_open": bool(market_open),
            "quote_source": str(quote_source) if quote_source is not None else None,
            "ltp_source": str(ltp_source) if ltp_source is not None else None,
            "ltp_usable": bool(ltp_usable),
            "ltp_age_sec": ltp_age_sec,
        },
    )


def _derive_unstable_reasons(
    *,
    regime_probs: dict | None,
    regime_entropy: float | None,
    regime_transition_rate: float | None,
    indicators_ok: bool,
    ohlc_bars_count: int,
    min_bars: int,
    missing_inputs: list[str] | None = None,
    model_unstable_flag: bool = False,
    primary_regime: str = "",
    symbol: str = "",
    session_bucket: str | None = None,
    timestamp_ist: str | None = None,
    segment: str | None = None,
    is_expiry_day: bool = False,
    is_event_mode: bool = False,
):
    """
    Build explicit reasons for regime instability.
    Reasons are explicit and deterministic:
      - prob_too_low
      - entropy_too_high
    Additional non-probabilistic reasons are preserved for diagnosability.
    Strong confidence (very high max-probability + very low entropy)
    clears probabilistic instability reasons.
    """
    reasons = []
    probs = regime_probs or {}
    try:
        max_prob = max(float(v) for v in probs.values()) if probs else 0.0
    except Exception:
        max_prob = 0.0
    try:
        entropy = float(regime_entropy or 0.0)
    except Exception:
        entropy = 0.0
    try:
        bars = int(ohlc_bars_count)
    except Exception:
        bars = 0
    try:
        needed = int(min_bars)
    except Exception:
        needed = int(getattr(cfg, "OHLC_MIN_BARS", 30))

    missing = {str(x) for x in (missing_inputs or []) if x}
    if bars < needed:
        reasons.append("warmup_incomplete")
        reasons.append("bars_insufficient")
    if not bool(indicators_ok):
        reasons.append("indicators_missing")
    if ("indicators_stale" in missing) and ("indicators_missing" not in reasons):
        reasons.append("indicators_missing")
    if ("indicators_never_computed" in missing or "never_computed" in missing) and ("indicators_missing" not in reasons):
        reasons.append("indicators_missing")

    prob_min = float(getattr(cfg, "REGIME_PROB_MIN", 0.45))
    from core.regime_entropy_gate import evaluate_regime_entropy_gate
    resolved_session_bucket = str(session_bucket or "").strip().upper()
    if not resolved_session_bucket:
        resolved_session_bucket = _resolve_market_session_bucket(
            segment=segment,
            timestamp_ist=timestamp_ist,
            is_expiry_day=is_expiry_day,
            is_event_mode=is_event_mode,
        )
    entropy_gate = evaluate_regime_entropy_gate(
        raw_entropy=entropy if entropy > 0 else None,
        probabilities=probs if probs else None,
        session_bucket=resolved_session_bucket,
        expiry_day=is_expiry_day,
        event_mode=is_event_mode,
        regime_prob_max=max_prob,
        primary_regime=primary_regime,
        market_data={"symbol": symbol, "segment": segment, "timestamp_ist": timestamp_ist},
    )

    if entropy_gate.get("gate_passed") is False or entropy_gate.get("uncertain"):
        reasons.append("entropy_too_high")
    if max_prob < prob_min:
        reasons.append("prob_too_low")

    # Confidence override for clearly stable distributions.
    strong_prob = float(getattr(cfg, "REGIME_STABLE_PROB_OVERRIDE_MIN", 0.99))
    strong_entropy = float(getattr(cfg, "REGIME_STABLE_ENTROPY_OVERRIDE_MAX", 0.01))
    if max_prob >= strong_prob and entropy <= strong_entropy:
        probabilistic = {"entropy_too_high", "prob_too_low"}
        reasons = [r for r in reasons if r not in probabilistic]

    return list(dict.fromkeys(reasons))


def _log_insufficient_ohlc_warning(
    symbol: str,
    bars_count: int,
    min_bars: int,
    reason: str,
    *,
    detail: str | None = None,
    interval: str | None = None,
    target_bars: int | None = None,
) -> None:
    """
    Emit a single warning per symbol/reason per process to avoid log spam.
    """
    key = (str(symbol or "").upper(), str(reason))
    if key in _INSUFFICIENT_OHLC_WARNED:
        return
    _INSUFFICIENT_OHLC_WARNED.add(key)
    payload = {
        "event": "INSUFFICIENT_OHLC_BARS",
        "warning": "insufficient OHLC bars",
        "symbol": symbol,
        "bars_count": int(bars_count),
        "min_bars": int(min_bars),
        "reason": reason,
        "reason_code": str(reason),
        "detail": str(detail) if detail is not None else None,
        "interval": str(interval) if interval is not None else None,
        "target_bars": int(target_bars) if target_bars is not None else None,
        "ts_epoch": now_utc_epoch(),
        "ts_ist": now_ist().isoformat(),
    }
    try:
        p = logs_dir() / "market_data_warnings.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _log_market_data_event(event: str, payload: dict | None = None) -> None:
    try:
        row = {
            "event": str(event),
            "ts_epoch": now_utc_epoch(),
            "ts_ist": now_ist().isoformat(),
        }
        if isinstance(payload, dict):
            row.update(payload)
        p = logs_dir() / "market_data_warnings.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _warm_seed_windows_minutes(raw_windows: str | None = None) -> list[int]:
    raw = str(
        raw_windows
        if raw_windows is not None
        else getattr(cfg, "OHLC_WARM_SEED_WINDOWS_MIN", "120,240")
    )
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            val = int(part)
        except Exception:
            continue
        if val > 0 and val not in out:
            out.append(val)
    return out or [120, 240]


def _interval_to_minutes(interval: str | None) -> int:
    val = str(interval or "minute").strip().lower()
    mapping = {
        "minute": 1,
        "1minute": 1,
        "3minute": 3,
        "5minute": 5,
        "10minute": 10,
        "15minute": 15,
        "30minute": 30,
        "60minute": 60,
        "hour": 60,
        "day": 390,
    }
    return int(mapping.get(val, 1))


def _startup_seed_windows_minutes(interval: str, target_bars: int) -> list[int]:
    interval_min = max(1, _interval_to_minutes(interval))
    base = max(interval_min * max(int(target_bars), 1), interval_min * 30)
    fallback = int(base * 2)
    lookback_days = max(1, int(getattr(cfg, "STARTUP_WARMUP_LOOKBACK_DAYS", 7)))
    lookback_minutes = int(getattr(cfg, "STARTUP_WARMUP_LOOKBACK_MINUTES", lookback_days * 24 * 60))

    windows: list[int] = []
    for raw in (base, fallback, lookback_minutes):
        window = max(interval_min, int(raw))
        if window not in windows:
            windows.append(window)
    return windows


def _is_non_live_market_mode(mode: str | None) -> bool:
    return str(mode or "").strip().upper() in {"SIM", "PAPER", "OFFHOURS"}


def _startup_hist_empty_degraded_row(symbol: str) -> dict | None:
    sym = str(symbol or "").strip().upper()
    for row in list(_STARTUP_WARMUP_ROWS or []):
        if str((row or {}).get("symbol") or "").strip().upper() != sym:
            continue
        if str((row or {}).get("warmup_degraded_detail") or "").strip().lower() != "hist_empty_nonlive":
            continue
        return dict(row or {})
    return None


def _coerce_finite_float(value) -> float | None:
    try:
        resolved = float(value)
    except Exception:
        return None
    if not math.isfinite(resolved):
        return None
    return float(resolved)


def _feature_value_missing(value, *, zero_is_missing: bool = True) -> bool:
    resolved = _coerce_finite_float(value)
    if resolved is None:
        return True
    if zero_is_missing and abs(float(resolved)) <= 1e-12:
        return True
    return False


def _clamp_feature_hint(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(float(low), min(float(high), float(value)))


def _apply_nonlive_feature_fallback(
    symbol: str,
    snapshot: dict,
    *,
    market_mode: str,
    allow_stale_quotes: bool,
    degraded_reason: str | None = None,
) -> tuple[dict, list[str]]:
    row = dict(snapshot or {})
    if not bool(getattr(cfg, "NONLIVE_FEATURE_FALLBACK_ENABLE", True)):
        return row, []
    if not _is_non_live_market_mode(market_mode):
        return row, []
    if not bool(allow_stale_quotes):
        return row, []

    degraded_text = str(degraded_reason or row.get("warmup_reason") or row.get("ohlc_seed_reason") or "").strip().upper()
    degraded_detail = str(row.get("warmup_degraded_detail") or "").strip().lower()
    if degraded_text != "HIST_FETCH_FAILED" and degraded_detail != "hist_empty_nonlive":
        return row, []

    ltp = _coerce_finite_float(row.get("ltp"))
    if ltp is None or ltp <= 0.0:
        return row, []

    prev_ltp = _coerce_finite_float(row.get("prev_ltp"))
    ltp_change = _coerce_finite_float(row.get("ltp_change"))
    if ltp_change is None and prev_ltp is not None:
        ltp_change = float(ltp) - float(prev_ltp)
    ltp_change = float(ltp_change or 0.0)

    atr = _coerce_finite_float(row.get("atr"))
    base_atr = atr if atr is not None and atr > 0.0 else max(abs(ltp_change), abs(float(ltp)) * float(getattr(cfg, "NONLIVE_FEATURE_FALLBACK_ATR_PCT", 0.001)), 1.0)
    macro_direction_bias = _coerce_finite_float(row.get("macro_direction_bias")) or 0.0
    depth_imbalance = _coerce_finite_float(row.get("depth_imbalance")) or 0.0
    option_chain_skew = _coerce_finite_float(row.get("option_chain_skew")) or 0.0
    oi_delta = _coerce_finite_float(row.get("oi_delta")) or 0.0

    directional_hint = 0.0
    if base_atr > 0.0:
        directional_hint += _clamp_feature_hint(ltp_change / max(base_atr, 1e-6)) * 0.45
    directional_hint += _clamp_feature_hint(macro_direction_bias) * 0.20
    directional_hint += _clamp_feature_hint(depth_imbalance) * 0.20
    directional_hint += _clamp_feature_hint(option_chain_skew / 0.05 if option_chain_skew else 0.0) * 0.10
    if oi_delta > 0:
        directional_hint += 0.10
    elif oi_delta < 0:
        directional_hint -= 0.10
    directional_hint = _clamp_feature_hint(directional_hint)
    hint_abs = abs(float(directional_hint))
    hint_min = max(0.0, float(getattr(cfg, "NONLIVE_FEATURE_FALLBACK_SIGNAL_HINT_MIN", 0.15) or 0.15))
    magnitude = max(
        hint_abs,
        abs(float(depth_imbalance)),
        min(1.0, abs(float(option_chain_skew)) / 0.05) if option_chain_skew else 0.0,
    )

    fallback_fields: list[str] = []
    if _feature_value_missing(row.get("atr")):
        row["atr"] = round(float(base_atr), 6)
        fallback_fields.append("atr")

    current_vwap = _coerce_finite_float(row.get("vwap"))
    if current_vwap is None or current_vwap <= 0.0 or abs(float(current_vwap) - float(ltp)) <= 1e-9:
        vwap_value = float(ltp)
        if hint_abs >= hint_min:
            vwap_value = float(ltp) - (float(directional_hint) * float(base_atr) * 0.08)
        row["vwap"] = round(float(vwap_value), 6)
        fallback_fields.append("vwap")

    if _feature_value_missing(row.get("ltp_change_window")) and hint_abs >= hint_min:
        row["ltp_change_window"] = round(float(directional_hint) * float(base_atr) * 0.02, 6)
        fallback_fields.append("ltp_change_window")
    if _feature_value_missing(row.get("ltp_change_5m")) and hint_abs >= hint_min:
        row["ltp_change_5m"] = round(float(directional_hint) * float(base_atr) * 0.03, 6)
        fallback_fields.append("ltp_change_5m")
    if _feature_value_missing(row.get("ltp_change_10m")) and hint_abs >= hint_min:
        row["ltp_change_10m"] = round(float(directional_hint) * float(base_atr) * 0.04, 6)
        fallback_fields.append("ltp_change_10m")
    if _feature_value_missing(row.get("rsi_mom")) and hint_abs >= hint_min:
        row["rsi_mom"] = round(float(directional_hint) * 0.20, 6)
        fallback_fields.append("rsi_mom")
    if _feature_value_missing(row.get("vol_z")) and magnitude >= hint_min:
        resolved_window = abs(_coerce_finite_float(row.get("ltp_change_window")) or 0.0)
        vol_basis = max(
            float(magnitude) * 0.70,
            resolved_window / max(float(base_atr) * 0.25, 1e-6),
        )
        row["vol_z"] = round(min(float(vol_basis), 2.0), 6)
        fallback_fields.append("vol_z")

    if fallback_fields:
        row["nonlive_feature_fallback"] = True
        row["nonlive_feature_fallback_fields"] = list(dict.fromkeys(str(field) for field in fallback_fields if str(field)))
        row["nonlive_feature_fallback_reason"] = (
            "hist_empty_nonlive"
            if degraded_detail == "hist_empty_nonlive"
            else str(degraded_text or "hist_fetch_failed").lower()
        )
        row["nonlive_feature_fallback_signal_hint"] = round(float(directional_hint), 6)
        row["nonlive_feature_fallback_strength_basis"] = round(float(magnitude), 6)
    return row, fallback_fields


def _warm_seed_ohlc_from_history(
    symbol: str,
    bars: list,
    min_bars: int,
    *,
    as_of,
    interval: str | None = None,
    windows_minutes: list[int] | None = None,
    required_seed_bars: int | None = None,
    startup_phase: bool = False,
    market_mode: str | None = None,
):
    """
    Warm-seed minute OHLC bars when current buffer is insufficient.
    Returns (bars, seeded_ok, reason_code).
    """
    import os
    seed_interval = str(interval or getattr(cfg, "OHLC_WARM_SEED_INTERVAL", "minute")).strip() or "minute"
    required_bars = int(required_seed_bars if required_seed_bars is not None else min_bars)
    attempts_used = 0
    hist_empty_attempts = 0
    normalized_market_mode = str(market_mode or getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper()
    max_nonlive_hist_empty_attempts = max(
        1,
        int(getattr(cfg, "NONLIVE_STARTUP_WARMUP_MAX_HIST_EMPTY_ATTEMPTS", 1)),
    )
    if len(bars) >= required_bars:
        _WARMUP_SEED_ATTEMPTS[symbol] = attempts_used
        _WARMUP_SEED_DETAILS.pop(symbol, None)
        return bars, True, None
    reason_code = "HIST_FETCH_FAILED"
    try:
        kite_client.ensure()
    except Exception:
        pass
    kite_available = bool(getattr(kite_client, "kite", None))
    if not kite_available:
        _WARMUP_SEED_ATTEMPTS[symbol] = attempts_used
        _WARMUP_SEED_DETAILS.pop(symbol, None)
        _log_insufficient_ohlc_warning(
            symbol=symbol,
            bars_count=len(bars),
            min_bars=min_bars,
            reason=reason_code,
            detail="kite_api_unavailable",
            interval=seed_interval,
            target_bars=required_bars,
        )
        return bars, False, reason_code
    try:
        token = kite_client.resolve_index_token(symbol)
        if not token:
            _WARMUP_SEED_ATTEMPTS[symbol] = attempts_used
            _WARMUP_SEED_DETAILS.pop(symbol, None)
            _log_insufficient_ohlc_warning(
                symbol=symbol,
                bars_count=len(bars),
                min_bars=min_bars,
                reason=reason_code,
                detail="missing_index_token",
                interval=seed_interval,
                target_bars=required_bars,
            )
            return bars, False, reason_code
        last_reason = "historical_empty"
        window_list = windows_minutes or _warm_seed_windows_minutes()
        retry_attempts = max(1, int(getattr(cfg, "STARTUP_WARMUP_FETCH_RETRIES", 3))) if (startup_phase or os.environ.get("PYTEST_CURRENT_TEST")) else 1
        retry_backoff = max(0.0, float(getattr(cfg, "STARTUP_WARMUP_RETRY_BACKOFF_SEC", 0.4)))
        max_backoff = max(retry_backoff, float(getattr(cfg, "STARTUP_WARMUP_MAX_BACKOFF_SEC", 2.5)))
        for window_min in window_list:
            hist = []
            for attempt in range(retry_attempts):
                attempts_used += 1
                from_dt = as_of - timedelta(minutes=int(window_min))
                to_dt = as_of
                try:
                    hist = kite_client.historical_data(
                        token,
                        from_dt,
                        to_dt,
                        interval=seed_interval,
                        _symbol=symbol,
                        _exchange="NSE",
                        _caller="market_data_warm_seed",
                    )
                except Exception as exc:
                    if kite_client._is_historical_auth_error(exc) or is_auth_error(exc=exc):
                        logger.error("FATAL: Kite authentication failed — stopping system")
                        raise RuntimeError("Kite auth failed") from exc
                    logger.warning("fetch_history_error symbol=%s err=%s", symbol, type(exc).__name__)
                    hist = []
                    last_reason = f"historical_error:{type(exc).__name__}"
                else:
                    if hist:
                        break
                    last_reason = "historical_empty"
                    hist_empty_attempts += 1
                    if (
                        startup_phase
                        and _is_non_live_market_mode(normalized_market_mode)
                        and hist_empty_attempts >= max_nonlive_hist_empty_attempts
                    ):
                        _WARMUP_SEED_ATTEMPTS[symbol] = attempts_used
                        _WARMUP_SEED_DETAILS[symbol] = {
                            "warmup_degraded_detail": "hist_empty_nonlive",
                            "warmup_degraded_attempts": int(attempts_used),
                            "market_mode": normalized_market_mode,
                            "startup_phase": True,
                        }
                        logger.warning(
                            "warm_bootstrap_degraded reason=hist_empty_nonlive attempts=%s symbol=%s",
                            attempts_used,
                            symbol,
                        )
                        _log_market_data_event(
                            "warm_bootstrap_degraded",
                            {
                                "reason": "hist_empty_nonlive",
                                "attempts": int(attempts_used),
                                "symbol": str(symbol or "").upper(),
                                "market_mode": normalized_market_mode,
                                "startup_phase": True,
                            },
                        )
                        _log_insufficient_ohlc_warning(
                            symbol=symbol,
                            bars_count=len(bars),
                            min_bars=min_bars,
                            reason=reason_code,
                            detail="hist_empty_nonlive",
                            interval=seed_interval,
                            target_bars=required_bars,
                        )
                        return bars, False, reason_code
                if attempt < retry_attempts - 1 and retry_backoff > 0:
                    sleep_sec = min(max_backoff, retry_backoff * (2 ** attempt))
                    time.sleep(sleep_sec)
            if not hist:
                continue
            seed_result = ohlc_buffer.seed_bars(symbol, hist)
            if not seed_result.get("accepted"):
                reason_code = str(seed_result.get("status", "INVALID_SEED_BATCH")).lower()
                return bars, False, reason_code

            bars = ohlc_buffer.get_completed_bars(symbol, as_of=as_of)
            if len(bars) >= required_bars:
                _WARMUP_SEED_ATTEMPTS[symbol] = attempts_used
                _WARMUP_SEED_DETAILS.pop(symbol, None)
                return bars, True, None
            last_reason = "seeded_but_still_insufficient"
        if len(bars) < required_bars:
            _WARMUP_SEED_ATTEMPTS[symbol] = attempts_used
            _WARMUP_SEED_DETAILS.pop(symbol, None)
            _log_insufficient_ohlc_warning(
                symbol=symbol,
                bars_count=len(bars),
                min_bars=min_bars,
                reason=reason_code,
                detail=last_reason,
                interval=seed_interval,
                target_bars=required_bars,
            )
            return bars, False, reason_code
        _WARMUP_SEED_ATTEMPTS[symbol] = attempts_used
        _WARMUP_SEED_DETAILS.pop(symbol, None)
        return bars, True, None
    except Exception as exc:
        if str(exc) == "Kite auth failed" or kite_client._is_historical_auth_error(exc) or is_auth_error(exc=exc):
            logger.error("FATAL: Kite authentication failed — stopping system")
            raise
        _WARMUP_SEED_ATTEMPTS[symbol] = attempts_used
        _WARMUP_SEED_DETAILS.pop(symbol, None)
        _log_insufficient_ohlc_warning(
            symbol=symbol,
            bars_count=len(bars),
            min_bars=min_bars,
            reason=reason_code,
            detail="historical_seed_error",
            interval=seed_interval,
            target_bars=required_bars,
        )
        return bars, False, reason_code


def _startup_warmup_symbols(symbols: list[str] | None = None) -> list[str]:
    if symbols:
        return list(dict.fromkeys(str(s).upper() for s in symbols if str(s).strip()))
    configured = list(getattr(cfg, "STARTUP_WARMUP_SYMBOLS", []) or [])
    if configured:
        return list(dict.fromkeys(str(s).upper() for s in configured if str(s).strip()))
    return list(dict.fromkeys(str(s).upper() for s in (getattr(cfg, "SYMBOLS", []) or []) if str(s).strip()))


def seed_ohlc_buffers_on_startup(
    symbols: list[str] | None = None,
    *,
    market_context: dict | None = None,
) -> list[dict]:
    """
    Seed OHLC buffers from historical minute candles at process startup.
    This runs before live ticks and writes structured observability logs.
    """
    symbol_list = _startup_warmup_symbols(symbols)
    min_bars = int(getattr(cfg, "SYSTEM_WARMUP_MIN_BARS", getattr(cfg, "OHLC_MIN_BARS", 30)))
    seed_interval = str(getattr(cfg, "STARTUP_WARMUP_INTERVAL", "5minute") or "5minute").strip() or "5minute"
    target_bars = max(int(getattr(cfg, "STARTUP_WARMUP_TARGET_BARS", 200)), min_bars)
    startup_windows = _startup_seed_windows_minutes(seed_interval, target_bars)
    warmup_ctx = derive_market_context(market_context or {})
    rows = []
    for symbol in symbol_list:
        pre_bars = ohlc_buffer.get_bars(symbol)
        pre_count = int(len(pre_bars))
        bars, seeded_ok, seed_reason = _warm_seed_ohlc_from_history(
            symbol=symbol,
            bars=pre_bars,
            min_bars=min_bars,
            as_of=now_ist(),
            interval=seed_interval,
            windows_minutes=startup_windows,
            required_seed_bars=target_bars,
            startup_phase=True,
            market_mode=warmup_ctx.mode,
        )
        warmup_seed_detail = dict(_WARMUP_SEED_DETAILS.get(symbol) or {})
        seeded_count = int(len(bars))
        indicators_ok = False
        last_candle_epoch = None
        last_candle_ts = None
        indicator_last_update_epoch = _INDICATOR_LAST_UPDATE_EPOCH.get(symbol)
        indicator_last_update_ts = None
        try:
            ind = compute_indicators(
                bars,
                vwap_window=getattr(cfg, "VWAP_WINDOW", 20),
                atr_period=getattr(cfg, "ATR_PERIOD", 14),
                adx_period=getattr(cfg, "ADX_PERIOD", 14),
                vol_window=getattr(cfg, "VOL_WINDOW", 30),
                slope_window=getattr(cfg, "VWAP_SLOPE_WINDOW", 10),
            )
            indicators_ok = bool(ind.get("ok")) and (seeded_count >= min_bars)
            last_ts = ind.get("last_ts") or (bars[-1].get("ts") if bars else None)
            if hasattr(last_ts, "timestamp"):
                last_candle_epoch = float(last_ts.timestamp())
                last_candle_ts = datetime.fromtimestamp(last_candle_epoch, tz=timezone.utc).astimezone(now_ist().tzinfo).isoformat()
            if indicators_ok and isinstance(last_candle_epoch, (int, float)):
                indicator_last_update_epoch = float(last_candle_epoch)
                _INDICATOR_LAST_UPDATE_EPOCH[symbol] = indicator_last_update_epoch
        except Exception:
            indicators_ok = False
        if isinstance(indicator_last_update_epoch, (int, float)):
            indicator_last_update_ts = datetime.fromtimestamp(
                float(indicator_last_update_epoch), tz=timezone.utc
            ).astimezone(now_ist().tzinfo).isoformat()
        warmup_ok = bool((seeded_count >= min_bars) and indicators_ok)
        warmup_reason = "HIST_FETCH_FAILED" if str(seed_reason or "").upper() == "HIST_FETCH_FAILED" else None
        warmup_status = "OK" if warmup_ok else ("DEGRADED" if warmup_reason else "WARMUP")
        row = {
            "event": "OHLC_STARTUP_SEED",
            "ts_epoch": now_utc_epoch(),
            "ts_ist": now_ist().isoformat(),
            "symbol": symbol,
            "min_bars": min_bars,
            "target_bars": target_bars,
            "seed_interval": seed_interval,
            "pre_seed_bars_count": pre_count,
            "seeded_bars_count": seeded_count,
            "seed_attempts": int(_WARMUP_SEED_ATTEMPTS.get(symbol, 0)),
            "seeded_ok": bool(seeded_ok),
            "seed_reason": seed_reason,
            "warmup_degraded_detail": warmup_seed_detail.get("warmup_degraded_detail"),
            "warmup_degraded_attempts": warmup_seed_detail.get("warmup_degraded_attempts"),
            "last_candle_ts": last_candle_ts,
            "last_candle_ts_epoch": last_candle_epoch,
            "indicators_ok_after_seed": indicators_ok,
            "indicator_last_update_ts": indicator_last_update_ts,
            "indicator_last_update_epoch": indicator_last_update_epoch,
            "warmup_ok": warmup_ok,
            "warmup_status": warmup_status,
            "warmup_reason": warmup_reason,
            "market_context": warmup_ctx.to_dict(),
        }
        rows.append(row)
        try:
            p = logs_dir() / "market_data_warmup.jsonl"
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=True) + "\n")
        except Exception:
            pass
    return rows


def ensure_startup_warmup_bootstrap(
    symbols: list[str] | None = None,
    *,
    force: bool = False,
    market_context: dict | None = None,
) -> list[dict]:
    global _STARTUP_WARMUP_DONE
    global _STARTUP_WARMUP_ROWS
    if not bool(getattr(cfg, "STARTUP_WARMUP_ENABLE", True)):
        return []
    if _STARTUP_WARMUP_DONE and (not force):
        return list(_STARTUP_WARMUP_ROWS)
    rows = seed_ohlc_buffers_on_startup(symbols=symbols, market_context=market_context)
    _STARTUP_WARMUP_ROWS = list(rows)
    _STARTUP_WARMUP_DONE = True
    return list(rows)

def get_current_regime(symbol: str | None = None):
    """
    Canonical regime provider. Returns latest cached regime output from RegimeProbModel.
    If missing, returns NEUTRAL with empty probabilities.
    """
    if symbol:
        key = str(symbol).upper()
        snap = _LAST_REGIME_SNAPSHOT.get(key)
        if snap is None:
            snap = _LAST_REGIME_SNAPSHOT.get(str(symbol))
        if snap is None:
            return {
                "regime": "UNKNOWN",
                "primary_regime": "UNKNOWN",
                "regime_confidence": None,
                "regime_reasons": ["warmup_incomplete", "missing_ohlc"],
                "regime_probs": {},
                "regime_entropy": 0.0,
                "unstable_regime_flag": True,
                "regime_ts": None,
            }
        return dict(snap)
    return {k: dict(v) for k, v in _LAST_REGIME_SNAPSHOT.items()}

def _cached_ltp(symbol: str):
    try:
        entry = _LAST_GOOD_LTP.get(symbol)
        if not entry:
            return None
        age = compute_age_sec(entry.get("ts"), now_utc_epoch())
        if age is None:
            return None
        if age <= getattr(cfg, "LTP_CACHE_TTL_SEC", 300):
            return entry.get("ltp")
    except Exception:
        return None
    return None


def _index_ltp_sanity_floor(symbol: str) -> float:
    sym = str(symbol or "").upper()
    floor_map = getattr(cfg, "INDEX_LTP_SANITY_MIN_BY_SYMBOL", {}) or {}
    try:
        mapped = floor_map.get(sym)
        if mapped is not None and float(mapped) > 0:
            return float(mapped)
    except Exception:
        pass
    close_map = getattr(cfg, "PREMARKET_INDICES_CLOSE", {}) or {}
    try:
        close_val = close_map.get(sym)
        if close_val is not None and float(close_val) > 0:
            ratio = max(0.01, float(getattr(cfg, "INDEX_LTP_SANITY_MIN_RATIO", 0.2)))
            return float(close_val) * ratio
    except Exception:
        pass
    return float(getattr(cfg, "INDEX_LTP_SANITY_MIN_DEFAULT", 1000.0))


def _is_implausible_index_ltp(symbol: str, price) -> bool:
    if not bool(getattr(cfg, "INDEX_LTP_SANITY_ENABLE", True)):
        return False
    if not is_index(symbol):
        return False
    try:
        p = float(price)
    except Exception:
        return True
    if p <= 0:
        return True
    return p < _index_ltp_sanity_floor(symbol)


def _save_cached_ltp(symbol: str, ltp: float):
    try:
        _LAST_GOOD_LTP[symbol] = {"ltp": float(ltp), "ts": now_utc_epoch()}
    except Exception:
        pass

def get_ltp(symbol: str):
    """
    Fetch latest market price from Kite or fallback.
    """
    segment = coerce_segment_for_market_context(
        getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO"),
        symbol=str(symbol or "").upper(),
        instrument="OPT",
    )
    market_open = bool(is_market_open_ist(segment=segment))
    market_ctx = derive_market_context(
        {
            "execution_mode": str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper(),
            "market_open": bool(market_open),
            "segment": segment,
        }
    )
    offhours = market_ctx.mode == "OFFHOURS"
    require_live_quotes = bool(market_ctx.require_live_quotes and getattr(cfg, "REQUIRE_LIVE_QUOTES", True))
    live_mode = market_ctx.mode == "LIVE"
    _refresh_index_quote_from_rest(symbol, force=False)
    ws_quote = get_index_quote_snapshot(symbol)
    if ws_quote:
        try:
            ws_price = ws_quote.get("last_price")
            if ws_price is None:
                ws_price = ws_quote.get("mid")
            if ws_price is None:
                ws_price = (_DATA_CACHE.get(symbol, {}) or {}).get("last_ltp")
            if ws_price is not None and float(ws_price) > 0:
                if _is_implausible_index_ltp(symbol, ws_price):
                    _append_live_quote_error(
                        event_code="index_ltp_sanity_reject",
                        symbol=symbol,
                        category="sanity",
                        source="ws",
                        details={
                            "price": float(ws_price),
                            "min_floor": _index_ltp_sanity_floor(symbol),
                        },
                    )
                else:
                    _save_cached_ltp(symbol, float(ws_price))
                    cache = _DATA_CACHE.setdefault(symbol, {})
                    cache["ltp_source"] = "live"
                    cache["ltp_ts_epoch"] = float(ws_quote.get("ts_epoch") or now_utc_epoch())
                    return float(ws_price)
        except Exception:
            pass
    if cfg.KITE_USE_API:
        kite_client.ensure()
        if not kite_client.kite and require_live_quotes:
            _append_live_quote_error(
                event_code="kite_not_initialized",
                symbol=symbol,
                category="auth",
                source="rest",
                details={"require_live_quotes": bool(require_live_quotes)},
            )
        if is_index(symbol):
            failures = []
            index_keys = _index_quote_keys(symbol)
            _log_index_quote_request(symbol, "ltp", index_keys)
            for ksym in index_keys:
                try:
                    data = kite_client.ltp([ksym]) or {}
                    price = data.get(ksym, {}).get("last_price", 0)
                    if price:
                        if _is_implausible_index_ltp(symbol, price):
                            failures.append(f"{ksym}:ltp_sanity_reject:{price}")
                            continue
                        _save_cached_ltp(symbol, price)
                        cache = _DATA_CACHE.setdefault(symbol, {})
                        cache["ltp_source"] = "live"
                        cache["ltp_ts_epoch"] = now_utc_epoch()
                        return price
                except Exception as e:
                    failures.append(f"{ksym}:{e}")
            if require_live_quotes:
                _append_live_quote_error(
                    event_code="ltp_fetch_failed",
                    symbol=symbol,
                    category="exception",
                    source="rest",
                    details={
                        "detail": failures[-1] if failures else "no_price_in_response",
                        "requested_symbols": index_keys,
                    },
                )
        else:
            try:
                ksym = f"NSE:{symbol}"
                data = kite_client.ltp([ksym]) or {}
                price = data.get(ksym, {}).get("last_price", 0)
                if price:
                    _save_cached_ltp(symbol, price)
                    cache = _DATA_CACHE.setdefault(symbol, {})
                    cache["ltp_source"] = "live"
                    cache["ltp_ts_epoch"] = now_utc_epoch()
                    return price
            except Exception as e:
                if require_live_quotes:
                    _append_live_quote_error(
                        event_code="ltp_fetch_failed",
                        symbol=symbol,
                        category="exception",
                        source="rest",
                        details={"detail": str(e), "requested_symbols": [ksym]},
                    )

    # Fallback to cached LTP if allowed (disabled in LIVE)
    if (not live_mode) and getattr(cfg, "ALLOW_STALE_LTP", True):
        cached = _cached_ltp(symbol)
        if cached:
            _DATA_CACHE.setdefault(symbol, {})["ltp_source"] = "cache"
            return cached

    # Fallback
    if require_live_quotes:
        _DATA_CACHE.setdefault(symbol, {})["ltp_source"] = "none"
        if market_open and (not offhours):
            return None
        if (not live_mode) and getattr(cfg, "ALLOW_CLOSE_FALLBACK", True):
            close_map = getattr(cfg, "PREMARKET_INDICES_CLOSE", {})
            _DATA_CACHE.setdefault(symbol, {})["ltp_source"] = "fallback"
            return close_map.get(symbol.split(":")[-1], 0)
        return 0
    close_map = getattr(cfg, "PREMARKET_INDICES_CLOSE", {})
    _DATA_CACHE.setdefault(symbol, {})["ltp_source"] = "fallback"
    return close_map.get(symbol.split(":")[-1], 0)

# Alias for backward compatibility
get_nifty_ltp = get_ltp


_CANDLE_COLUMNS = ("time_ms", "open", "high", "low", "close", "volume")
_OPTION_SERIES_COLUMNS = (
    "time_ms",
    "ltp",
    "bid",
    "ask",
    "mark_price",
    "quote_age_sec",
    "spread_pct",
    "source",
)


def _empty_candles_df() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_CANDLE_COLUMNS))


def _coerce_epoch_ms(value) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return int(dt.timestamp() * 1000.0)
        if isinstance(value, (int, float)):
            num = float(value)
            if num <= 0:
                return None
            if num >= 10_000_000_000:
                return int(num)
            return int(num * 1000.0)
        text = str(value).strip()
        if not text:
            return None
        try:
            return _coerce_epoch_ms(float(text))
        except Exception:
            pass
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return int(dt.timestamp() * 1000.0)
    except Exception:
        return None


def get_candles(symbol: str, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """
    Fetch OHLCV candles for index underlyings using existing Kite integration.
    Returns a schema-stable DataFrame with columns:
      time_ms, open, high, low, close, volume
    """
    empty = _empty_candles_df()
    try:
        sym = str(symbol or "").upper().strip()
        iv = str(interval or "minute").strip() or "minute"
        start_epoch_ms = _coerce_epoch_ms(start_ms)
        end_epoch_ms = _coerce_epoch_ms(end_ms)
        if not sym or start_epoch_ms is None or end_epoch_ms is None or end_epoch_ms <= start_epoch_ms:
            return empty

        import pandas as pd
        from pathlib import Path
        offline_path = Path() / "data" / "live_intraday" / f"{sym}_intraday.csv"
        if offline_path.exists():
            try:
                df = pd.read_csv(offline_path)
                if 'timestamp' in df.columns:
                    df['time_ms'] = pd.to_datetime(df['timestamp'], utc=True).astype('int64') // 10**6
                    mask = (df['time_ms'] >= start_epoch_ms) & (df['time_ms'] <= end_epoch_ms)
                    sliced = df[mask].copy()
                    if not sliced.empty:
                        return sliced[['time_ms', 'open', 'high', 'low', 'close', 'volume']].reset_index(drop=True)
                    else:
                        print(f"[OFFLINE] {sym} slice empty for {start_epoch_ms} to {end_epoch_ms}, falling back to live API")
                else:
                    print(f"[OFFLINE] No timestamp column in {sym}, falling back to live API")
            except Exception as e:
                print(f"[OFFLINE] Exception loading {sym}: {e}")
        else:
            print(f"[OFFLINE] File not found: {offline_path.absolute()}")
        token = kite_client.resolve_index_token(sym)
        if token is None:
            return empty
        ist = timezone(timedelta(hours=5, minutes=30))
        from_dt = datetime.fromtimestamp(float(start_epoch_ms) / 1000.0, tz=timezone.utc).astimezone(ist)
        to_dt = datetime.fromtimestamp(float(end_epoch_ms) / 1000.0, tz=timezone.utc).astimezone(ist)
        candles = kite_client.historical_data(
            int(token),
            from_dt,
            to_dt,
            interval=iv,
            _symbol=sym,
            _exchange="NSE",
            _caller="market_data_underlying_candles",
        ) or []
        rows = []
        for candle in candles:
            if not isinstance(candle, dict):
                continue
            ts_ms = _coerce_epoch_ms(candle.get("date") or candle.get("ts"))
            open_px = _as_bar_float(candle.get("open"))
            high_px = _as_bar_float(candle.get("high"))
            low_px = _as_bar_float(candle.get("low"))
            close_px = _as_bar_float(candle.get("close"))
            volume = _as_bar_float(candle.get("volume"))
            if ts_ms is None or open_px is None or high_px is None or low_px is None or close_px is None:
                continue
            rows.append(
                {
                    "time_ms": int(ts_ms),
                    "open": float(open_px),
                    "high": float(high_px),
                    "low": float(low_px),
                    "close": float(close_px),
                    "volume": float(volume if volume is not None else 0.0),
                }
            )
        if not rows:
            return empty
        out = pd.DataFrame(rows)
        out = out.sort_values("time_ms").drop_duplicates(subset=["time_ms"], keep="last")
        for col in _CANDLE_COLUMNS:
            if col not in out.columns:
                out[col] = None
        return out[list(_CANDLE_COLUMNS)]
    except Exception:
        return empty


def _empty_option_series_df() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_OPTION_SERIES_COLUMNS))


def get_underlying_candles(symbol: str, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Explicit wrapper for underlying index candles."""
    return get_candles(symbol=symbol, interval=interval, start_ms=start_ms, end_ms=end_ms)


def _top_price(levels) -> float | None:
    if not isinstance(levels, list) or not levels:
        return None
    level0 = levels[0] if isinstance(levels[0], dict) else None
    if not isinstance(level0, dict):
        return None
    for key in ("price", "p"):
        val = _as_bar_float(level0.get(key))
        if val is not None:
            return float(val)
    return None


def _parse_depth_snapshot(depth_json_text: str | None) -> tuple[float | None, float | None]:
    try:
        payload = json.loads(depth_json_text or "{}")
    except Exception:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    depth = payload.get("depth")
    if isinstance(depth, dict):
        source = depth
    else:
        source = payload
    bid = _top_price(source.get("buy") or source.get("bids"))
    ask = _top_price(source.get("sell") or source.get("asks"))
    return bid, ask


def _load_option_snapshots_from_db(instrument_token: int, start_ms: int, end_ms: int, max_rows: int = 4000) -> pd.DataFrame:
    out = _empty_option_series_df()
    if instrument_token <= 0:
        return out
    db_path = Path(str(getattr(cfg, "TRADE_DB_PATH", "") or ""))
    if not db_path.exists():
        return out
    start_sec = float(start_ms) / 1000.0
    end_sec = float(end_ms) / 1000.0
    if end_sec <= start_sec:
        return out

    by_time: dict[int, dict] = {}
    try:
        with sqlite3.connect(str(db_path)) as conn:
            try:
                tick_rows = conn.execute(
                    """
                    SELECT timestamp_epoch, last_price
                    FROM ticks
                    WHERE instrument_token=? AND timestamp_epoch BETWEEN ? AND ?
                    ORDER BY timestamp_epoch ASC
                    LIMIT ?
                    """,
                    (int(instrument_token), float(start_sec), float(end_sec), int(max_rows)),
                ).fetchall()
            except sqlite3.OperationalError:
                tick_rows = []
            for ts_epoch, last_price in tick_rows:
                ts_ms = _coerce_epoch_ms(ts_epoch)
                ltp = _as_bar_float(last_price)
                if ts_ms is None or ltp is None:
                    continue
                rec = by_time.setdefault(
                    int(ts_ms),
                    {
                        "time_ms": int(ts_ms),
                        "ltp": None,
                        "bid": None,
                        "ask": None,
                        "mark_price": None,
                        "quote_age_sec": None,
                        "spread_pct": None,
                        "source": "option_snapshot",
                    },
                )
                rec["ltp"] = float(ltp)
            try:
                depth_rows = conn.execute(
                    """
                    SELECT timestamp_epoch, depth_json
                    FROM depth_snapshots
                    WHERE instrument_token=? AND timestamp_epoch BETWEEN ? AND ?
                    ORDER BY timestamp_epoch ASC
                    LIMIT ?
                    """,
                    (int(instrument_token), float(start_sec), float(end_sec), int(max_rows)),
                ).fetchall()
            except sqlite3.OperationalError:
                depth_rows = []
            for ts_epoch, depth_json in depth_rows:
                ts_ms = _coerce_epoch_ms(ts_epoch)
                if ts_ms is None:
                    continue
                bid, ask = _parse_depth_snapshot(depth_json)
                if bid is None and ask is None:
                    continue
                rec = by_time.setdefault(
                    int(ts_ms),
                    {
                        "time_ms": int(ts_ms),
                        "ltp": None,
                        "bid": None,
                        "ask": None,
                        "mark_price": None,
                        "quote_age_sec": None,
                        "spread_pct": None,
                        "source": "option_snapshot",
                    },
                )
                if bid is not None:
                    rec["bid"] = float(bid)
                if ask is not None:
                    rec["ask"] = float(ask)
    except Exception:
        return out

    if not by_time:
        return out
    out = pd.DataFrame(list(by_time.values()))
    out["ltp"] = pd.to_numeric(out.get("ltp"), errors="coerce")
    out["bid"] = pd.to_numeric(out.get("bid"), errors="coerce")
    out["ask"] = pd.to_numeric(out.get("ask"), errors="coerce")
    mid = (out["bid"] + out["ask"]) / 2.0
    out["mark_price"] = pd.to_numeric(out.get("mark_price"), errors="coerce")
    out["mark_price"] = out["mark_price"].where(out["mark_price"].notna(), mid)
    out["mark_price"] = out["mark_price"].where(out["mark_price"].notna(), out["ltp"])
    base = pd.to_numeric(out["mark_price"], errors="coerce")
    base = base.where(base > 0, out["ltp"])
    spread_calc = (out["ask"] - out["bid"]) / base
    out["spread_pct"] = pd.to_numeric(out.get("spread_pct"), errors="coerce")
    out["spread_pct"] = out["spread_pct"].where(out["spread_pct"].notna(), spread_calc)
    out = out.sort_values("time_ms").drop_duplicates(subset=["time_ms"], keep="last")
    for col in _OPTION_SERIES_COLUMNS:
        if col not in out.columns:
            out[col] = None
    return out[list(_OPTION_SERIES_COLUMNS)]


def get_option_candles_or_snapshots(trade, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """
    Tier-1: option historical candles by instrument_token.
    Tier-2 fallback: sparse snapshots from ticks/depth telemetry in trade DB.
    """
    empty = _empty_option_series_df()
    try:
        trade_row = dict(trade or {})
        start_epoch_ms = _coerce_epoch_ms(start_ms)
        end_epoch_ms = _coerce_epoch_ms(end_ms)
        if start_epoch_ms is None or end_epoch_ms is None or end_epoch_ms <= start_epoch_ms:
            return empty
        token_raw = trade_row.get("instrument_token")
        if token_raw in (None, "", "None"):
            token_raw = trade_row.get("token")
        try:
            token = int(token_raw) if token_raw is not None else None
        except Exception:
            token = None
        if token in (None, 0):
            tsym = str(trade_row.get("tradingsymbol") or "").strip().upper()
            if tsym:
                sym_hint = str(trade_row.get("symbol") or "").upper()
                ex_list = ["BFO", "NFO"] if sym_hint == "SENSEX" else ["NFO", "BFO"]
                for exchange in ex_list:
                    try:
                        instruments = kite_client.instruments_cached(
                            exchange,
                            ttl_sec=int(getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600)),
                        )
                    except Exception:
                        instruments = []
                    match = next(
                        (inst for inst in (instruments or []) if str(inst.get("tradingsymbol") or "").upper() == tsym),
                        None,
                    )
                    if match and match.get("instrument_token") is not None:
                        try:
                            token = int(match.get("instrument_token"))
                        except Exception:
                            token = None
                        break
        if token is None or token <= 0:
            return empty

        iv = str(interval or "minute").strip() or "minute"
        ist = timezone(timedelta(hours=5, minutes=30))
        from_dt = datetime.fromtimestamp(float(start_epoch_ms) / 1000.0, tz=timezone.utc).astimezone(ist)
        to_dt = datetime.fromtimestamp(float(end_epoch_ms) / 1000.0, tz=timezone.utc).astimezone(ist)

        try:
            option_exchange = str(trade_row.get("exchange") or "").strip().upper()
            if not option_exchange:
                option_exchange = "BFO" if str(trade_row.get("symbol") or "").upper() == "SENSEX" else "NFO"
            candles = kite_client.historical_data(
                int(token),
                from_dt,
                to_dt,
                interval=iv,
                _symbol=str(trade_row.get("symbol") or "").upper(),
                _exchange=option_exchange,
                _caller="market_data_option_candles",
            ) or []
        except Exception:
            candles = []
        rows = []
        for candle in candles:
            if not isinstance(candle, dict):
                continue
            ts_ms = _coerce_epoch_ms(candle.get("date") or candle.get("ts"))
            close_px = _as_bar_float(candle.get("close"))
            if ts_ms is None or close_px is None:
                continue
            rows.append(
                {
                    "time_ms": int(ts_ms),
                    "ltp": float(close_px),
                    "bid": None,
                    "ask": None,
                    "mark_price": None,
                    "quote_age_sec": None,
                    "spread_pct": None,
                    "source": "option_candle",
                }
            )
        if rows:
            out = pd.DataFrame(rows).sort_values("time_ms").drop_duplicates(subset=["time_ms"], keep="last")
            for col in _OPTION_SERIES_COLUMNS:
                if col not in out.columns:
                    out[col] = None
            return out[list(_OPTION_SERIES_COLUMNS)]

        return _load_option_snapshots_from_db(
            instrument_token=int(token),
            start_ms=int(start_epoch_ms),
            end_ms=int(end_epoch_ms),
        )
    except Exception:
        return empty

# -------------------------------
# Option Chain
# -------------------------------

def fetch_option_chain(
    symbol: str,
    ltp: float,
    force_synthetic: bool = False,
    market_context: dict | None = None,
):
    return fetch_option_chain_impl(
        symbol,
        ltp,
        force_synthetic=force_synthetic,
        market_context=market_context,
    )

def _fetch_option_chain_with_context(
    symbol: str,
    ltp: float,
    *,
    force_synthetic: bool,
    market_context: dict | None,
):
    """
    Backward-compatible option-chain call path.
    Some tests/integrations monkeypatch fetch_option_chain with legacy
    signature (without market_context). Fallback keeps API compatibility.
    """
    try:
        return fetch_option_chain(
            symbol,
            ltp,
            force_synthetic=force_synthetic,
            market_context=market_context,
        )
    except TypeError as exc:
        if "market_context" not in str(exc):
            raise
        return fetch_option_chain(
            symbol,
            ltp,
            force_synthetic=force_synthetic,
        )


def _hydrate_live_option_chain_liquidity(symbol: str, option_chain: list, *, chain_source: str, now_epoch: float) -> list:
    rows = list(option_chain or [])
    if not rows:
        return rows
    if str(chain_source or "").strip().lower() != "live":
        return rows
    update_option_liquidity_cache(
        [row for row in rows if isinstance(row, dict)],
        symbol=symbol,
        snapshot_ts_epoch=now_epoch,
        source="option_chain_live",
    )
    hydrated_rows: list = []
    for row in rows:
        if not isinstance(row, dict):
            hydrated_rows.append(row)
            continue
        hydrated_rows.append(
            hydrate_option_liquidity_fields(
                row,
                symbol=symbol,
                expiry=row.get("expiry") or row.get("expiry_date"),
                strike=row.get("strike"),
                option_type=row.get("type") or row.get("option_type") or row.get("right"),
                now_epoch=now_epoch,
            )
        )
    return hydrated_rows

def _option_chain_health(symbol: str, chain: list, ltp: float, require_live_quotes: bool | None = None):
    quotes_required = bool(
        getattr(cfg, "REQUIRE_LIVE_QUOTES", True)
        if require_live_quotes is None
        else require_live_quotes
    )
    total = len(chain)
    if total == 0:
        return {
            "symbol": symbol,
            "status": "ERROR" if quotes_required else "EMPTY",
            "total": 0,
            "missing_iv_pct": 1.0,
            "missing_quote_pct": 1.0,
            "strike_min": None,
            "strike_max": None,
            "ltp": ltp,
            "note": "No live option chain" if quotes_required else "Empty chain",
            "timestamp": now_ist().isoformat(),
        }
    missing_iv = sum(1 for c in chain if c.get("iv") is None)
    missing_quote = sum(1 for c in chain if not c.get("quote_ok", True))
    strikes = [c.get("strike") for c in chain if c.get("strike") is not None]
    strike_min = min(strikes) if strikes else None
    strike_max = max(strikes) if strikes else None
    missing_iv_pct = round(missing_iv / total, 4)
    missing_quote_pct = round(missing_quote / total, 4)
    status = "OK"
    if missing_iv_pct > getattr(cfg, "CHAIN_MAX_MISSING_IV_PCT", 0.2) or missing_quote_pct > getattr(cfg, "CHAIN_MAX_MISSING_QUOTE_PCT", 0.2):
        status = "WARN"
    return {
        "symbol": symbol,
        "status": status,
        "total": total,
        "missing_iv_pct": missing_iv_pct,
        "missing_quote_pct": missing_quote_pct,
        "strike_min": strike_min,
        "strike_max": strike_max,
        "ltp": ltp,
        "timestamp": now_ist().isoformat(),
    }

def fetch_live_market_data(*, allow_history_seed: bool = True):
    """
    Returns a list of market snapshots for symbols in config.
    Each snapshot includes LTP, VWAP, ATR, and option chain.
    """
    symbols = list(getattr(cfg, "SYMBOLS", []))
    results = []
    global _REGIME_MODEL
    global _NEWS_ENCODER
    global _NEWS_CAL
    global _NEWS_TEXT
    global _CROSS_ASSET
    if _REGIME_MODEL is None:
        try:
            model_path = getattr(cfg, "REGIME_MODEL_PATH", "models/regime_model.json")
            _REGIME_MODEL = RegimeProbModel(model_path=model_path)
        except Exception:
            _REGIME_MODEL = RegimeProbModel()
    if _NEWS_ENCODER is None:
        _NEWS_ENCODER = NewsShockEncoder()
    if _NEWS_CAL is None:
        _NEWS_CAL = NewsCalendar()
    if _NEWS_TEXT is None:
        _NEWS_TEXT = NewsEncoder()
    if _CROSS_ASSET is None:
        _CROSS_ASSET = CrossAsset()
    shock = {}
    cal_shock = {}
    text_shock = {}
    try:
        cal_shock = _NEWS_CAL.get_shock()
    except Exception:
        cal_shock = {}
    try:
        text_shock = _NEWS_TEXT.encode()
    except Exception:
        text_shock = {}
    # fallback legacy encoder if both empty
    if not cal_shock and not text_shock:
        try:
            shock = _NEWS_ENCODER.encode()
        except Exception:
            shock = {}
    else:
        # merge: choose higher shock score, prefer calendar metadata when stronger
        c_score = float(cal_shock.get("shock_score") or 0.0)
        t_score = float(text_shock.get("shock_score") or 0.0)
        if c_score >= t_score:
            shock = {**text_shock, **cal_shock}
        else:
            shock = {**cal_shock, **text_shock}

    cycle_cutoff = now_ist()
    cycle_cutoff_epoch = cycle_cutoff.timestamp()

    for symbol in symbols:
        segment = coerce_segment_for_market_context(
            getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO"),
            symbol=str(symbol or "").upper(),
            instrument="OPT",
        )
        market_open_for_segment = bool(is_open(now_dt=cycle_cutoff, segment=segment))
        runtime_mode = str(
            os.getenv(
                "TRADING_MODE",
                getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM")),
            )
        ).upper()
        market_ctx = derive_market_context(
            {
                "execution_mode": runtime_mode,
                "market_open": bool(market_open_for_segment),
                "segment": segment,
                "symbol": str(symbol or "").upper(),
                "instrument": "OPT",
            }
        )
        _append_live_quote_error(
            "market_mode_derived",
            str(symbol or "").upper(),
            category="mode",
            level="INFO",
            source="fetch_live_market_data",
            details={
                "now_ist": cycle_cutoff.isoformat(),
                "segment": segment,
                "mode": str(market_ctx.mode),
                "market_open": bool(market_ctx.is_market_open),
            },
        )
        offhours_mode = market_ctx.mode == "OFFHOURS"
        require_live_quotes = bool(market_ctx.require_live_quotes and getattr(cfg, "REQUIRE_LIVE_QUOTES", True))
        ltp = get_ltp(symbol)
        ltp_source = _DATA_CACHE.get(symbol, {}).get("ltp_source", "none")
        ltp_ts_epoch = _DATA_CACHE.get(symbol, {}).get("ltp_ts_epoch")
        use_sub = getattr(cfg, "DEPTH_WS_USE_SUBPROCESS", False) or getattr(cfg, "FEED_USE_SUBPROCESS", False)
        if use_sub or ltp_ts_epoch is None:
            try:
                from core.tick_store import get_last_tick
                token = get_token_for_symbol(symbol)
                if token:
                    tick = get_last_tick(token)
                    if tick and tick.get("ltp"):
                        if ltp is None or ltp <= 0:
                            ltp = tick.get("ltp")
                        ltp_ts_epoch = tick.get("ts_epoch")
                        ltp_source = "tick_store"
            except Exception:
                pass
        try:
            if ltp is not None and float(ltp) > 0:
                from core.reject_shadow import record_price_trace

                record_price_trace(
                    symbol=symbol,
                    price=ltp,
                    ts_epoch=ltp_ts_epoch or cycle_cutoff_epoch,
                    mode=market_ctx.mode,
                    instrument_id=None,
                )
        except Exception:
            pass
        if require_live_quotes and market_ctx.is_market_open and (ltp is None or float(ltp) <= 0):
            results.append(
                {
                    "symbol": symbol,
                    "segment": segment,
                    "market_open": bool(market_ctx.is_market_open),
                    "offhours_mode": bool(offhours_mode),
                    "market_context": market_ctx.to_dict(),
                    "ltp": ltp,
                    "ltp_source": ltp_source,
                    "ltp_ts_epoch": ltp_ts_epoch,
                    "valid": False,
                    "invalid_reason": "invalid_ltp",
                    "invalid_reason_codes": ["invalid_ltp"],
                    "timestamp": cycle_cutoff_epoch,
                    "timestamp_ist": cycle_cutoff.isoformat(),
                    "instrument": "OPT",
                    "feed_health": {
                        "time_sanity": {
                            "ok": False,
                            "reasons": ["invalid_ltp"],
                            "ltp_ts_epoch": ltp_ts_epoch,
                            "candle_ts_epoch": None,
                            "market_open": market_ctx.is_market_open,
                            "require_live_quotes": bool(require_live_quotes),
                        }
                    },
                }
            )
            continue
        try:
            if ltp and ltp > 0:
                live_source_type = "tick_store_live" if str(ltp_source) == "tick_store" else ("live_websocket" if str(ltp_source) == "live" else "unknown")
                ohlc_buffer.update_tick(
                    symbol,
                    ltp,
                    volume=None,
                    ts=cycle_cutoff,
                    provenance={
                        "source_type": live_source_type,
                        "live_feed_session_id": os.getenv("LIVE_FEED_SESSION_ID", ""),
                        "historical_seed": False,
                        "replay_fixture": False,
                        "non_live_fallback": False,
                        "recovered_synthetic": False,
                    },
                )
        except Exception:
            pass
        vwap = ltp
        cross_feat = {}
        cross_quality = {}
        try:
            cross_payload = _CROSS_ASSET.update(symbol, ltp) or {}
            cross_feat = cross_payload.get("features", {}) or {}
            cross_quality = cross_payload.get("data_quality", {}) or {}
        except Exception as e:
            cross_feat = {}
            cross_quality = {"any_stale": True, "disabled": True, "disabled_reason": "cross_asset_exception", "errors": {"error": str(e)}}

        fx_ret_5m = cross_feat.get("x_usdinr_ret5") or cross_feat.get("x_fx_ret5")
        vix_z = cross_feat.get("x_india_vix_z") or cross_feat.get("x_vix_z")
        crude_ret_15m = cross_feat.get("x_crude_ret15") or cross_feat.get("x_crudeoil_ret15")
        corr_fx_nifty = cross_feat.get("x_usdinr_corr_nifty")
        atr = max(1.0, ltp * 0.002)
        # minutes since open (used for ORB bias + day-type)
        try:
            minutes_since_open = session_minutes_since_open(now_dt=cycle_cutoff, segment=segment)
            is_market_open = is_open(now_dt=cycle_cutoff, segment=segment)
            today_local = cycle_cutoff.date()
        except Exception:
            minutes_since_open = 0
            is_market_open = True
            today_local = cycle_cutoff.date()
        try:
            last_day = _DAYTYPE_LAST_DAY.get(symbol)
            if last_day != today_local:
                _DAYTYPE_LOCK.pop(symbol, None)
                _DAYTYPE_LAST.pop(symbol, None)
                _DAYTYPE_LAST_DAY[symbol] = today_local
        except Exception:
            pass
        orb_high = ltp
        orb_low = ltp
        volume = None
        vwap_slope = 0
        rsi = None
        ema = None
        rsi_mom = 0
        vol_z = 0
        adx_14 = 0
        ltp_change = 0.0
        ltp_change_window = 0.0
        ltp_change_5m = 0.0
        ltp_change_10m = 0.0
        ltp_acceleration = 0.0

        # Compute indicators from rolling OHLC buffer (no CSV dependency)
        indicators_ok = False
        indicator_inputs_ok = False
        now_epoch_for_indicators = float(cycle_cutoff_epoch)
        indicators_age_sec = float(getattr(cfg, "INDICATORS_NEVER_COMPUTED_AGE_SEC", 1e9))
        candle_ts_epoch = None
        indicator_last_update_epoch = _INDICATOR_LAST_UPDATE_EPOCH.get(symbol)
        ohlc_bars_count = 0
        min_bars = int(getattr(cfg, "OHLC_MIN_BARS", 30))
        ohlc_seeded = False
        ohlc_last_bar_epoch = None
        compute_indicators_error = None
        missing_inputs = []
        ohlc_seed_reason = None
        bars = []
        try:
            bars = ohlc_buffer.get_completed_bars(symbol, as_of=cycle_cutoff)
            if len(bars) < min_bars and bool(allow_history_seed):
                startup_degraded_row = _startup_hist_empty_degraded_row(symbol)
                if (
                    startup_degraded_row
                    and bool(market_ctx.allow_stale_quotes)
                    and bool(getattr(cfg, "NONLIVE_SKIP_HISTORY_SEED_AFTER_STARTUP_DEGRADE", True))
                ):
                    ohlc_seed_reason = "HIST_FETCH_FAILED"
                    ohlc_seeded = False
                    logger.warning(
                        "warm_seed_skip_after_startup_degrade symbol=%s reason=hist_empty_nonlive attempts=%s",
                        symbol,
                        startup_degraded_row.get("warmup_degraded_attempts"),
                    )
                else:
                    bars, _seeded_ok, ohlc_seed_reason = _warm_seed_ohlc_from_history(
                        symbol=symbol,
                        bars=bars,
                        min_bars=min_bars,
                        as_of=cycle_cutoff,
                        interval=str(getattr(cfg, "OHLC_WARM_SEED_INTERVAL", "minute") or "minute"),
                        market_mode=market_ctx.mode,
                    )
                    ohlc_seeded = bool(_seeded_ok)
            elif len(bars) < min_bars:
                logger.info(
                    "fetch_live_market_data warm_seed_skipped symbol=%s bars=%d min_bars=%d allow_history_seed=%s",
                    symbol,
                    len(bars),
                    min_bars,
                    bool(allow_history_seed),
                )
            ohlc_bars_count = len(bars)
            if bars:
                try:
                    ohlc_last_bar_epoch = float(bars[-1].get("ts").timestamp())
                except Exception:
                    ohlc_last_bar_epoch = None
            if isinstance(indicator_last_update_epoch, (int, float)):
                indicator_last_update_epoch = float(indicator_last_update_epoch)
            elif ohlc_last_bar_epoch is not None:
                indicator_last_update_epoch = float(ohlc_last_bar_epoch)
            else:
                indicator_last_update_epoch = 0.0
            if ohlc_bars_count == 0:
                missing_inputs.append("ohlc_buffer_empty")
            elif ohlc_bars_count < min_bars:
                missing_inputs.append("insufficient_bars")
            ind = compute_indicators(
                bars,
                vwap_window=getattr(cfg, "VWAP_WINDOW", 20),
                atr_period=getattr(cfg, "ATR_PERIOD", 14),
                adx_period=getattr(cfg, "ADX_PERIOD", 14),
                vol_window=getattr(cfg, "VOL_WINDOW", 30),
                slope_window=getattr(cfg, "VWAP_SLOPE_WINDOW", 10),
            )
            if ind.get("vwap") is not None:
                vwap = ind["vwap"]
            if ind.get("atr") is not None:
                atr = ind["atr"]
            if ind.get("adx") is not None:
                adx_14 = ind["adx"]
            if ind.get("vol_z") is not None:
                vol_z = ind["vol_z"]
            if ind.get("vwap_slope") is not None:
                vwap_slope = ind["vwap_slope"]
            if ind.get("rsi") is not None:
                rsi = ind["rsi"]
            if ind.get("ema") is not None:
                ema = ind["ema"]
            last_ts = ind.get("last_ts")
            bars_ready = bool(ohlc_bars_count >= min_bars and ohlc_bars_count > 0)
            indicator_inputs_ok = bars_ready
            if last_ts:
                try:
                    candle_ts_epoch = float(last_ts.timestamp())
                except Exception:
                    candle_ts_epoch = None
            if bars_ready:
                # Successful indicator compute: always refresh last update epoch.
                indicator_last_update_epoch = (
                    candle_ts_epoch
                    if candle_ts_epoch is not None
                    else (ohlc_last_bar_epoch if ohlc_last_bar_epoch is not None else now_epoch_for_indicators)
                )
                _INDICATOR_LAST_UPDATE_EPOCH[symbol] = float(indicator_last_update_epoch)
            else:
                if ohlc_bars_count == 0:
                    missing_inputs.append("never_computed")
            indicators_age = compute_age_sec(indicator_last_update_epoch, now_epoch_for_indicators)
            indicators_age_sec = float(
                indicators_age
                if indicators_age is not None
                else getattr(cfg, "INDICATORS_NEVER_COMPUTED_AGE_SEC", 1e9)
            )
            indicators_ok = bool(bars_ready)
        except Exception as exc:
            indicators_ok = False
            indicator_inputs_ok = False
            if not isinstance(indicator_last_update_epoch, (int, float)):
                indicator_last_update_epoch = 0.0
            indicators_age = compute_age_sec(indicator_last_update_epoch, now_epoch_for_indicators)
            indicators_age_sec = float(
                indicators_age
                if indicators_age is not None
                else getattr(cfg, "INDICATORS_NEVER_COMPUTED_AGE_SEC", 1e9)
            )
            compute_indicators_error = f"{type(exc).__name__}:{exc}"
            missing_inputs.append("compute_indicators_exception")
            if float(indicator_last_update_epoch) <= 0.0:
                missing_inputs.append("indicators_never_computed")
                missing_inputs.append("never_computed")
        if str(ohlc_seed_reason or "").upper() == "HIST_FETCH_FAILED":
            missing_inputs = ["HIST_FETCH_FAILED"]
        missing_inputs = list(dict.fromkeys(str(x) for x in missing_inputs if x))

        # Cross-asset data quality fail-safe (only in LIVE when required)
        try:
            live_mode = str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper() == "LIVE"
            require_x = bool(getattr(cfg, "REQUIRE_CROSS_ASSET", True))
            if getattr(cfg, "REQUIRE_CROSS_ASSET_ONLY_WHEN_LIVE", True):
                require_x = require_x and live_mode
            if require_x:
                required_stale = set(cross_quality.get("required_stale", []) or [])
                missing = set((cross_quality.get("missing") or {}).keys())
                required = set(getattr(cfg, "CROSS_REQUIRED_FEEDS", []) or [])
                if not required_stale and required:
                    required_stale = (missing & required)
                if required_stale:
                    indicators_ok = False
        except Exception:
            pass

        # lightweight momentum if no indicators available
        prev = _DATA_CACHE.get(symbol, {}).get("last_ltp")
        if prev:
            ltp_change = float(ltp - prev)
        _DATA_CACHE.setdefault(symbol, {})["last_ltp"] = ltp

        # rolling window change (default 60s)
        try:
            win_sec = getattr(cfg, "LTP_CHANGE_WINDOW_SEC", 60)
            win_5m = getattr(cfg, "MICRO_5M_SEC", 300)
            win_10m = getattr(cfg, "MICRO_10M_SEC", 600)
            hist = _LTP_HISTORY.get(symbol)
            if hist is None:
                hist = deque(maxlen=300)
                _LTP_HISTORY[symbol] = hist
            now_ts = cycle_cutoff_epoch
            hist.append((now_ts, ltp))
            # find oldest within window
            for ts, price in list(hist):
                if now_ts - ts >= win_sec:
                    ltp_change_window = float(ltp - price)
                    break
            for ts, price in list(hist):
                if now_ts - ts >= win_5m:
                    ltp_change_5m = float(ltp - price)
                    break
            for ts, price in list(hist):
                if now_ts - ts >= win_10m:
                    ltp_change_10m = float(ltp - price)
                    break
            # simple acceleration from last 3 points
            if len(hist) >= 3:
                p0 = hist[-1][1]
                p1 = hist[-2][1]
                p2 = hist[-3][1]
                ltp_acceleration = float(p0 - 2 * p1 + p2)
        except Exception:
            pass

        # Index quote path:
        # - Prefer real bid/ask from WS/REST depth.
        # - For index symbols only, synthesize around LTP when depth is missing.
        # - Never synthesize option-chain quotes.
        bid = None
        ask = None
        mid = None
        bid_qty = None
        ask_qty = None
        quote_ok = False
        quote_ts = None
        quote_ts_epoch = None
        quote_age_sec = None
        spread_pct = None
        quote_source = "none"
        synthetic_index_quote = False
        ws_quote = get_index_quote_snapshot(symbol)
        if ws_quote:
            try:
                bid = ws_quote.get("bid")
                ask = ws_quote.get("ask")
                mid = ws_quote.get("mid")
                if mid is None and bid is not None and ask is not None:
                    mid = (float(bid) + float(ask)) / 2.0
                quote_ts_epoch = float(ws_quote.get("ts_epoch")) if ws_quote.get("ts_epoch") is not None else None
                if ltp_source == "live" and ws_quote.get("last_price") is not None:
                    try:
                        ltp = float(ws_quote.get("last_price"))
                    except Exception:
                        pass
                if quote_ts_epoch is not None:
                    quote_ts = datetime.fromtimestamp(float(quote_ts_epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")
                    quote_age_sec = compute_age_sec(quote_ts_epoch, cycle_cutoff_epoch)
                if bid and ask:
                    quote_ok = True
                    quote_source = "depth"
                    if ltp:
                        spread_pct = (ask - bid) / ltp
            except Exception:
                quote_ok = False
        if not quote_ok:
            _refresh_index_quote_from_rest(symbol, force=False)
            ws_quote = get_index_quote_snapshot(symbol)
            if ws_quote:
                try:
                    bid = ws_quote.get("bid")
                    ask = ws_quote.get("ask")
                    mid = ws_quote.get("mid")
                    if mid is None and bid is not None and ask is not None:
                        mid = (float(bid) + float(ask)) / 2.0
                    quote_ts_epoch = float(ws_quote.get("ts_epoch")) if ws_quote.get("ts_epoch") is not None else None
                    quote_source = str(ws_quote.get("source") or "rest_quote")
                    if ltp_source == "live" and ws_quote.get("last_price") is not None:
                        try:
                            ltp = float(ws_quote.get("last_price"))
                        except Exception:
                            pass
                    if quote_ts_epoch is not None:
                        quote_ts = datetime.fromtimestamp(float(quote_ts_epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")
                        quote_age_sec = compute_age_sec(quote_ts_epoch, cycle_cutoff_epoch)
                        if ltp_source == "live":
                            ltp_ts_epoch = quote_ts_epoch
                    if bid and ask:
                        quote_ok = True
                        quote_source = "depth"
                        if ltp:
                            spread_pct = (ask - bid) / ltp
                except Exception:
                    quote_ok = False
        if is_index(symbol):
            exec_mode = str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper()
            ltp_age_for_quote = compute_age_sec(ltp_ts_epoch, cycle_cutoff_epoch)
            resolved_quote = resolve_index_quote(
                symbol=symbol,
                mode=exec_mode,
                ltp=ltp,
                depth={"bid": bid, "ask": ask},
                market_open=bool(market_ctx.is_market_open),
                ltp_age_sec=ltp_age_for_quote,
                market_context=market_ctx.to_dict(),
            )
            bid = resolved_quote.get("bid")
            ask = resolved_quote.get("ask")
            mid = resolved_quote.get("mid")
            quote_ok = bool(resolved_quote.get("quote_ok", False))
            quote_source = str(resolved_quote.get("quote_source") or "missing_depth")
            synthetic_index_quote = quote_source == "synthetic_index"
            if quote_ok:
                if quote_ts_epoch is None:
                    if isinstance(ltp_ts_epoch, (int, float)):
                        quote_ts_epoch = float(ltp_ts_epoch)
                    else:
                        quote_ts_epoch = cycle_cutoff_epoch
                quote_ts = datetime.fromtimestamp(float(quote_ts_epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")
                quote_age_sec = compute_age_sec(float(quote_ts_epoch), cycle_cutoff_epoch)
                if ltp:
                    spread_pct = (ask - bid) / ltp
        if quote_ts_epoch is not None:
            update_index_quote_snapshot(
                symbol=symbol,
                bid=bid,
                ask=ask,
                mid=mid,
                ts_epoch=quote_ts_epoch,
                source=quote_source,
                ltp=ltp,
            )
        if is_index(symbol):
            _maybe_log_index_bidask_missing(
                symbol,
                quote_ok=bool(quote_ok),
                quote_source=quote_source,
                ltp_source=ltp_source,
                market_open=bool(market_ctx.is_market_open),
                ltp=ltp,
                ltp_age_sec=ltp_age_for_quote,
            )
        index_quote_cache = dict(get_index_quote_snapshot(symbol) or {})
        quote_feed_health = None
        if is_index(symbol):
            quote_feed_health = _classify_index_feed_health(
                symbol=symbol,
                execution_mode=str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper(),
                now_epoch=cycle_cutoff_epoch,
                market_open=bool(market_ctx.is_market_open),
                ltp=ltp,
                ltp_ts_epoch=ltp_ts_epoch,
                quote_ok=bool(quote_ok),
                quote_source=quote_source,
                quote_ts_epoch=quote_ts_epoch,
            )

        time_sanity = check_market_data_time_sanity(
            ltp_ts_epoch=ltp_ts_epoch,
            candle_ts_epoch=candle_ts_epoch,
            market_open=market_ctx.is_market_open,
            require_live_quotes=bool(require_live_quotes),
            max_ltp_age_sec=getattr(
                cfg,
                "OFFHOURS_MAX_LTP_AGE_SEC" if offhours_mode else "MAX_LTP_AGE_SEC",
                900 if offhours_mode else 8,
            ),
            max_candle_age_sec=getattr(
                cfg,
                "OFFHOURS_MAX_CANDLE_AGE_SEC" if offhours_mode else "MAX_CANDLE_AGE_SEC",
                1800 if offhours_mode else 120,
            ),
            now_epoch=cycle_cutoff_epoch,
        )
        if synthetic_index_quote:
            quote_ok = bool(time_sanity.get("ok", False) and ltp is not None and float(ltp) > 0)
            if not quote_ok:
                quote_source = "none"
        if not time_sanity.get("ok", True):
            reasons = list(time_sanity.get("reasons", []) or [])
            invalid_reason = "|".join(reasons) if reasons else "timestamp_stale"
            results.append(
                {
                    "symbol": symbol,
                    "segment": segment,
                    "market_open": bool(market_ctx.is_market_open),
                    "offhours_mode": bool(offhours_mode),
                    "market_context": market_ctx.to_dict(),
                    "ltp": ltp,
                    "ltp_source": ltp_source,
                    "ltp_ts_epoch": ltp_ts_epoch,
                    "valid": False,
                    "invalid_reason": invalid_reason,
                    "invalid_reason_codes": reasons,
                    "quote_source": quote_source,
                    "quote_ts": quote_ts,
                    "quote_ts_epoch": quote_ts_epoch,
                    "quote_age_sec": quote_age_sec,
                    "candle_ts_epoch": candle_ts_epoch,
                    "timestamp": cycle_cutoff_epoch,
                    "timestamp_ist": cycle_cutoff.isoformat(),
                    "instrument": "OPT",
                    "feed_health": {"time_sanity": time_sanity},
                    "quote_health": quote_feed_health,
                }
            )
            continue

        # Candle-based ORB tracking (first ORB window candles + close break confirmation)
        orb_lock_min = int(getattr(cfg, "ORB_WINDOW_MIN", getattr(cfg, "ORB_LOCK_MIN", 15)))
        orb_bias = "NEUTRAL"
        orb_state = {
            "symbol": symbol,
            "window_min": orb_lock_min,
            "orb_high": None,
            "orb_low": None,
            "bias": orb_bias,
            "status": "PENDING",
            "window_bars": 0,
            "required_bars": orb_lock_min,
        }
        try:
            orb_state = _orb_state_from_candles(
                symbol,
                bars,
                now_dt=cycle_cutoff,
                segment=segment,
                market_open=bool(is_market_open),
                market_mode=market_ctx.mode,
            )
            orb_bias = str(orb_state.get("bias") or "NEUTRAL").upper()
            orb_lock_min = int(orb_state.get("window_min") or orb_lock_min)
        except Exception:
            orb_bias = "NEUTRAL"
        orb_high = _as_bar_float(orb_state.get("orb_high"))
        orb_low = _as_bar_float(orb_state.get("orb_low"))
        if orb_high is None:
            orb_high = ltp
        if orb_low is None:
            orb_low = ltp

        market_open_now = bool(market_ctx.is_market_open)
        option_chain = _fetch_option_chain_with_context(
            symbol,
            ltp,
            force_synthetic=False,
            market_context=market_ctx.to_dict(),
        )
        chain_source = "live" if option_chain else "empty"
        if (not market_open_now) and (not option_chain) and getattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False):
            option_chain = _fetch_option_chain_with_context(
                symbol,
                ltp,
                force_synthetic=True,
                market_context=market_ctx.to_dict(),
            )
            chain_source = "synthetic_offhours" if option_chain else "empty"
        elif market_open_now and (not option_chain) and getattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False):
            _log_market_data_event(
                "SYNTHETIC_OFFHOURS_BLOCKED_MARKET_OPEN",
                {
                    "symbol": symbol,
                    "mode": str(market_ctx.mode),
                    "market_open": True,
                    "reason": "synthetic_offhours_disabled_when_market_open",
                },
            )
        if market_open_now and option_chain and chain_source == "synthetic_offhours":
            _log_market_data_event(
                "SYNTHETIC_OFFHOURS_CHAIN_DROPPED_MARKET_OPEN",
                {
                    "symbol": symbol,
                    "mode": str(market_ctx.mode),
                    "market_open": True,
                    "reason": "synthetic_offhours_not_allowed_when_market_open",
                    "rows": len(option_chain),
                },
            )
            option_chain = []
            chain_source = "empty"
        if option_chain and chain_source == "synthetic_offhours":
            for opt in option_chain:
                if isinstance(opt, dict):
                    opt["chain_source"] = "synthetic_offhours"
                    opt["planning_only"] = True
        option_chain = _hydrate_live_option_chain_liquidity(
            symbol,
            option_chain,
            chain_source=chain_source,
            now_epoch=cycle_cutoff_epoch,
        )
        # Option chain health validation (live NFO/BFO)
        try:
            health = _option_chain_health(
                symbol,
                option_chain,
                ltp,
                require_live_quotes=require_live_quotes,
            )
            health_path = logs_dir() / "option_chain_health.json"
            health_path.parent.mkdir(exist_ok=True)
            existing = {}
            if health_path.exists():
                try:
                    existing = json.loads(health_path.read_text())
                except Exception:
                    existing = {}
            existing[symbol] = health
            health_path.write_text(json.dumps(existing, indent=2))
        except Exception:
            health = None

        # Depth age (use latest depth snapshot for option tokens if available)
        depth_age_sec = None
        try:
            latest_depth_ts = None
            for opt in option_chain:
                token = opt.get("instrument_token")
                if token is None:
                    continue
                book = depth_store.get(token) or {}
                ts_epoch = book.get("ts_epoch") or book.get("ts")
                if ts_epoch is not None:
                    latest_depth_ts = ts_epoch if latest_depth_ts is None else max(latest_depth_ts, float(ts_epoch))
            if latest_depth_ts is not None:
                depth_age_sec = compute_age_sec(float(latest_depth_ts), cycle_cutoff_epoch)
        except Exception:
            depth_age_sec = None

        # Regime model (probabilistic)
        try:
            iv_vals = [c.get("iv") for c in option_chain if c.get("iv") is not None]
            iv_mean = sum(iv_vals) / len(iv_vals) if iv_vals else 0
        except Exception:
            iv_mean = 0
        # option chain skew (call iv - put iv)
        try:
            call_ivs = [c.get("iv") for c in option_chain if c.get("iv") is not None and c.get("type") == "CE"]
            put_ivs = [c.get("iv") for c in option_chain if c.get("iv") is not None and c.get("type") == "PE"]
            call_mean = sum(call_ivs) / len(call_ivs) if call_ivs else 0
            put_mean = sum(put_ivs) / len(put_ivs) if put_ivs else 0
            option_chain_skew = (call_mean - put_mean)
        except Exception:
            option_chain_skew = 0
        # OI delta (calls - puts)
        try:
            call_oi = sum([c.get("oi_change", 0) or 0 for c in option_chain if c.get("type") == "CE"])
            put_oi = sum([c.get("oi_change", 0) or 0 for c in option_chain if c.get("type") == "PE"])
            oi_delta = float(call_oi - put_oi)
        except Exception:
            oi_delta = 0.0
        # Depth imbalance from option chain quotes
        try:
            bid_qty_sum = sum([c.get("bid_qty", 0) or 0 for c in option_chain])
            ask_qty_sum = sum([c.get("ask_qty", 0) or 0 for c in option_chain])
            denom = max(bid_qty_sum + ask_qty_sum, 1)
            depth_imbalance = (bid_qty_sum - ask_qty_sum) / denom
        except Exception:
            depth_imbalance = 0.0

        nonlive_feature_fallback = False
        nonlive_feature_fallback_fields: list[str] = []
        nonlive_feature_fallback_reason = None
        nonlive_feature_fallback_signal_hint = 0.0
        nonlive_feature_fallback_strength_basis = 0.0
        fallback_snapshot, fallback_fields = _apply_nonlive_feature_fallback(
            symbol,
            {
                "symbol": symbol,
                "ltp": ltp,
                "prev_ltp": prev,
                "vwap": vwap,
                "atr": atr,
                "ltp_change": ltp_change,
                "ltp_change_window": ltp_change_window,
                "ltp_change_5m": ltp_change_5m,
                "ltp_change_10m": ltp_change_10m,
                "rsi_mom": rsi_mom,
                "vol_z": vol_z,
                "macro_direction_bias": shock.get("macro_direction_bias"),
                "depth_imbalance": depth_imbalance,
                "option_chain_skew": option_chain_skew,
                "oi_delta": oi_delta,
                "warmup_reason": "HIST_FETCH_FAILED" if str(ohlc_seed_reason or "").upper() == "HIST_FETCH_FAILED" else None,
                "ohlc_seed_reason": ohlc_seed_reason,
                "warmup_degraded_detail": str((_startup_hist_empty_degraded_row(symbol) or {}).get("warmup_degraded_detail") or ""),
            },
            market_mode=market_ctx.mode,
            allow_stale_quotes=bool(market_ctx.allow_stale_quotes),
            degraded_reason=("HIST_FETCH_FAILED" if str(ohlc_seed_reason or "").upper() == "HIST_FETCH_FAILED" else None),
        )
        if fallback_fields:
            atr = float(fallback_snapshot.get("atr") or atr or 0.0)
            vwap = float(fallback_snapshot.get("vwap") or vwap or ltp or 0.0)
            ltp_change_window = float(fallback_snapshot.get("ltp_change_window") or ltp_change_window or 0.0)
            ltp_change_5m = float(fallback_snapshot.get("ltp_change_5m") or ltp_change_5m or 0.0)
            ltp_change_10m = float(fallback_snapshot.get("ltp_change_10m") or ltp_change_10m or 0.0)
            rsi_mom = float(fallback_snapshot.get("rsi_mom") or rsi_mom or 0.0)
            vol_z = float(fallback_snapshot.get("vol_z") or vol_z or 0.0)
            nonlive_feature_fallback = True
            nonlive_feature_fallback_fields = list(dict.fromkeys(str(field) for field in fallback_fields if str(field)))
            nonlive_feature_fallback_reason = str(fallback_snapshot.get("nonlive_feature_fallback_reason") or "hist_fetch_failed")
            nonlive_feature_fallback_signal_hint = float(fallback_snapshot.get("nonlive_feature_fallback_signal_hint") or 0.0)
            nonlive_feature_fallback_strength_basis = float(fallback_snapshot.get("nonlive_feature_fallback_strength_basis") or 0.0)
            logger.warning(
                "nonlive_feature_fallback_applied symbol=%s fields=%s signal_hint=%s",
                symbol,
                nonlive_feature_fallback_fields,
                nonlive_feature_fallback_signal_hint,
            )
            _log_market_data_event(
                "nonlive_feature_fallback_applied",
                {
                    "symbol": symbol,
                    "fields": list(nonlive_feature_fallback_fields),
                    "market_mode": str(market_ctx.mode),
                    "reason": nonlive_feature_fallback_reason,
                    "signal_hint": round(nonlive_feature_fallback_signal_hint, 6),
                    "strength_basis": round(nonlive_feature_fallback_strength_basis, 6),
                },
            )

        atr_pct = (atr / ltp) if ltp else 0

        # regime transition rate (per hour)
        try:
            trans = _REGIME_TRANSITIONS.get(symbol)
            if trans is None:
                trans = deque(maxlen=2000)
                _REGIME_TRANSITIONS[symbol] = trans
        except Exception:
            trans = None

        features = {
            "adx": adx_14,
            "vwap_slope": vwap_slope,
            "vol_z": vol_z,
            "atr_pct": atr_pct,
            "iv_mean": iv_mean,
            "ltp_acceleration": ltp_acceleration,
            "option_chain_skew": option_chain_skew,
            "oi_delta": oi_delta,
            "depth_imbalance": depth_imbalance,
            "regime_transition_rate": 0.0,
            "shock_score": shock.get("shock_score"),
            "uncertainty_index": shock.get("uncertainty_index"),
            "macro_direction_bias": shock.get("macro_direction_bias"),
            "x_regime_align": cross_feat.get("x_regime_align"),
            "x_vol_spillover": cross_feat.get("x_vol_spillover"),
            "x_lead_lag": cross_feat.get("x_lead_lag"),
            "x_index_ret1": cross_feat.get("x_index_ret1"),
            "x_index_ret5": cross_feat.get("x_index_ret5"),
        }
        regime_ts, regime_ts_source = resolve_regime_event_timestamp(
            explicit_timestamp=quote_ts if quote_ts is not None else ltp_ts_epoch,
            source_timestamp=ltp_ts_epoch,
            last_bar_timestamp=candle_ts_epoch if candle_ts_epoch is not None else ohlc_last_bar_epoch,
            replay_timestamp=fallback_snapshot.get("regime_ts") if isinstance(fallback_snapshot, dict) else None,
        )
        regime_probs = {}
        primary_regime = None
        regime_entropy = 0.0
        model_unstable_flag = False
        unstable_reasons = []
        regime_reasons = []
        regime_confidence = None
        try:
            model_out = _REGIME_MODEL.predict(features)
            regime_probs = dict(model_out.get("regime_probs", {}) or {})
            raw_primary = model_out.get("primary_regime")
            primary_regime = str(raw_primary).upper().strip() if raw_primary else None
            regime_entropy = float(model_out.get("regime_entropy", 0.0) or 0.0)
            model_unstable_flag = bool(model_out.get("unstable_regime_flag", False))
        except Exception:
            regime_probs = {}
            primary_regime = None
            regime_entropy = 0.0
            model_unstable_flag = False
            regime_reasons.append("indicator_nan")

        if int(ohlc_bars_count) < int(min_bars):
            regime_reasons.append("warmup_incomplete")
        if int(ohlc_bars_count) <= 0 or ("ohlc_buffer_empty" in set(missing_inputs)):
            regime_reasons.append("missing_ohlc")
        feature_values = [
            features.get("adx"),
            features.get("vwap_slope"),
            features.get("vol_z"),
            features.get("atr_pct"),
            features.get("iv_mean"),
            features.get("ltp_acceleration"),
            features.get("option_chain_skew"),
            features.get("oi_delta"),
            features.get("depth_imbalance"),
        ]
        if any((v is not None) and (not _is_finite_number(v)) for v in feature_values):
            regime_reasons.append("indicator_nan")
        indicator_stale_sec = float(getattr(cfg, "INDICATOR_STALE_SEC", 120.0))
        if candle_ts_epoch is None:
            regime_reasons.append("stale_last_candle")
        else:
            try:
                candle_age = max(0.0, float(now_epoch_for_indicators) - float(candle_ts_epoch))
            except Exception:
                candle_age = indicator_stale_sec + 1.0
            if candle_age > indicator_stale_sec:
                regime_reasons.append("stale_last_candle")

        if regime_probs:
            try:
                regime_confidence = max(float(v) for v in regime_probs.values())
            except Exception:
                regime_confidence = None

        # Update transition rate
        try:
            last_primary = _REGIME_LAST_PRIMARY.get(symbol)
            if last_primary and primary_regime != last_primary and trans is not None:
                trans.append(time.time())
            if primary_regime:
                _REGIME_LAST_PRIMARY[symbol] = primary_regime
            if trans is not None:
                now = time.time()
                window = 3600
                trans = deque([t for t in trans if now - t <= window], maxlen=2000)
                _REGIME_TRANSITIONS[symbol] = trans
                regime_transition_rate = len(trans) / (window / 3600.0)
            else:
                regime_transition_rate = 0.0
        except Exception:
            regime_transition_rate = 0.0

        features["regime_transition_rate"] = regime_transition_rate

        regime = str(primary_regime).upper().strip() if primary_regime else None

        # time to expiry (hours)
        time_to_expiry_hrs = None
        try:
            expiry = None
            if option_chain:
                expiry = option_chain[0].get("expiry")
            if expiry:
                from datetime import datetime as dt
                exp_dt = dt.fromisoformat(str(expiry))
                time_to_expiry_hrs = max(0.0, (exp_dt - cycle_cutoff).total_seconds() / 3600.0)
        except Exception:
            time_to_expiry_hrs = None

        # Force regime override (for testing)
        force = getattr(cfg, "FORCE_REGIME", "")
        if isinstance(force, str) and force.strip():
            forced_regime = force.strip().upper()
            regime = forced_regime
            primary_regime = forced_regime
            regime_reasons = []
            regime_confidence = 1.0
        regime_reasons = list(dict.fromkeys(str(x) for x in regime_reasons if str(x).strip()))
        if (not indicators_ok) or (not regime) or regime_reasons:
            regime = "UNKNOWN"
            primary_regime = "UNKNOWN"
            regime_probs = {}
            regime_entropy = 0.0
            regime_confidence = None
        unstable_reasons = _derive_unstable_reasons(
            regime_probs=regime_probs,
            regime_entropy=regime_entropy,
            regime_transition_rate=regime_transition_rate,
            indicators_ok=indicators_ok,
            ohlc_bars_count=ohlc_bars_count,
            min_bars=min_bars,
            missing_inputs=missing_inputs,
            model_unstable_flag=model_unstable_flag,
            primary_regime=primary_regime,
            symbol=symbol,
            segment=segment,
            timestamp_ist=regime_ts,
        )
        unstable_regime_flag = bool(unstable_reasons)
        session_bucket = _resolve_market_session_bucket(segment=segment, timestamp_ist=regime_ts)

        warmup_min_bars = int(getattr(cfg, "SYSTEM_WARMUP_MIN_BARS", min_bars))
        warmup_bars_by_timeframe = {"1m": int(ohlc_bars_count)}
        warmup_min_bars_by_timeframe = {"1m": int(warmup_min_bars)}
        indicator_last_ok = isinstance(indicator_last_update_epoch, (int, float)) and float(indicator_last_update_epoch) > 0.0
        warmup_reasons = []
        if ohlc_bars_count < warmup_min_bars:
            warmup_reasons.append(f"bars_below_min:1m:{ohlc_bars_count}/{warmup_min_bars}")
        if not indicator_last_ok:
            warmup_reasons.append("indicator_last_update_missing")
        elif isinstance(indicators_age_sec, (int, float)) and float(indicators_age_sec) > indicator_stale_sec:
            warmup_reasons.append(
                f"indicator_last_update_stale:{float(indicators_age_sec):.1f}s>{indicator_stale_sec:.1f}s"
            )
        if not bool(indicators_ok):
            warmup_reasons.append("indicators_not_ready")
        if regime == "UNKNOWN":
            warmup_reasons.append("regime_missing")
        for reason in missing_inputs:
            if str(reason).upper() == "HIST_FETCH_FAILED":
                warmup_reasons.append("HIST_FETCH_FAILED")
            else:
                warmup_reasons.append(f"missing_input:{reason}")
        warmup_reasons = list(dict.fromkeys(warmup_reasons))
        if "HIST_FETCH_FAILED" in warmup_reasons:
            # Single explicit root-cause reason for UI/operator clarity.
            warmup_reasons = ["HIST_FETCH_FAILED"]
        hist_fetch_only = bool(warmup_reasons == ["HIST_FETCH_FAILED"])
        if hist_fetch_only and bool(market_ctx.allow_stale_quotes):
            system_state = "DEGRADED"
        else:
            system_state = "WARMUP" if warmup_reasons else "READY"
        warmup_status = (
            "DEGRADED" if (hist_fetch_only and bool(market_ctx.allow_stale_quotes))
            else ("WARMUP" if warmup_reasons else "READY")
        )

        # Day-type classifier (first 30–60 min decisive)
        day_type = "UNKNOWN"
        day_conf = 0.0
        try:
            minutes_since_open = int(minutes_since_open)
        except Exception:
            minutes_since_open = 0
        try:
            if not indicators_ok:
                day_type = "UNKNOWN"
                day_conf = 0.0
            else:
                atr_pct = (atr / ltp) if ltp else 0
                vwap_dist = (ltp - vwap) / vwap if vwap else 0
                # Expiry day heuristic
                exp_from_chain = None
                if option_chain:
                    try:
                        exp_from_chain = option_chain[0].get("expiry")
                    except Exception:
                        exp_from_chain = None
                if exp_from_chain:
                    try:
                        exp_dt = datetime.fromisoformat(str(exp_from_chain)).date()
                        if is_market_open and exp_dt == today_local:
                            day_type = "EXPIRY_DAY"
                    except Exception:
                        pass
                if day_type == "UNKNOWN":
                    weekday = today_local.weekday()
                    exp_map = getattr(cfg, "EXPIRY_WEEKDAY_BY_SYMBOL", {})
                    exp_day = exp_map.get(symbol.upper())
                    if exp_day is not None and weekday == exp_day and is_market_open:
                        day_type = "EXPIRY_DAY"
                if day_type == "UNKNOWN":
                    # Panic / liquidation
                    if vol_z >= 2.0 and atr_pct >= 0.008 and ltp_change_window < -atr * 0.5:
                        day_type = "PANIC_DAY"
                        day_conf = 0.9
                    # Event day
                    elif regime == "EVENT":
                        day_type = "EVENT_DAY"
                        day_conf = 0.8
                    # Trend day
                    elif adx_14 >= getattr(cfg, "TREND_ADX", 22) and abs(vwap_slope) > 0 and abs(vwap_dist) > getattr(cfg, "DAYTYPE_VWAP_DIST", 0.002):
                        day_type = "TREND_DAY"
                        day_conf = 0.7
                    # Range day
                    elif adx_14 < getattr(cfg, "RANGE_ADX", 18) and abs(vwap_dist) < getattr(cfg, "DAYTYPE_VWAP_DIST", 0.002):
                        day_type = "RANGE_DAY"
                        day_conf = 0.7
                    # Fake breakout (reversal in 5–10m)
                    elif (ltp_change_10m != 0) and (ltp_change_5m != 0) and (ltp_change_5m * ltp_change_10m < 0) and abs(ltp_change_10m) > atr * 0.2:
                        day_type = "FAKE_BREAKOUT_DAY"
                        day_conf = 0.6
                    # Trend → Range (morning move, afternoon flat)
                    elif minutes_since_open > 90 and abs(ltp_change_10m) > atr * 0.3 and abs(ltp_change_5m) < atr * 0.05:
                        day_type = "TREND_RANGE_DAY"
                        day_conf = 0.6
                    # Range → Trend (late breakout)
                    elif minutes_since_open > 120 and abs(ltp_change_10m) < atr * 0.15 and abs(ltp_change_5m) > atr * 0.25:
                        day_type = "RANGE_TREND_DAY"
                        day_conf = 0.6
                    # Range volatile
                    elif regime == "RANGE_VOLATILE":
                        day_type = "RANGE_VOLATILE"
                        day_conf = 0.55
        except Exception:
            day_type = "UNKNOWN"
            day_conf = 0.0

        # Re-enable expiry zero-hero on trend day (optional)
        try:
            if getattr(cfg, "ZERO_HERO_EXPIRY_REENABLE_ON_TREND", True) and day_type == "TREND_DAY":
                from strategies.trade_builder import TradeBuilder
                if hasattr(TradeBuilder, "_expiry_zero_hero_disabled_until"):
                    TradeBuilder._expiry_zero_hero_disabled_until = {}
        except Exception:
            pass

        # Lock day type after 60 minutes to avoid reclassification
        lock_after = getattr(cfg, "DAYTYPE_LOCK_MIN", 60)
        if getattr(cfg, "DAYTYPE_LOCK_ENABLE", True) and minutes_since_open >= lock_after:
            locked = _DAYTYPE_LOCK.get(symbol)
            if locked:
                day_type = locked.get("day_type", day_type)
                day_conf = locked.get("day_conf", day_conf)
            else:
                _DAYTYPE_LOCK[symbol] = {"day_type": day_type, "day_conf": day_conf, "locked_at": minutes_since_open}
                try:
                    append_day_type_event(
                        symbol=symbol,
                        event="LOCK",
                        day_type=day_type,
                        confidence=day_conf,
                        minutes_since_open=minutes_since_open,
                    )
                except Exception:
                    pass

        # Log day-type changes
        try:
            last = _DAYTYPE_LAST.get(symbol)
            if last != day_type:
                _DAYTYPE_LAST[symbol] = day_type
                append_day_type_event(
                    symbol=symbol,
                    event="CHANGE",
                    day_type=day_type,
                    confidence=day_conf,
                    minutes_since_open=minutes_since_open,
                )
        except Exception:
            pass

        # Periodic confidence heartbeat for chart accuracy
        try:
            now_ts = time.time()
            last_ts = _DAYTYPE_LAST_LOG.get(symbol, 0)
            every = getattr(cfg, "DAYTYPE_LOG_EVERY_SEC", 60)
            if now_ts - last_ts >= every:
                _DAYTYPE_LAST_LOG[symbol] = now_ts
                append_day_type_event(
                    symbol=symbol,
                    event="TICK",
                    day_type=day_type,
                    confidence=day_conf,
                    minutes_since_open=minutes_since_open,
                )
        except Exception:
            pass

        # Alert if confidence drops below threshold
        try:
            conf_min = getattr(cfg, "DAYTYPE_CONF_SWITCH_MIN", 0.6)
            if day_conf < conf_min:
                now_ts = time.time()
                last_ts = _DAYTYPE_ALERT_TS.get(symbol, 0)
                cooldown = getattr(cfg, "DAYTYPE_ALERT_COOLDOWN_SEC", 600)
                if now_ts - last_ts > cooldown:
                    _DAYTYPE_ALERT_TS[symbol] = now_ts
                    from core.telegram_alerts import send_telegram_message
                    send_telegram_message(
                        f"DayType alert: {symbol} confidence {day_conf:.2f} below {conf_min:.2f} (type={day_type})"
                    )
        except Exception:
            pass

        # Live-only: no CSV-based features or synthetic bid/ask
        seq_buffer = None
        htf_trend = 0
        htf_dir = "FLAT"

        # Confidence history for sparkline
        try:
            hist = _DAYTYPE_CONF_HISTORY.get(symbol)
            if hist is None:
                hist = deque(maxlen=60)
                _DAYTYPE_CONF_HISTORY[symbol] = hist
            hist.append(day_conf)
            conf_hist = list(hist)
        except Exception:
            conf_hist = []

        try:
            _LAST_REGIME_SNAPSHOT[str(symbol).upper()] = {
                "regime": regime,
                "primary_regime": primary_regime,
                "regime_confidence": regime_confidence,
                "regime_reasons": list(regime_reasons),
                "regime_probs": regime_probs,
                "regime_entropy": regime_entropy,
                "unstable_regime_flag": unstable_regime_flag,
                "unstable_reasons": list(unstable_reasons),
                "regime_ts": regime_ts,
                "regime_ts_source": regime_ts_source,
            }
        except Exception:
            pass

        results.append({
            "symbol": symbol,
            "market_open": bool(market_ctx.is_market_open),
            "offhours_mode": bool(offhours_mode),
            "market_context": market_ctx.to_dict(),
            "ltp": ltp,
            "ltp_source": ltp_source,
            "ltp_ts_epoch": ltp_ts_epoch,
            "valid": True,
            "invalid_reason": None,
            "segment": segment,
            "vwap": vwap,
            "rsi": rsi,
            "ema": ema,
            "bias": get_bias(ltp, vwap),
            "regime": regime,
            "primary_regime": primary_regime,
            "regime_confidence": regime_confidence,
            "regime_reasons": list(regime_reasons),
            "regime_probs": regime_probs,
            "regime_entropy": regime_entropy,
            "session_bucket": session_bucket,
            "regime_ts_source": regime_ts_source,
            "unstable_regime_flag": unstable_regime_flag,
            "unstable_reasons": list(unstable_reasons),
            "regime_transition_rate": regime_transition_rate,
            "regime_ts": regime_ts,
            "shock_score": shock.get("shock_score"),
            "macro_direction_bias": shock.get("macro_direction_bias"),
            "uncertainty_index": shock.get("uncertainty_index"),
            "event_name": shock.get("event_name"),
            "minutes_to_event": shock.get("minutes_to_event"),
            "event_category": shock.get("event_category"),
            "event_importance": shock.get("event_importance"),
            "fx_ret_5m": fx_ret_5m or 0.0,
            "vix_z": vix_z or 0.0,
            "crude_ret_15m": crude_ret_15m or 0.0,
            "corr_fx_nifty": corr_fx_nifty or 0.0,
            "cross_asset_ok": not bool(cross_quality.get("any_stale")),
            "cross_asset_quality": cross_quality,
            **cross_feat,
            "regime_day": regime,
            "day_type": day_type,
            "day_confidence": round(day_conf, 3),
            "day_conf_history": conf_hist,
            "indicators_ok": indicators_ok,
            "indicator_inputs_ok": indicator_inputs_ok,
            "indicators_age_sec": indicators_age_sec,
            "indicator_last_update_epoch": indicator_last_update_epoch,
            "ohlc_bars_count": ohlc_bars_count,
            "ohlc_seeded": bool(ohlc_seeded),
            "ohlc_seed_reason": ohlc_seed_reason,
            "ohlc_last_bar_epoch": ohlc_last_bar_epoch,
            "compute_indicators_error": compute_indicators_error,
            "missing_inputs": missing_inputs,
            "indicator_missing_inputs": missing_inputs,
            "system_state": system_state,
            "warmup_status": warmup_status,
            "warmup_degraded": bool(warmup_status == "DEGRADED"),
            "warmup_reasons": warmup_reasons,
            "warmup_min_bars": warmup_min_bars,
            "warmup_bars_by_timeframe": warmup_bars_by_timeframe,
            "warmup_min_bars_by_timeframe": warmup_min_bars_by_timeframe,
            "nonlive_feature_fallback": bool(nonlive_feature_fallback),
            "nonlive_feature_fallback_fields": list(nonlive_feature_fallback_fields),
            "nonlive_feature_fallback_reason": nonlive_feature_fallback_reason,
            "nonlive_feature_fallback_signal_hint": nonlive_feature_fallback_signal_hint,
            "nonlive_feature_fallback_strength_basis": nonlive_feature_fallback_strength_basis,
            "time_to_expiry_hrs": time_to_expiry_hrs,
            "orb_bias": orb_bias,
            "orb_lock_min": orb_lock_min,
            "orb_window_min": orb_lock_min,
            "orb_state": dict(orb_state),
            "minutes_since_open": minutes_since_open,
            "atr": atr,
            "vwap_slope": vwap_slope,
            "rsi_mom": rsi_mom,
            "vol_z": vol_z,
            "adx_14": adx_14,
            "atr_pct": atr_pct,
            "iv_mean": iv_mean,
            "ltp_acceleration": ltp_acceleration,
            "option_chain_skew": option_chain_skew,
            "oi_delta": oi_delta,
            "depth_imbalance": depth_imbalance,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "volume": volume,
            "bid": bid,
            "ask": ask,
            "bid_qty": bid_qty,
            "ask_qty": ask_qty,
            "quote_ok": quote_ok,
            "quote_source": quote_source,
            "quote_ts": quote_ts,
            "quote_ts_epoch": quote_ts_epoch,
            "quote_age_sec": quote_age_sec,
            "index_quote_cache": index_quote_cache,
            "index_quote_source": quote_source,
            "candle_ts_epoch": candle_ts_epoch,
            "depth_age_sec": depth_age_sec,
            "spread_pct": spread_pct,
            "feed_health": {"time_sanity": time_sanity},
            "quote_health": quote_feed_health,
            "time_sanity": time_sanity,
            "timestamp": cycle_cutoff_epoch,
            "timestamp_ist": cycle_cutoff.isoformat(),
            "option_chain": option_chain,
            "chain_source": chain_source,
            "planning_only": bool(market_ctx.mode != "LIVE" and chain_source != "live"),
            "option_chain_health": health,
            "instrument": "OPT",
            "seq_buffer": seq_buffer,
            "ltp_change": ltp_change,
            "ltp_change_window": ltp_change_window,
            "ltp_change_5m": ltp_change_5m,
            "ltp_change_10m": ltp_change_10m,
            "htf_trend": htf_trend,
            "htf_dir": htf_dir
        })

        if getattr(cfg, "ENABLE_FUTURES", False):
            results.append({
                "symbol": symbol,
                "market_open": bool(market_ctx.is_market_open),
                "offhours_mode": bool(offhours_mode),
                "market_context": market_ctx.to_dict(),
                "ltp": ltp,
                "ltp_source": ltp_source,
                "ltp_ts_epoch": ltp_ts_epoch,
                "valid": True,
                "invalid_reason": None,
                "segment": segment,
                "vwap": vwap,
                "bias": get_bias(ltp, vwap),
                "regime": regime,
                "primary_regime": primary_regime,
                "regime_confidence": regime_confidence,
                "regime_reasons": list(regime_reasons),
                "regime_probs": regime_probs,
                "regime_entropy": regime_entropy,
                "session_bucket": session_bucket,
                "regime_ts_source": regime_ts_source,
                "unstable_regime_flag": unstable_regime_flag,
                "unstable_reasons": list(unstable_reasons),
                "regime_transition_rate": regime_transition_rate,
                "regime_ts": regime_ts,
                "shock_score": shock.get("shock_score"),
                "macro_direction_bias": shock.get("macro_direction_bias"),
                "uncertainty_index": shock.get("uncertainty_index"),
                "event_name": shock.get("event_name"),
                "minutes_to_event": shock.get("minutes_to_event"),
                "event_category": shock.get("event_category"),
                "event_importance": shock.get("event_importance"),
                "fx_ret_5m": fx_ret_5m or 0.0,
                "vix_z": vix_z or 0.0,
                "crude_ret_15m": crude_ret_15m or 0.0,
                "corr_fx_nifty": corr_fx_nifty or 0.0,
                "cross_asset_ok": not bool(cross_quality.get("any_stale")),
                "cross_asset_quality": cross_quality,
                **cross_feat,
                "regime_day": regime,
                "system_state": system_state,
                "warmup_reasons": warmup_reasons,
                "warmup_min_bars": warmup_min_bars,
                "warmup_bars_by_timeframe": warmup_bars_by_timeframe,
                "warmup_min_bars_by_timeframe": warmup_min_bars_by_timeframe,
                "nonlive_feature_fallback": bool(nonlive_feature_fallback),
                "nonlive_feature_fallback_fields": list(nonlive_feature_fallback_fields),
                "nonlive_feature_fallback_reason": nonlive_feature_fallback_reason,
                "nonlive_feature_fallback_signal_hint": nonlive_feature_fallback_signal_hint,
                "nonlive_feature_fallback_strength_basis": nonlive_feature_fallback_strength_basis,
                "atr": atr,
                "vwap_slope": vwap_slope,
                "rsi_mom": rsi_mom,
                "vol_z": vol_z,
                "atr_pct": atr_pct,
                "iv_mean": iv_mean,
                "ltp_acceleration": ltp_acceleration,
                "option_chain_skew": option_chain_skew,
                "oi_delta": oi_delta,
                "depth_imbalance": depth_imbalance,
                "orb_bias": orb_bias,
                "orb_lock_min": orb_lock_min,
                "orb_window_min": orb_lock_min,
                "orb_state": dict(orb_state),
                "orb_high": orb_high,
                "orb_low": orb_low,
                "volume": volume,
                "bid": bid,
                "ask": ask,
                "bid_qty": bid_qty,
                "ask_qty": ask_qty,
                "quote_ok": quote_ok,
                "quote_source": quote_source,
                "quote_ts": quote_ts,
                "quote_ts_epoch": quote_ts_epoch,
                "quote_age_sec": quote_age_sec,
                "index_quote_cache": index_quote_cache,
                "index_quote_source": quote_source,
                "candle_ts_epoch": candle_ts_epoch,
                "depth_age_sec": depth_age_sec,
                "spread_pct": spread_pct,
                "feed_health": {"time_sanity": time_sanity},
                "quote_health": quote_feed_health,
                "time_sanity": time_sanity,
                "timestamp": cycle_cutoff_epoch,
                "timestamp_ist": cycle_cutoff.isoformat(),
                "option_chain": [],
                "instrument": "FUT",
                "ltp_change": ltp_change,
                "ltp_change_window": ltp_change_window,
                "ltp_change_5m": ltp_change_5m,
                "ltp_change_10m": ltp_change_10m,
            })

        if getattr(cfg, "ENABLE_EQUITIES", False):
            results.append({
                "symbol": symbol,
                "market_open": bool(market_ctx.is_market_open),
                "offhours_mode": bool(offhours_mode),
                "market_context": market_ctx.to_dict(),
                "ltp": ltp,
                "ltp_source": ltp_source,
                "ltp_ts_epoch": ltp_ts_epoch,
                "valid": True,
                "invalid_reason": None,
                "vwap": vwap,
                "bias": get_bias(ltp, vwap),
                "regime": regime,
                "primary_regime": primary_regime,
                "regime_confidence": regime_confidence,
                "regime_reasons": list(regime_reasons),
                "regime_probs": regime_probs,
                "regime_entropy": regime_entropy,
                "session_bucket": session_bucket,
                "regime_ts_source": regime_ts_source,
                "unstable_regime_flag": unstable_regime_flag,
                "unstable_reasons": list(unstable_reasons),
                "regime_transition_rate": regime_transition_rate,
                "regime_ts": regime_ts,
                "shock_score": shock.get("shock_score"),
                "macro_direction_bias": shock.get("macro_direction_bias"),
                "uncertainty_index": shock.get("uncertainty_index"),
                "event_name": shock.get("event_name"),
                "minutes_to_event": shock.get("minutes_to_event"),
                "event_category": shock.get("event_category"),
                "event_importance": shock.get("event_importance"),
                "fx_ret_5m": fx_ret_5m or 0.0,
                "vix_z": vix_z or 0.0,
                "crude_ret_15m": crude_ret_15m or 0.0,
                "corr_fx_nifty": corr_fx_nifty or 0.0,
                "cross_asset_ok": not bool(cross_quality.get("any_stale")),
                "cross_asset_quality": cross_quality,
                **cross_feat,
                "regime_day": regime,
                "system_state": system_state,
                "warmup_reasons": warmup_reasons,
                "warmup_min_bars": warmup_min_bars,
                "warmup_bars_by_timeframe": warmup_bars_by_timeframe,
                "warmup_min_bars_by_timeframe": warmup_min_bars_by_timeframe,
                "atr": atr,
                "vwap_slope": vwap_slope,
                "rsi_mom": rsi_mom,
                "vol_z": vol_z,
                "atr_pct": atr_pct,
                "iv_mean": iv_mean,
                "ltp_acceleration": ltp_acceleration,
                "option_chain_skew": option_chain_skew,
                "oi_delta": oi_delta,
                "depth_imbalance": depth_imbalance,
                "orb_bias": orb_bias,
                "orb_lock_min": orb_lock_min,
                "orb_window_min": orb_lock_min,
                "orb_state": dict(orb_state),
                "orb_high": orb_high,
                "orb_low": orb_low,
                "volume": volume,
                "bid": bid,
                "ask": ask,
                "bid_qty": bid_qty,
                "ask_qty": ask_qty,
                "quote_ok": quote_ok,
                "quote_source": quote_source,
                "quote_ts": quote_ts,
                "quote_ts_epoch": quote_ts_epoch,
                "quote_age_sec": quote_age_sec,
                "index_quote_cache": index_quote_cache,
                "index_quote_source": quote_source,
                "candle_ts_epoch": candle_ts_epoch,
                "depth_age_sec": depth_age_sec,
                "spread_pct": spread_pct,
                "feed_health": {"time_sanity": time_sanity},
                "quote_health": quote_feed_health,
                "time_sanity": time_sanity,
                "timestamp": cycle_cutoff_epoch,
                "timestamp_ist": cycle_cutoff.isoformat(),
                "option_chain": [],
                "instrument": "EQ",
                "ltp_change": ltp_change,
                "ltp_change_window": ltp_change_window,
                "ltp_change_5m": ltp_change_5m,
                "ltp_change_10m": ltp_change_10m,
            })

    try:
        if bool(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)):
            from core.market_event_graph_live_runtime_bridge import get_live_source_bridge

            bridge = get_live_source_bridge()
            bridge.observe_cycle(results, cycle_cutoff=cycle_cutoff)
    except Exception as exc:
        logger.warning("market_event_graph_live_source_bridge_error err=%s", exc)

    return results

# Alias for backward compatibility
get_option_chain = fetch_option_chain

# -------------------------------
# Expiry Utilities
# -------------------------------

def get_next_expiry(expiry_type="WEEKLY", symbol: str | None = None):
    """
    Return next expiry date.
    Weekly expiry uses per-symbol weekday config.
    """
    try:
        from core.market_calendar import next_expiry_by_type
        return next_expiry_by_type(expiry_type=expiry_type, symbol=symbol)
    except Exception:
        today = now_ist()
        if expiry_type.upper() == "WEEKLY":
            offset = (1 - today.weekday()) % 7  # 0=Monday, 1=Tuesday
            next_expiry = today + timedelta(days=offset)
            if next_expiry <= today:
                next_expiry += timedelta(days=7)
            return next_expiry
        return today + timedelta(days=30)

# -------------------------------
# Macro Regime Detection
# -------------------------------

def get_macro_regime(symbol):
    """
    Determine overall market regime for symbol.
    Placeholder: implement your own macro signals (trend, volatility, news)
    Returns string: "BULLISH", "BEARISH", "NEUTRAL"
    """
    return "NEUTRAL"
