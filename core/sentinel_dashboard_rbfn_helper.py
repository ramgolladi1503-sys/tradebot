"""Helper functions for Sentinel Dashboard RBFN calculations.
Decoupled from Streamlit UI runtime for clean, safe testing.
"""
from __future__ import annotations

import json
import os
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from strategies.optionmate_rbfn_strategy import OptionMateRBFNStrategy, GoldenCandle


def resolve_upstox_prev_close(item: dict, instrument_key: Optional[str] = None, token: Optional[str] = None) -> Optional[float]:
    """Computes prior day close strictly from round(float(last_price) - float(net_change), 2).
    Rejects item['ohlc']['close'] because Upstox mutates it to the live candle close during market hours.
    Adds daily candle fallback via /v2/historical-candle/{instrument}/day/{today}/{5_days_ago}.
    """
    if not isinstance(item, dict):
        return None

    # Priority 1: Derivation from live quote last_price and net_change
    try:
        last_price = item.get("last_price")
        net_change = item.get("net_change")
        if last_price is not None and net_change is not None:
            lp_f = float(last_price)
            nc_f = float(net_change)
            if lp_f > 0:
                return round(lp_f - nc_f, 2)
    except (ValueError, TypeError):
        pass

    # Priority 2: Fallback to daily historical candle endpoint
    if instrument_key and token:
        try:
            today_s = datetime.now().strftime("%Y-%m-%d")
            five_days_ago_s = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            headers = {
                "accept": "application/json",
                "Api-Version": "2.0",
                "Authorization": f"Bearer {token}",
                "User-Agent": "TradeBot/Sentinel",
            }
            d_url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/day/{today_s}/{five_days_ago_s}"
            resp = requests.get(d_url, headers=headers, timeout=2)
            if resp.status_code == 200:
                candles = resp.json().get("data", {}).get("candles", [])
                # Upstox day candles format: [timestamp, open, high, low, close, volume, open_interest]
                # Candles are reverse-chronological or chronological; skip today's uncompleted candle if present
                for c in candles:
                    c_date = str(c[0])[:10]
                    if c_date < today_s:
                        return round(float(c[4]), 2)
        except Exception:
            pass

    return None


def get_cache_path(date_str: str) -> str:
    """Returns the persistent session PIT cache file path."""
    return f"/tmp/tradebot_rbfn_cache_{date_str}.json"


def load_cached_boundaries(date_str: str) -> Optional[dict]:
    """Loads frozen boundaries from persistent cache if available."""
    cache_file = get_cache_path(date_str)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
                if data.get("date") == date_str and "symbols" in data:
                    return data
        except Exception:
            pass
    return None


def save_cached_boundaries(date_str: str, cache_data: dict) -> None:
    """Saves frozen boundaries to persistent cache."""
    cache_file = get_cache_path(date_str)
    try:
        with open(cache_file, "w") as f:
            json.dump(cache_data, f, indent=2)
    except Exception:
        pass


