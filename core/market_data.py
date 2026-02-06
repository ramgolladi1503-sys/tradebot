# core/market_data.py

import os
import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from config import config as cfg
from core.option_chain import fetch_option_chain as fetch_option_chain_impl
from core.filters import get_bias

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

# -------------------------------
# Market Data Functions
# -------------------------------

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
    if cfg.KITE_USE_API:
        kite_client.ensure()
        if not kite_client.kite and getattr(cfg, "REQUIRE_LIVE_QUOTES", True):
            try:
                err = {"symbol": symbol, "error": "kite_not_initialized", "timestamp": datetime.now().isoformat()}
                p = Path("logs/live_quote_errors.jsonl")
                p.parent.mkdir(exist_ok=True)
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
                _DATA_CACHE.setdefault(symbol, {})["ltp_source"] = "live"
                return price
        except Exception as e:
            if getattr(cfg, "REQUIRE_LIVE_QUOTES", True):
                try:
                    err = {"symbol": symbol, "error": "ltp_fetch_failed", "detail": str(e), "timestamp": datetime.now().isoformat()}
                    p = Path("logs/live_quote_errors.jsonl")
                    p.parent.mkdir(exist_ok=True)
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
                    _DATA_CACHE.setdefault(symbol, {})["ltp_source"] = "live"
                    return price
        except Exception as e:
            if getattr(cfg, "REQUIRE_LIVE_QUOTES", True):
                try:
                    from pathlib import Path
                    import json
                    err = {"symbol": symbol, "error": "ltp_alias_failed", "detail": str(e), "timestamp": datetime.now().isoformat()}
                    p = Path("logs/live_quote_errors.jsonl")
                    p.parent.mkdir(exist_ok=True)
                    with p.open("a") as f:
                        f.write(json.dumps(err) + "\n")
                except Exception:
                    pass
                pass

    # Fallback to cached LTP if allowed
    if getattr(cfg, "ALLOW_STALE_LTP", True):
        cached = _cached_ltp(symbol)
        if cached:
            _DATA_CACHE.setdefault(symbol, {})["ltp_source"] = "cache"
            return cached

    # Fallback
    if getattr(cfg, "REQUIRE_LIVE_QUOTES", True):
        _DATA_CACHE.setdefault(symbol, {})["ltp_source"] = "none"
        if getattr(cfg, "ALLOW_CLOSE_FALLBACK", True):
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
            "timestamp": datetime.now().isoformat(),
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
        "timestamp": datetime.now().isoformat(),
    }

