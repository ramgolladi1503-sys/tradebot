# core/market_data.py

import os
import json
import time
from datetime import timezone
from datetime import datetime, timedelta
from config import config as cfg
from core.option_chain import fetch_option_chain as fetch_option_chain_impl
from core.regime_prob_model import RegimeProbModel
from core.news_shock_encoder import NewsShockEncoder
from core.news_encoder import NewsEncoder
from core.news_calendar import NewsCalendar
from core.cross_asset import CrossAsset
from core.ohlc_buffer import ohlc_buffer
from core.indicators_live import compute_indicators
from core.filters import get_bias
from core.depth_store import depth_store
from core.time_utils import now_ist, now_utc_epoch, is_market_open_ist
from core.session_calendar import minutes_since_open as session_minutes_since_open, is_open
from core.time_sanity import check_market_data_time_sanity
from core.day_type_history import append_day_type_event

from core.kite_client import kite_client

try:
    from modules.real_time_indicators import calculate_vwap, calculate_atr, calculate_orb
except Exception:
    calculate_vwap = calculate_atr = calculate_orb = None

from collections import deque
from pathlib import Path

_DATA_CACHE = {}
_LTP_HISTORY = {}
_DAYTYPE_LOCK = {}
_DAYTYPE_CONF_HISTORY = {}
_DAYTYPE_LAST = {}
_DAYTYPE_LAST_DAY = {}
_DAYTYPE_ALERT_TS = {}
_DAYTYPE_LAST_LOG = {}
_OPEN_RANGE = {}
_LAST_GOOD_LTP = {}
_REGIME_LAST_PRIMARY = {}
_REGIME_TRANSITIONS = {}
_LAST_REGIME_SNAPSHOT = {}
_INDICATOR_LAST_UPDATE_EPOCH = {}
_INSUFFICIENT_OHLC_WARNED = set()
_INDEX_BIDASK_MISSING_LOG_TS = {}
_INDEX_REST_QUOTE_REFRESH_TS = {}

_REGIME_MODEL = None
_NEWS_ENCODER = None
_NEWS_CAL = None
_NEWS_TEXT = None
_CROSS_ASSET = None

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
        age_sec = max(0.0, now_epoch - float(last_update_epoch))
    stale = age_sec > stale_limit
    ok = bool(required_inputs_ok) and (not never_computed) and (not stale)
    reason = "indicators_never_computed" if never_computed else ("indicators_stale" if stale else None)
    return {"age_sec": age_sec, "stale": stale, "ok": ok, "never_computed": never_computed, "reason": reason}