def compute_official_rbfn_boundaries(spots: Optional[Dict[str, float]] = None, token: Optional[str] = None) -> dict:
    """Computes daily causal RBFN Trend Decider and Reversal Price Lines (RP1, RP2) using OptionMate strategy engine.
    Anchors to closed 09:15-09:20 5m bar equilibrium when available to eliminate opening auction drift.
    Guarantees session PIT freeze across midday restarts via /tmp cache.
    """
    if spots is None:
        spots = {}
    today_s = datetime.now().strftime("%Y-%m-%d")

    # Check session PIT cache first
    cached_session = load_cached_boundaries(today_s)
    cached_symbols = cached_session.get("symbols", {}) if cached_session else {}

    if token is None:
        token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    headers = {"accept": "application/json", "Api-Version": "2.0", "Authorization": f"Bearer {token}", "User-Agent": "TradeBot/Sentinel"}

    index_configs = {
        "NIFTY": {"sym": "NSE_INDEX%7CNifty%2050", "key": "NSE_INDEX:Nifty 50", "default_atr": 150.0, "step_size": 50},
        "SENSEX": {"sym": "BSE_INDEX%7CSENSEX", "key": "BSE_INDEX:SENSEX", "default_atr": 400.0, "step_size": 100},
        "BANKNIFTY": {"sym": "NSE_INDEX%7CNifty%20Bank", "key": "NSE_INDEX:Nifty Bank", "default_atr": 350.0, "step_size": 100},
    }

    rbfn_results = {}
    new_cache_symbols = dict(cached_symbols)
    cache_updated = False

    for idx_name, cfg in index_configs.items():
        # If frozen entry exists in persistent cache for today, reuse directly!
        if idx_name in cached_symbols and cached_symbols[idx_name].get("frozen") is True:
            rbfn_results[idx_name] = dict(cached_symbols[idx_name]["boundaries"])
            continue

        current_spot = spots.get(idx_name, 0.0)
        bar_5m = None
        upstox_prev_close = None
        if token:
            try:
                # 1. Resolve dynamic previous close from Upstox quote via resolve_upstox_prev_close
                q_url = f"https://api.upstox.com/v2/market-quote/quotes?instrument_key={cfg['sym']}"
                rq = requests.get(q_url, headers=headers, timeout=2)
                if rq.status_code == 200:
                    q_data = rq.json().get("data", {})
                    # Key in quote data could be formatted with colon or pipe
                    item = q_data.get(cfg["key"]) or q_data.get(cfg["sym"]) or next(iter(q_data.values()), {})
                    upstox_prev_close = resolve_upstox_prev_close(item, instrument_key=cfg["sym"], token=token)
            except Exception:
                pass

            try:
                # 2. Historical 1m candle for opening 5m bar equilibrium
                c_url = f"https://api.upstox.com/v2/historical-candle/intraday/{cfg['sym']}/1minute"
                r = requests.get(c_url, headers=headers, timeout=3)
                if r.status_code == 200:
                    c_list = r.json().get("data", {}).get("candles", [])
                    # First 5 minutes: 09:15:00 to 09:19:00
                    five_min_candles = [c for c in c_list if "09:15:00" <= c[0][11:19] <= "09:19:00"]
                    if len(five_min_candles) >= 5:
                        o = float(five_min_candles[-1][1])
                        h = float(max(c[2] for c in five_min_candles))
                        l = float(min(c[3] for c in five_min_candles))
                        c_close = float(five_min_candles[0][4])
                        v = float(sum(c[5] for c in five_min_candles))
                        bar_5m = GoldenCandle.create(open=o, high=h, low=l, close=c_close, volume=v)
            except Exception:
                pass

        # Resolve previous close safely: Upstox quote -> current_spot -> bar_5m.open -> fallback
        if upstox_prev_close is not None and upstox_prev_close > 0:
            resolved_prev_close = upstox_prev_close
        elif current_spot > 0:
            resolved_prev_close = current_spot
        elif bar_5m is not None:
            resolved_prev_close = bar_5m.open
        else:
            resolved_prev_close = 24000.0 if idx_name == "NIFTY" else (78000.0 if idx_name == "SENSEX" else 51000.0)

        open_ref = bar_5m.open if bar_5m else (current_spot if current_spot > 0 else resolved_prev_close)
        strat = OptionMateRBFNStrategy(symbol=idx_name, step_size=cfg["step_size"])
        grid = strat.compute_daily_grid(
            date=today_s,
            spot_open=open_ref,
            prev_close=resolved_prev_close,
            atr_14=cfg["default_atr"],
            vix=14.0,
            bar_5m_equilibrium=bar_5m,
            symbol=idx_name,
        )
        res_dict = {
            "trend_decider": grid.trend_decider,
            "rp1_upper": grid.rp1_upper,
            "rp2_upper": grid.rp2_upper,
            "rp1_lower": grid.rp1_lower,
            "rp2_lower": grid.rp2_lower,
            "target_strike": grid.target_strike,
            "call_strike": grid.call_strike,
            "put_strike": grid.put_strike,
            "bias": grid.recommended_bias,
            "equilibrium_bar_frozen": bar_5m is not None,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }
        rbfn_results[idx_name] = res_dict

        # Freeze to cache if valid open_ref and bar_5m are available
        if bar_5m is not None and open_ref > 0:
            new_cache_symbols[idx_name] = {
                "frozen": True,
                "boundaries": res_dict,
                "open_ref": open_ref,
                "prev_close": resolved_prev_close,
            }
            cache_updated = True

    if cache_updated:
        save_cached_boundaries(today_s, {"date": today_s, "symbols": new_cache_symbols})

    return rbfn_results
