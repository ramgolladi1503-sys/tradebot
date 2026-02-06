from __future__ import annotations

from pathlib import Path
import json
from config import config as cfg


def _adaptive_multiplier(strategy_name: str | None) -> float:
    if not strategy_name:
        return 1.0
    try:
        path = Path("logs/strategy_perf.json")
        if not path.exists():
            return 1.0
        raw = json.loads(path.read_text())
        stats = raw.get("stats", {})
        st = stats.get(strategy_name, {})
        trades = st.get("trades", 0)
        wins = st.get("wins", 0)
        if trades < 10:
            return 1.0
        win_rate = wins / max(1, trades)
        # Scale 0.8–1.2 around 50% win-rate
        mult = 0.8 + (win_rate - 0.5) * 0.8
        return max(0.6, min(1.2, mult))
    except Exception:
        return 1.0


def compute_trade_score(market_data: dict, opt: dict, direction: str, rr: float | None, strategy_name: str | None = None):
    """
    Multi-factor trade scoring engine.
    Returns dict with score, alignment, components, and issues.
    """
    components = {}
    issues = []

    # Inputs
    ltp = market_data.get("ltp", 0) or 0
    vwap = market_data.get("vwap", ltp) or ltp
    htf_dir = (market_data.get("htf_dir") or "FLAT").upper()
    vwap_slope = market_data.get("vwap_slope", 0) or 0
    vol_z = market_data.get("vol_z", 0) or 0
    atr = market_data.get("atr", 0) or 0
    atr_pct = (atr / ltp) if ltp else 0
    day_type = (market_data.get("day_type") or "").upper()
    regime = (market_data.get("regime") or "").upper()

    opt_ltp = opt.get("ltp") or 0
    bid = opt.get("bid") or 0
    ask = opt.get("ask") or 0
    spread_pct = (ask - bid) / opt_ltp if opt_ltp else 1
    volume = opt.get("volume", 0) or 0
    oi_build = (opt.get("oi_build") or "FLAT").upper()
    iv = opt.get("iv")
    iv_z = opt.get("iv_z")
    delta = opt.get("delta")
    theta = opt.get("theta")

    # 1) Trend alignment
    trend = 20
    if direction == "BUY_CALL":
        if ltp >= vwap and htf_dir == "UP" and vwap_slope >= 0:
            trend = 100
        elif ltp >= vwap:
            trend = 70
        elif htf_dir == "UP":
            trend = 50
    else:
        if ltp <= vwap and htf_dir == "DOWN" and vwap_slope <= 0:
            trend = 100
        elif ltp <= vwap:
            trend = 70
        elif htf_dir == "DOWN":
            trend = 50
    components["trend"] = trend

    # 2) Regime alignment
    if day_type in ("TREND_DAY", "RANGE_TREND_DAY", "TREND_RANGE_DAY"):
        regime_score = 90 if ((direction == "BUY_CALL" and htf_dir == "UP") or (direction == "BUY_PUT" and htf_dir == "DOWN")) else 60
    elif day_type in ("RANGE_DAY", "RANGE_VOLATILE"):
        regime_score = 40
        issues.append("Range day: directional risk")
    elif day_type in ("EVENT_DAY", "PANIC_DAY", "EXPIRY_DAY"):
        regime_score = 30
        issues.append("Event/expiry day risk")
    else:
        regime_score = 60
    components["regime"] = regime_score

    # 3) Risk/Reward
    if rr is None:
        rr_score = 0
        issues.append("RR missing")
    elif rr >= 2.0:
        rr_score = 100
    elif rr >= 1.5:
        rr_score = 70
    elif rr >= 1.2:
        rr_score = 50
    else:
        rr_score = 0
        issues.append("RR below 1.2")
    components["rr"] = rr_score

    # 4) Volatility context
    vol_score = 70
    if iv_z is not None and iv_z > 1.5:
        vol_score = 35
        issues.append("IV elevated")
    elif iv_z is not None and iv_z < -0.5:
        vol_score = 85
    if vol_z >= getattr(cfg, "EVENT_VOL_Z", 1.0):
        vol_score -= 15
        issues.append("High vol regime")
    if atr_pct >= getattr(cfg, "EVENT_ATR_PCT", 0.004):
        vol_score -= 10
    vol_score = max(0, min(100, vol_score))
    components["volatility"] = vol_score

    # 5) OI flow confirmation
    if direction == "BUY_CALL":
        if oi_build == "LONG":
            oi_score = 100
        elif oi_build == "SHORT_COVER":
            oi_score = 70
        elif oi_build == "FLAT":
            oi_score = 50
        else:
            oi_score = 25
    else:
        if oi_build == "SHORT":
            oi_score = 100
        elif oi_build == "LONG_LIQ":
            oi_score = 70
        elif oi_build == "FLAT":
            oi_score = 50
        else:
            oi_score = 25
    components["oi_flow"] = oi_score

    # 6) Liquidity
    if spread_pct <= 0.005 and volume >= 50000:
        liq = 100
    elif spread_pct <= getattr(cfg, "MAX_SPREAD_PCT", 0.015) and volume >= 10000:
        liq = 70
    elif spread_pct <= getattr(cfg, "MAX_SPREAD_PCT", 0.015):
        liq = 55
    else:
        liq = 30
        issues.append("Wide spread / low volume")
    components["liquidity"] = liq

    # 7) Multi-timeframe structure
    mtf = 40
    if direction == "BUY_CALL" and htf_dir == "UP" and ltp >= vwap:
        mtf = 90
    elif direction == "BUY_PUT" and htf_dir == "DOWN" and ltp <= vwap:
        mtf = 90
    elif htf_dir in ("UP", "DOWN"):
        mtf = 60
    components["mtf"] = mtf

    # 8) Event/news dampener
    if day_type in ("EVENT_DAY", "PANIC_DAY"):
        event_score = 30
    elif day_type == "EXPIRY_DAY":
        event_score = 40
    else:
        event_score = 100
    components["event"] = event_score

    # 9) Greeks sanity
    if delta is not None and (abs(delta) < getattr(cfg, "DELTA_MIN", 0.25) or abs(delta) > getattr(cfg, "DELTA_MAX", 0.7)):
        components["greeks"] = 40
        issues.append("Delta out of band")
    else:
        components["greeks"] = 80

    # Weighted score
    w = {
        "trend": 0.25,
        "regime": 0.15,
        "oi_flow": 0.15,
        "volatility": 0.10,
        "liquidity": 0.10,
        "rr": 0.10,
        "mtf": 0.10,
        "event": 0.05,
    }
    score = 0.0
    for k, weight in w.items():
        score += weight * components.get(k, 0)

    # Adaptive weighting (recent strategy performance)
    score *= _adaptive_multiplier(strategy_name)

    # Strategy alignment meter (trend + mtf + regime)
    alignment = (components["trend"] * 0.4) + (components["mtf"] * 0.3) + (components["regime"] * 0.3)

    return {
        "score": max(0.0, min(100.0, score)),
        "alignment": max(0.0, min(100.0, alignment)),
        "components": components,
        "issues": issues,
        "day_type": day_type,
        "regime": regime,
    }