def _should_require_live_ltp(
    execution_mode: str | None = None,
    require_live_quotes: bool | None = None,
) -> bool:
    mode = str(execution_mode if execution_mode is not None else getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    require_quotes = bool(
        getattr(cfg, "REQUIRE_LIVE_QUOTES", True)
        if require_live_quotes is None
        else require_live_quotes
    )
    return (mode == "LIVE") or require_quotes


def _apply_indicator_quote_policy(
    indicators_ok: bool,
    ltp,
    ltp_source: str | None,
    execution_mode: str | None = None,
    require_live_quotes: bool | None = None,
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
    )
    if require_live_ltp and str(ltp_source or "").lower() != "live":
        return False
    return True


def update_index_quote_snapshot(
    symbol: str,
    bid=None,
    ask=None,
    mid=None,
    ts_epoch: float | None = None,
    source: str = "ws",
    ltp=None,
):
    """
    Update index quote cache from live sources (WS/REST) in a uniform structure:
      bid, ask, mid, ts_epoch, source
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
    snap = {
        "symbol": sym,
        "bid": resolved_bid,
        "ask": resolved_ask,
        "mid": resolved_mid,
        "last_price": resolved_last_price,
        "ts_epoch": ts,
        "source": str(source or "unknown"),
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
    return dict((_DATA_CACHE.get(sym) or {}).get("index_quote") or {})


def _index_quote_keys(symbol: str) -> list[str]:
    sym = str(symbol or "").upper()
    primary = str((getattr(cfg, "PREMARKET_INDICES_LTP", {}) or {}).get(sym) or "").strip()
    aliases = {
        "NIFTY": ["NSE:NIFTY 50"],
        "BANKNIFTY": ["NSE:NIFTY BANK", "NSE:BANKNIFTY"],
        "SENSEX": ["BSE:SENSEX"],
    }.get(sym, [])
    keys = []
    if primary:
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


def _synthesize_index_bid_ask(mid_price) -> tuple[float | None, float | None, float | None]:
    try:
        mid = float(mid_price)
        if mid <= 0:
            return None, None, None
        spread = max(
            float(mid) * float(getattr(cfg, "SYNTH_INDEX_SPREAD_PCT", 0.00005)),
            float(getattr(cfg, "SYNTH_INDEX_SPREAD_ABS", 0.5)),
        )
        half = spread / 2.0
        bid = round(mid - half, 4)
        ask = round(mid + half, 4)
        return bid, ask, mid
    except Exception:
        return None, None, None


def _extract_quote_epoch(raw_ts, fallback_epoch: float) -> float:
    if raw_ts is None:
        return float(fallback_epoch)
    try:
        if hasattr(raw_ts, "timestamp"):
            out = float(raw_ts.timestamp())
        elif isinstance(raw_ts, (int, float)):
            out = float(raw_ts)
        else:
            out = float(datetime.fromisoformat(str(raw_ts)).timestamp())
        if out > 1e12:
            out = out / 1000.0
        return out
    except Exception:
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
    try:
        snap_age = max(0.0, now_epoch - float(snap_ts)) if snap_ts is not None else float("inf")
    except Exception:
        snap_age = float("inf")
    if (not force) and has_cached_bidask and snap_age <= min_interval:
        return True
    last_refresh = float(_INDEX_REST_QUOTE_REFRESH_TS.get(sym) or 0.0)
    if (not force) and last_refresh and (now_epoch - last_refresh) < min_interval:
        return has_cached_bidask
    if not bool(getattr(cfg, "KITE_USE_API", True)):
        return has_cached_bidask
    try:
        kite_client.ensure()
    except Exception:
        return has_cached_bidask
    if not kite_client.kite:
        return has_cached_bidask
    _INDEX_REST_QUOTE_REFRESH_TS[sym] = now_epoch
    for key in _index_quote_keys(sym):
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


def _log_index_bidask_missing(symbol: str, source: str | None = None):
    sym = str(symbol or "").upper()
    if not sym:
        return
    now_epoch = now_utc_epoch()
    min_interval = float(getattr(cfg, "INDEX_BIDASK_MISSING_LOG_SEC", 60.0))
    last = float(_INDEX_BIDASK_MISSING_LOG_TS.get(sym) or 0.0)
    if last and (now_epoch - last) < min_interval:
        return
    _INDEX_BIDASK_MISSING_LOG_TS[sym] = now_epoch
    try:
        payload = {
            "event": "index_bidask_missing",
            "symbol": sym,
            "source": source or "unknown",
            "ts_epoch": now_epoch,
            "ts_ist": now_ist().isoformat(),
        }
        p = Path("logs/live_quote_errors.jsonl")
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


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

    entropy_unstable = float(getattr(cfg, "REGIME_ENTROPY_MAX", 1.3))
    prob_min = float(getattr(cfg, "REGIME_PROB_MIN", 0.45))
    if entropy > entropy_unstable:
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


def _log_insufficient_ohlc_warning(symbol: str, bars_count: int, min_bars: int, reason: str) -> None:
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
        "ts_epoch": now_utc_epoch(),
        "ts_ist": now_ist().isoformat(),
    }
    try:
        p = Path("logs/market_data_warnings.jsonl")
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _warm_seed_windows_minutes() -> list[int]:
    raw = str(getattr(cfg, "OHLC_WARM_SEED_WINDOWS_MIN", "120,240") or "120,240")
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


def _warm_seed_ohlc_from_history(symbol: str, bars: list, min_bars: int):
    """
    Warm-seed minute OHLC bars when current buffer is insufficient.
    Returns (bars, seeded_ok, reason_code).
    """
    if len(bars) >= int(min_bars):
        return bars, True, None
    try:
        kite_client.ensure()
    except Exception:
        pass
    kite_available = bool(getattr(kite_client, "kite", None))
    if not kite_available:
        _log_insufficient_ohlc_warning(
            symbol=symbol,
            bars_count=len(bars),
            min_bars=min_bars,
            reason="kite_api_unavailable",
        )
        return bars, False, "kite_api_unavailable"
    try:
        token = kite_client.resolve_index_token(symbol)
        if not token:
            _log_insufficient_ohlc_warning(
                symbol=symbol,
                bars_count=len(bars),
                min_bars=min_bars,
                reason="missing_index_token",
            )
            return bars, False, "missing_index_token"
        last_reason = "historical_empty"
        for window_min in _warm_seed_windows_minutes():
            from_dt = now_ist() - timedelta(minutes=int(window_min))
            to_dt = now_ist()
            hist = kite_client.historical_data(token, from_dt, to_dt, interval="minute")
            if not hist:
                last_reason = "historical_empty"
                continue
            ohlc_buffer.seed_bars(symbol, hist)
            bars = ohlc_buffer.get_bars(symbol)
            if len(bars) >= int(min_bars):
                return bars, True, None
            last_reason = "seeded_but_still_insufficient"
        if len(bars) < int(min_bars):
            _log_insufficient_ohlc_warning(
                symbol=symbol,
                bars_count=len(bars),
                min_bars=min_bars,
                reason=last_reason,
            )
            return bars, False, last_reason
        return bars, True, None
    except Exception:
        _log_insufficient_ohlc_warning(
            symbol=symbol,
            bars_count=len(bars),
            min_bars=min_bars,
            reason="historical_seed_error",
        )
        return bars, False, "historical_seed_error"

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
                "primary_regime": "NEUTRAL",
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
        age = time.time() - entry.get("ts", 0)
        if age <= getattr(cfg, "LTP_CACHE_TTL_SEC", 300):
            return entry.get("ltp")
    except Exception:
        return None
    return None

def _save_cached_ltp(symbol: str, ltp: float):
    try:
        _LAST_GOOD_LTP[symbol] = {"ltp": float(ltp), "ts": time.time()}
    except Exception:
        pass

def get_ltp(symbol: str):
    """
    Fetch latest market price from Kite or fallback.
    """
    live_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "LIVE"
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
                _save_cached_ltp(symbol, float(ws_price))
                cache = _DATA_CACHE.setdefault(symbol, {})
                cache["ltp_source"] = "live"
                cache["ltp_ts_epoch"] = float(ws_quote.get("ts_epoch") or now_utc_epoch())
                return float(ws_price)
        except Exception:
            pass
    if cfg.KITE_USE_API:
        kite_client.ensure()
        if not kite_client.kite and getattr(cfg, "REQUIRE_LIVE_QUOTES", True):
            try:
                err = {"symbol": symbol, "error": "kite_not_initialized", "timestamp": now_ist().isoformat()}
                p = Path("logs/live_quote_errors.jsonl")
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("a") as f:
                    f.write(json.dumps(err) + "\n")
            except Exception:
                pass
        try:
            ksym = getattr(cfg, "PREMARKET_INDICES_LTP", {}).get(symbol)
            if not ksym:
                ksym = f"NSE:{symbol}" if symbol != "SENSEX" else f"BSE:{symbol}"
            data = kite_client.ltp([ksym])
            price = data.get(ksym, {}).get("last_price", 0)
            if price:
                _save_cached_ltp(symbol, price)
                cache = _DATA_CACHE.setdefault(symbol, {})
                cache["ltp_source"] = "live"
                cache["ltp_ts_epoch"] = now_utc_epoch()
                return price
        except Exception as e:
            if getattr(cfg, "REQUIRE_LIVE_QUOTES", True):
                try:
                    err = {"symbol": symbol, "error": "ltp_fetch_failed", "detail": str(e), "timestamp": now_ist().isoformat()}
                    p = Path("logs/live_quote_errors.jsonl")
                    p.parent.mkdir(parents=True, exist_ok=True)
                    with p.open("a") as f:
                        f.write(json.dumps(err) + "\n")
                except Exception:
                    pass

        # hard fallback for index aliases
        try:
            alias_map = {
                "NIFTY": ["NSE:NIFTY 50"],
                "BANKNIFTY": ["NSE:NIFTY BANK", "NSE:BANKNIFTY"],
                "SENSEX": ["BSE:SENSEX"],
            }
            for ksym in alias_map.get(symbol, []):
                data = kite_client.ltp([ksym])
                price = data.get(ksym, {}).get("last_price", 0)
                if price:
                    _save_cached_ltp(symbol, price)
                    cache = _DATA_CACHE.setdefault(symbol, {})
                    cache["ltp_source"] = "live"
                    cache["ltp_ts_epoch"] = now_utc_epoch()
                    return price
        except Exception as e:
            if getattr(cfg, "REQUIRE_LIVE_QUOTES", True):
                try:
                    from pathlib import Path
                    import json
                    err = {"symbol": symbol, "error": "ltp_alias_failed", "detail": str(e), "timestamp": now_ist().isoformat()}
                    p = Path("logs/live_quote_errors.jsonl")
                    p.parent.mkdir(parents=True, exist_ok=True)
                    with p.open("a") as f:
                        f.write(json.dumps(err) + "\n")
                except Exception:
                    pass
                pass

    # Fallback to cached LTP if allowed (disabled in LIVE)
    if (not live_mode) and getattr(cfg, "ALLOW_STALE_LTP", True):
        cached = _cached_ltp(symbol)
        if cached:
            _DATA_CACHE.setdefault(symbol, {})["ltp_source"] = "cache"
            return cached

    # Fallback
    segment = getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")
    market_open = bool(is_market_open_ist(segment=segment))
    if getattr(cfg, "REQUIRE_LIVE_QUOTES", True):
        _DATA_CACHE.setdefault(symbol, {})["ltp_source"] = "none"
        if market_open:
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

# -------------------------------
# Option Chain
# -------------------------------

def fetch_option_chain(symbol: str, ltp: float, force_synthetic: bool = False):
    return fetch_option_chain_impl(symbol, ltp, force_synthetic=force_synthetic)

def _option_chain_health(symbol: str, chain: list, ltp: float):
    total = len(chain)
    if total == 0:
        return {
            "symbol": symbol,
            "status": "ERROR" if getattr(cfg, "REQUIRE_LIVE_QUOTES", True) else "EMPTY",
            "total": 0,
            "missing_iv_pct": 1.0,
            "missing_quote_pct": 1.0,
            "strike_min": None,
            "strike_max": None,
            "ltp": ltp,
            "note": "No live option chain" if getattr(cfg, "REQUIRE_LIVE_QUOTES", True) else "Empty chain",
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

def fetch_live_market_data():
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

    for symbol in symbols:
        segment = getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")
        market_open_for_segment = bool(is_open(now_dt=now_ist(), segment=segment))
        ltp = get_ltp(symbol)
        ltp_source = _DATA_CACHE.get(symbol, {}).get("ltp_source", "none")
        ltp_ts_epoch = _DATA_CACHE.get(symbol, {}).get("ltp_ts_epoch")
        if bool(getattr(cfg, "REQUIRE_LIVE_QUOTES", True)) and market_open_for_segment and (ltp is None or float(ltp) <= 0):
            results.append(
                {
                    "symbol": symbol,
                    "segment": segment,
                    "ltp": ltp,
                    "ltp_source": ltp_source,
                    "ltp_ts_epoch": ltp_ts_epoch,
                    "valid": False,
                    "invalid_reason": "invalid_ltp",
                    "invalid_reason_codes": ["invalid_ltp"],
                    "timestamp": now_utc_epoch(),
                    "timestamp_ist": now_ist().isoformat(),
                    "instrument": "OPT",
                    "feed_health": {
                        "time_sanity": {
                            "ok": False,
                            "reasons": ["invalid_ltp"],
                            "ltp_ts_epoch": ltp_ts_epoch,
                            "candle_ts_epoch": None,
                            "market_open": market_open_for_segment,
                            "require_live_quotes": bool(getattr(cfg, "REQUIRE_LIVE_QUOTES", True)),
                        }
                    },
                }
            )
            continue
        try:
            if ltp and ltp > 0:
                ohlc_buffer.update_tick(symbol, ltp, volume=0, ts=now_ist())
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
            now = now_ist()
            minutes_since_open = session_minutes_since_open(now_dt=now, segment=segment)
            is_market_open = is_open(now_dt=now, segment=segment)
            today_local = now.date()
        except Exception:
            minutes_since_open = 0
            is_market_open = True
            today_local = now_ist().date()
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
        volume = 0
        vwap_slope = 0
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
        now_epoch_for_indicators = float(now_utc_epoch())
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
        try:
            bars = ohlc_buffer.get_bars(symbol)
            if len(bars) < min_bars:
                bars, _seeded_ok, ohlc_seed_reason = _warm_seed_ohlc_from_history(
                    symbol=symbol,
                    bars=bars,
                    min_bars=min_bars,
                )
                ohlc_seeded = bool(_seeded_ok)
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
            last_ts = ind.get("last_ts")
            bars_ready = bool(ohlc_bars_count >= min_bars and ohlc_bars_count > 0)
            required_inputs_ok = bars_ready
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
            indicators_age_sec = max(0.0, now_epoch_for_indicators - float(indicator_last_update_epoch))
            indicators_ok = bool(bars_ready)
        except Exception as exc:
            indicators_ok = False
            indicator_inputs_ok = False
            if not isinstance(indicator_last_update_epoch, (int, float)):
                indicator_last_update_epoch = 0.0
            indicators_age_sec = max(0.0, now_epoch_for_indicators - float(indicator_last_update_epoch))
            compute_indicators_error = f"{type(exc).__name__}:{exc}"
            missing_inputs.append("compute_indicators_exception")
            if float(indicator_last_update_epoch) <= 0.0:
                missing_inputs.append("indicators_never_computed")
                missing_inputs.append("never_computed")
        if ohlc_seed_reason == "kite_api_unavailable" and ohlc_bars_count == 0:
            # Explicit fail-closed reason when REST warm-start is not available.
            missing_inputs = ["ohlc_buffer_empty"]
        missing_inputs = list(dict.fromkeys(str(x) for x in missing_inputs if x))

        # Cross-asset data quality fail-safe (only in LIVE when required)
        try:
            live_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "LIVE"
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
            now_ts = now_utc_epoch()
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
                    quote_ts = datetime.utcfromtimestamp(quote_ts_epoch).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
                    quote_age_sec = max(0.0, now_utc_epoch() - quote_ts_epoch)
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
                        quote_ts = datetime.utcfromtimestamp(quote_ts_epoch).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
                        quote_age_sec = max(0.0, now_utc_epoch() - quote_ts_epoch)
                        if ltp_source == "live":
                            ltp_ts_epoch = quote_ts_epoch
                    if bid and ask:
                        quote_ok = True
                        quote_source = "depth"
                        if ltp:
                            spread_pct = (ask - bid) / ltp
                except Exception:
                    quote_ok = False
        if not quote_ok and _is_index_symbol(symbol):
            synth_bid, synth_ask, synth_mid = _synthesize_index_bid_ask(ltp)
            if synth_bid is not None and synth_ask is not None and synth_mid is not None:
                bid = synth_bid
                ask = synth_ask
                mid = synth_mid
                synthetic_index_quote = True
                quote_source = "synthetic_index"
                quote_ok = True
                if quote_ts_epoch is None:
                    if isinstance(ltp_ts_epoch, (int, float)):
                        quote_ts_epoch = float(ltp_ts_epoch)
                    else:
                        quote_ts_epoch = now_utc_epoch()
                quote_ts = datetime.utcfromtimestamp(float(quote_ts_epoch)).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
                quote_age_sec = max(0.0, now_utc_epoch() - float(quote_ts_epoch))
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
        if not quote_ok:
            _log_index_bidask_missing(symbol, source=quote_source)
        index_quote_cache = dict(get_index_quote_snapshot(symbol) or {})

        time_sanity = check_market_data_time_sanity(
            ltp_ts_epoch=ltp_ts_epoch,
            candle_ts_epoch=candle_ts_epoch,
            market_open=market_open_for_segment,
            require_live_quotes=bool(getattr(cfg, "REQUIRE_LIVE_QUOTES", True)),
            max_ltp_age_sec=getattr(cfg, "MAX_LTP_AGE_SEC", 8),
            max_candle_age_sec=getattr(cfg, "MAX_CANDLE_AGE_SEC", 120),
            now_epoch=now_utc_epoch(),
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
                    "timestamp": now_utc_epoch(),
                    "timestamp_ist": now_ist().isoformat(),
                    "instrument": "OPT",
                    "feed_health": {"time_sanity": time_sanity},
                }
            )
            continue

        # Open-range tracking for bias lock
        orb_lock_min = getattr(cfg, "ORB_LOCK_MIN", 15)
        orb_bias = "NEUTRAL"
        try:
            or_state = _OPEN_RANGE.get(symbol, {"high": None, "low": None, "bias": None})
            if minutes_since_open <= orb_lock_min:
                hi = or_state.get("high")
                lo = or_state.get("low")
                if hi is None or ltp > hi:
                    hi = ltp
                if lo is None or ltp < lo:
                    lo = ltp
                or_state.update({"high": hi, "low": lo})
            else:
                if or_state.get("bias") is None:
                    hi = or_state.get("high")
                    lo = or_state.get("low")
                    if hi is not None and ltp > hi:
                        or_state["bias"] = "UP"
                    elif lo is not None and ltp < lo:
                        or_state["bias"] = "DOWN"
                    else:
                        or_state["bias"] = "NEUTRAL"
                orb_bias = or_state.get("bias") or "NEUTRAL"
            _OPEN_RANGE[symbol] = or_state
            if minutes_since_open <= orb_lock_min:
                orb_bias = "PENDING"
        except Exception:
            orb_bias = "NEUTRAL"

        option_chain = fetch_option_chain(symbol, ltp, force_synthetic=False)
        chain_source = "live" if option_chain else "empty"
        if not option_chain and getattr(cfg, "ALLOW_SYNTHETIC_CHAIN", False) and str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() != "LIVE":
            option_chain = fetch_option_chain(symbol, ltp, force_synthetic=True)
            chain_source = "synthetic" if option_chain else "empty"
        # Option chain health validation (live NFO/BFO)
        try:
            health = _option_chain_health(symbol, option_chain, ltp)
            health_path = Path("logs/option_chain_health.json")
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
                depth_age_sec = max(0.0, now_utc_epoch() - float(latest_depth_ts))
        except Exception:
            depth_age_sec = None

        # Regime model (probabilistic)
        atr_pct = (atr / ltp) if ltp else 0
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
        model_out = _REGIME_MODEL.predict(features)
        regime_probs = model_out.get("regime_probs", {})
        primary_regime = model_out.get("primary_regime", "NEUTRAL")
        regime_entropy = model_out.get("regime_entropy", 0.0)
        model_unstable_flag = bool(model_out.get("unstable_regime_flag", False))
        unstable_reasons = []

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

        regime = primary_regime

        # time to expiry (hours)
        time_to_expiry_hrs = None
        try:
            expiry = None
            if option_chain:
                expiry = option_chain[0].get("expiry")
            if expiry:
                from datetime import datetime as dt
                exp_dt = dt.fromisoformat(str(expiry))
                time_to_expiry_hrs = max(0.0, (exp_dt - now_ist()).total_seconds() / 3600.0)
        except Exception:
            time_to_expiry_hrs = None

        # Force regime override (for testing)
        force = getattr(cfg, "FORCE_REGIME", "")
        if isinstance(force, str) and force.strip():
            regime = force.strip().upper()

        if not indicators_ok:
            regime = "NEUTRAL"
            primary_regime = "NEUTRAL"
            regime_probs = {}
            regime_entropy = 0.0
        unstable_reasons = _derive_unstable_reasons(
            regime_probs=regime_probs,
            regime_entropy=regime_entropy,
            regime_transition_rate=regime_transition_rate,
            indicators_ok=indicators_ok,
            ohlc_bars_count=ohlc_bars_count,
            min_bars=min_bars,
            missing_inputs=missing_inputs,
            model_unstable_flag=model_unstable_flag,
        )
        unstable_regime_flag = bool(unstable_reasons)

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

        regime_ts = now_ist().isoformat()
        try:
            _LAST_REGIME_SNAPSHOT[str(symbol).upper()] = {
                "primary_regime": primary_regime,
                "regime_probs": regime_probs,
                "regime_entropy": regime_entropy,
                "unstable_regime_flag": unstable_regime_flag,
                "unstable_reasons": list(unstable_reasons),
                "regime_ts": regime_ts,
            }
        except Exception:
            pass

        results.append({
            "symbol": symbol,
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
            "regime_probs": regime_probs,
            "regime_entropy": regime_entropy,
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
            "time_to_expiry_hrs": time_to_expiry_hrs,
            "orb_bias": orb_bias,
            "orb_lock_min": orb_lock_min,
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
            "time_sanity": time_sanity,
            "timestamp": now_utc_epoch(),
            "timestamp_ist": now_ist().isoformat(),
            "option_chain": option_chain,
            "chain_source": chain_source,
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
                "regime_probs": regime_probs,
                "regime_entropy": regime_entropy,
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
                "time_sanity": time_sanity,
                "timestamp": now_utc_epoch(),
                "timestamp_ist": now_ist().isoformat(),
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
                "ltp": ltp,
                "ltp_source": ltp_source,
                "ltp_ts_epoch": ltp_ts_epoch,
                "valid": True,
                "invalid_reason": None,
                "vwap": vwap,
                "bias": get_bias(ltp, vwap),
                "regime": regime,
                "primary_regime": primary_regime,
                "regime_probs": regime_probs,
                "regime_entropy": regime_entropy,
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
                "time_sanity": time_sanity,
                "timestamp": now_utc_epoch(),
                "timestamp_ist": now_ist().isoformat(),
                "option_chain": [],
                "instrument": "EQ",
                "ltp_change": ltp_change,
                "ltp_change_window": ltp_change_window,
                "ltp_change_5m": ltp_change_5m,
                "ltp_change_10m": ltp_change_10m,
            })

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