def fetch_live_market_data():
    """
    Returns a list of market snapshots for symbols in config.
    Each snapshot includes LTP, VWAP, ATR, and option chain.
    """
    symbols = list(getattr(cfg, "SYMBOLS", []))
    data_dir = os.path.join(os.getcwd(), "data")
    results = []

    for symbol in symbols:
        ltp = get_ltp(symbol)
        vwap = ltp
        atr = max(1.0, ltp * 0.002)
        # minutes since open (used for ORB bias + day-type)
        try:
            tz = ZoneInfo("Asia/Kolkata")
            now = datetime.now(tz)
            market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
            market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
            minutes_since_open = max(0, int((now - market_open).total_seconds() / 60))
            is_market_open = market_open <= now <= market_close
            today_local = now.date()
        except Exception:
            minutes_since_open = 0
            is_market_open = True
            today_local = datetime.now().date()
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

        # If historical CSV exists, use it for indicators
        try:
            csv_candidates = [f for f in os.listdir(data_dir) if f.startswith(symbol + "_") and f.endswith(".csv")]
            if csv_candidates:
                csv_path = os.path.join(data_dir, sorted(csv_candidates)[-1])
                cached = _DATA_CACHE.get(symbol)
                if not cached or cached.get("path") != csv_path:
                    import pandas as pd
                    df = pd.read_csv(csv_path)
                    _DATA_CACHE.setdefault(symbol, {})
                    _DATA_CACHE[symbol]["path"] = csv_path
                    _DATA_CACHE[symbol]["df"] = df
                else:
                    df = cached.get("df")
                # Ensure indicators are present (fallback compute)
                try:
                    from core.feature_builder import add_indicators
                    needed = {"vwap", "vwap_slope", "rsi_mom", "vol_z", "adx_14", "atr_14"}
                    if not needed.issubset(set(df.columns)):
                        df = add_indicators(df)
                        _DATA_CACHE[symbol]["df"] = df
                except Exception:
                    pass
                # If live LTP is missing or fallback, use last close from CSV
                try:
                    if (ltp == 0 or _DATA_CACHE.get(symbol, {}).get("ltp_source") in ("none", "fallback")) and "close" in df.columns:
                        ltp = float(df["close"].iloc[-1])
                        _DATA_CACHE.setdefault(symbol, {})["ltp_source"] = "csv"
                        _save_cached_ltp(symbol, ltp)
                except Exception:
                    pass
                if "vwap" in df.columns:
                    vwap = float(df["vwap"].iloc[-1])
                elif "close" in df.columns and "volume" in df.columns and calculate_vwap:
                    vwap = calculate_vwap(df)
                if "atr_14" in df.columns:
                    atr = float(df["atr_14"].iloc[-1])
                elif {"high", "low", "close"}.issubset(df.columns) and calculate_atr:
                    atr = float(calculate_atr(df))
                if {"high", "low"}.issubset(df.columns) and calculate_orb:
                    orb_high, orb_low = calculate_orb(df)
                if "volume" in df.columns:
                    volume = int(df["volume"].iloc[-1])
                # extra features if present
                if "vwap_slope" in df.columns:
                    vwap_slope = float(df["vwap_slope"].iloc[-1])
                else:
                    vwap_slope = 0
                if "rsi_mom" in df.columns:
                    rsi_mom = float(df["rsi_mom"].iloc[-1])
                else:
                    rsi_mom = 0
                if "vol_z" in df.columns:
                    vol_z = float(df["vol_z"].iloc[-1])
                else:
                    vol_z = 0
                if "adx_14" in df.columns:
                    adx_14 = float(df["adx_14"].iloc[-1])
                else:
                    adx_14 = 0
            else:
                vwap_slope = 0
                rsi_mom = 0
                vol_z = 0
                adx_14 = 0
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
            now_ts = datetime.now().timestamp()
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
        except Exception:
            pass

        # Basic synthetic bid/ask when not available
        bid = round(ltp * 0.999, 2) if ltp else 0
        ask = round(ltp * 1.001, 2) if ltp else 0

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
        chain_source = "live"
        if not option_chain and getattr(cfg, "FORCE_SYNTH_CHAIN_ON_FAIL", True):
            option_chain = fetch_option_chain(symbol, ltp, force_synthetic=True)
            chain_source = "synthetic"
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

        # Regime detection based on available indicators
        regime = "NEUTRAL"
        if adx_14 >= getattr(cfg, "TREND_ADX", 22) and abs(vwap_slope) > 0:
            regime = "TREND"
        elif adx_14 < getattr(cfg, "RANGE_ADX", 18):
            regime = "RANGE"

        # Event regime override based on vol/IV
        try:
            atr_pct = (atr / ltp) if ltp else 0
            iv_vals = [c.get("iv") for c in option_chain if c.get("iv") is not None]
            iv_mean = sum(iv_vals) / len(iv_vals) if iv_vals else 0
            if vol_z >= getattr(cfg, "EVENT_VOL_Z", 1.0) or atr_pct >= getattr(cfg, "EVENT_ATR_PCT", 0.004) or iv_mean >= getattr(cfg, "EVENT_IV_MEAN", 0.35):
                regime = "EVENT"
            # Range volatile: choppy + elevated vol or IV
            if regime == "RANGE":
                if vol_z >= getattr(cfg, "RANGE_VOL_Z", 0.6) or atr_pct >= getattr(cfg, "RANGE_ATR_PCT", 0.003) or iv_mean >= getattr(cfg, "RANGE_IV_MEAN", 0.3):
                    regime = "RANGE_VOLATILE"
        except Exception:
            pass

        # time to expiry (hours)
        time_to_expiry_hrs = None
        try:
            expiry = None
            if option_chain:
                expiry = option_chain[0].get("expiry")
            if expiry:
                from datetime import datetime as dt
                exp_dt = dt.fromisoformat(str(expiry))
                time_to_expiry_hrs = max(0.0, (exp_dt - datetime.now()).total_seconds() / 3600.0)
        except Exception:
            time_to_expiry_hrs = None

        # Force regime override (for testing)
        force = getattr(cfg, "FORCE_REGIME", "")
        if isinstance(force, str) and force.strip():
            regime = force.strip().upper()

        # Day-type classifier (first 30–60 min decisive)
        day_type = "UNKNOWN"
        day_conf = 0.0
        try:
            minutes_since_open = int(minutes_since_open)
        except Exception:
            minutes_since_open = 0
        try:
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
                    Path("logs").mkdir(exist_ok=True)
                    with open("logs/day_type_events.jsonl", "a") as f:
                        f.write(json.dumps({
                            "ts": datetime.now().isoformat(),
                            "symbol": symbol,
                            "event": "LOCK",
                            "day_type": day_type,
                            "confidence": day_conf,
                            "minutes_since_open": minutes_since_open,
                        }) + "\n")
                except Exception:
                    pass

        # Log day-type changes
        try:
            last = _DAYTYPE_LAST.get(symbol)
            if last != day_type:
                _DAYTYPE_LAST[symbol] = day_type
                Path("logs").mkdir(exist_ok=True)
                with open("logs/day_type_events.jsonl", "a") as f:
                    f.write(json.dumps({
                        "ts": datetime.now().isoformat(),
                        "symbol": symbol,
                        "event": "CHANGE",
                        "day_type": day_type,
                        "confidence": day_conf,
                        "minutes_since_open": minutes_since_open,
                    }) + "\n")
        except Exception:
            pass

        # Periodic confidence heartbeat for chart accuracy
        try:
            now_ts = time.time()
            last_ts = _DAYTYPE_LAST_LOG.get(symbol, 0)
            every = getattr(cfg, "DAYTYPE_LOG_EVERY_SEC", 60)
            if now_ts - last_ts >= every:
                _DAYTYPE_LAST_LOG[symbol] = now_ts
                Path("logs").mkdir(exist_ok=True)
                with open("logs/day_type_events.jsonl", "a") as f:
                    f.write(json.dumps({
                        "ts": datetime.now().isoformat(),
                        "symbol": symbol,
                        "event": "TICK",
                        "day_type": day_type,
                        "confidence": day_conf,
                        "minutes_since_open": minutes_since_open,
                    }) + "\n")
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

        seq_buffer = None
        htf_trend = 0
        htf_dir = "FLAT"
        try:
            csv_candidates = [f for f in os.listdir(data_dir) if f.startswith(symbol + "_") and f.endswith(".csv")]
            if csv_candidates:
                csv_path = os.path.join(data_dir, sorted(csv_candidates)[-1])
                import pandas as pd
                df = pd.read_csv(csv_path).dropna()
                if len(df) >= getattr(cfg, "DEEP_SEQUENCE_LEN", 20):
                    from core.feature_builder import add_indicators
                    df = add_indicators(df)
                    cols = ["ltp","bid","ask","spread_pct","volume","atr","vwap_dist","moneyness","is_call","vwap_slope","rsi_mom","vol_z"]
                    # create pseudo feature window
                    feat = df.tail(getattr(cfg, "DEEP_SEQUENCE_LEN", 20))
                    # fallback: map close to ltp
                    feat = feat.assign(
                        ltp=feat["close"],
                        bid=feat["close"]*0.999,
                        ask=feat["close"]*1.001,
                        spread_pct=0.002,
                        moneyness=0,
                        is_call=1
                    )
                    seq_buffer = feat[cols].values.tolist()
                # higher timeframe trend (simple slope on last HTF_BARS)
                htf_bars = getattr(cfg, "HTF_BARS", 60)
                if len(df) >= htf_bars:
                    closes = df["close"].tail(htf_bars)
                    htf_trend = closes.iloc[-1] - closes.iloc[0]
                    htf_dir = "UP" if htf_trend > 0 else "DOWN" if htf_trend < 0 else "FLAT"
                else:
                    htf_trend = 0
                    htf_dir = "FLAT"
        except Exception:
            pass

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

        results.append({
            "symbol": symbol,
            "ltp": ltp,
            "ltp_source": _DATA_CACHE.get(symbol, {}).get("ltp_source", "none"),
            "vwap": vwap,
            "bias": get_bias(ltp, vwap),
            "regime": regime,
            "regime_day": regime,
            "day_type": day_type,
            "day_confidence": round(day_conf, 3),
            "day_conf_history": conf_hist,
            "time_to_expiry_hrs": time_to_expiry_hrs,
            "orb_bias": orb_bias,
            "orb_lock_min": orb_lock_min,
            "minutes_since_open": minutes_since_open,
            "atr": atr,
            "vwap_slope": vwap_slope,
            "rsi_mom": rsi_mom,
            "vol_z": vol_z,
            "adx_14": adx_14,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "volume": volume,
            "bid": bid,
            "ask": ask,
            "timestamp": datetime.now().timestamp(),
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
                "vwap": vwap,
                "bias": get_bias(ltp, vwap),
                "regime": regime,
                "regime_day": regime,
                "atr": atr,
                "vwap_slope": vwap_slope,
                "rsi_mom": rsi_mom,
                "vol_z": vol_z,
                "orb_high": orb_high,
                "orb_low": orb_low,
                "volume": volume,
                "bid": bid,
                "ask": ask,
                "timestamp": datetime.now().timestamp(),
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
                "vwap": vwap,
                "bias": get_bias(ltp, vwap),
                "regime": regime,
                "regime_day": regime,
                "atr": atr,
                "vwap_slope": vwap_slope,
                "rsi_mom": rsi_mom,
                "vol_z": vol_z,
                "orb_high": orb_high,
                "orb_low": orb_low,
                "volume": volume,
                "bid": bid,
                "ask": ask,
                "timestamp": datetime.now().timestamp(),
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
        today = datetime.now()
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
