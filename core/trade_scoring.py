from __future__ import annotations

from pathlib import Path
import json
from config import config as cfg


def _latest_exec_quality():
    try:
        from core.fill_quality import get_latest_exec_quality
        return get_latest_exec_quality()
    except Exception:
        return None


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


def compute_confluence_score(score_pack: dict | None) -> float:
    """
    Deterministic confluence score in [0, 1] derived from score+alignment.
    """
    pack = score_pack or {}
    try:
        score = float(pack.get("score", 0.0) or 0.0)
    except Exception:
        score = 0.0
    try:
        alignment = float(pack.get("alignment", 0.0) or 0.0)
    except Exception:
        alignment = 0.0
    blended = (0.6 * score) + (0.4 * alignment)
    return max(0.0, min(1.0, blended / 100.0))


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
    shock_score = float(market_data.get("shock_score") or 0.0)
    uncertainty = float(market_data.get("uncertainty_index") or 0.0)
    macro_bias = float(market_data.get("macro_direction_bias") or 0.0)

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

    # 9) News shock / macro bias
    news_score = 100.0
    news_score -= min(80.0, shock_score * 80.0)
    news_score -= min(30.0, uncertainty * 30.0)
    if shock_score >= getattr(cfg, "NEWS_SHOCK_EVENT_THRESHOLD", 0.4):
        issues.append("News shock elevated")
    if shock_score >= getattr(cfg, "NEWS_SHOCK_BLOCK_THRESHOLD", 0.7):
        news_score = 0.0
        issues.append("News shock extreme")
    bias_penalty = getattr(cfg, "NEWS_SHOCK_BIAS_PENALTY", 15)
    if macro_bias >= 0.2 and direction == "BUY_PUT":
        news_score -= bias_penalty
        issues.append("Macro bias bullish")
    if macro_bias <= -0.2 and direction == "BUY_CALL":
        news_score -= bias_penalty
        issues.append("Macro bias bearish")
    components["news_shock"] = max(0.0, min(100.0, news_score))

    # 10) Greeks sanity
    if delta is not None and (abs(delta) < getattr(cfg, "DELTA_MIN", 0.25) or abs(delta) > getattr(cfg, "DELTA_MAX", 0.7)):
        components["greeks"] = 40
        issues.append("Delta out of band")
    else:
        components["greeks"] = 80

    # Weighted score
    w = {
        "trend": 0.24,
        "regime": 0.15,
        "oi_flow": 0.15,
        "volatility": 0.10,
        "liquidity": 0.10,
        "rr": 0.10,
        "mtf": 0.08,
        "event": 0.03,
        "news_shock": 0.05,
    }
    score = 0.0
    for k, weight in w.items():
        score += weight * components.get(k, 0)

    # Optional cross-asset penalty (do not block)
    try:
        cross_q = market_data.get("cross_asset_quality", {}) or {}
        optional = set(getattr(cfg, "CROSS_OPTIONAL_FEEDS", []) or [])
        stale = set(cross_q.get("stale_feeds", []) or [])
        missing_map = cross_q.get("missing") or {}
        missing = set(k for k, v in missing_map.items() if not str(v).startswith("disabled"))
        bad_optional = (stale | missing) & optional
        if bad_optional:
            penalty = float(getattr(cfg, "CROSS_ASSET_OPTIONAL_SCORE_PENALTY", 8))
            score = max(0.0, score - penalty)
            issues.append("cross_asset_optional_stale")
    except Exception:
        pass

    # Execution quality influence
    try:
        exec_q = market_data.get("execution_quality_score")
        if exec_q is None:
            exec_q = _latest_exec_quality()
        if exec_q is not None:
            if float(exec_q) < float(getattr(cfg, "EXEC_QUALITY_BLOCK_BELOW", 35)):
                issues.append("exec_quality_block")
                score = 0.0
            elif float(exec_q) < float(getattr(cfg, "EXEC_QUALITY_MIN", 55)):
                penalty = float(getattr(cfg, "EXEC_QUALITY_PENALTY", 10))
                score = max(0.0, score - penalty)
                issues.append("exec_quality_low")
    except Exception:
        pass

    # Adaptive weighting (recent strategy performance)
    score *= _adaptive_multiplier(strategy_name)

    # Strategy alignment meter (trend + mtf + regime)
    alignment = (components["trend"] * 0.4) + (components["mtf"] * 0.3) + (components["regime"] * 0.3)

    result = {
        "score": max(0.0, min(100.0, score)),
        "alignment": max(0.0, min(100.0, alignment)),
        "components": components,
        "issues": issues,
        "day_type": day_type,
        "regime": regime,
    }
    result["confluence_score"] = compute_confluence_score(result)
    return result
