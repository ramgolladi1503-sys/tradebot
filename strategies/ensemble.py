from dataclasses import dataclass

@dataclass
class StrategySignal:
    direction: str
    score: float
    reason: str


def _strategy_debug(market_data, strategy_name: str) -> dict:
    if not isinstance(market_data, dict):
        return {}
    root = market_data.setdefault("strategy_debug", {})
    stats = root.setdefault(
        strategy_name,
        {
            "candidates_considered": 0,
            "candidates_rejected_pre_score": 0,
            "rejection_reason_counts": {},
            "candidates_scored": 0,
        },
    )
    return stats


def _debug_count(stats: dict, *, considered=0, rejected=0, scored=0, reason=None) -> None:
    if not isinstance(stats, dict):
        return
    stats["candidates_considered"] = int(stats.get("candidates_considered", 0)) + int(considered)
    stats["candidates_rejected_pre_score"] = int(
        stats.get("candidates_rejected_pre_score", 0)
    ) + int(rejected)
    stats["candidates_scored"] = int(stats.get("candidates_scored", 0)) + int(scored)
    if reason:
        counts = stats.setdefault("rejection_reason_counts", {})
        counts[str(reason)] = int(counts.get(str(reason), 0)) + 1


def _normalize_regime(regime):
    text = str(regime or "").strip().upper()
    if text in ("", "UNKNOWN"):
        return "NEUTRAL"
    if text in ("RANGE", "NEUTRAL", "MEAN_REVERT", "MEANREVERT"):
        return "MEAN_REVERT"
    if text in ("EVENT", "NEWS", "SPIKE"):
        return "EVENT"
    if text in ("TREND", "TRENDING"):
        return "TREND"
    return text

def trend_vwap_signal(ltp, vwap, vwap_slope, atr):
    if not ltp or not vwap:
        return None
    trend = (ltp - vwap) / vwap
    slope = float(vwap_slope or 0.0)
    if trend > 0.0025 and slope > 0.0:
        score = min(1.0, 0.50 + abs(trend) * 100)
        return StrategySignal("BUY_CALL", score, "VWAP strong trend up")
    if trend < -0.0025 and slope < 0.0:
        score = min(1.0, 0.50 + abs(trend) * 100)
        return StrategySignal("BUY_PUT", score, "VWAP strong trend down")
    return None

def mean_reversion_signal(ltp, vwap, rsi_mom):
    if not ltp or not vwap:
        return None
    dev = (ltp - vwap) / vwap
    rsi = float(rsi_mom or 0.0)
    if dev > 0.005:
        score = min(1.0, 0.45 + abs(dev) * 50)
        if rsi < -0.3:
            return StrategySignal("BUY_PUT", score, "Mean reversion down (exhaustion)")
    if dev < -0.005:
        score = min(1.0, 0.45 + abs(dev) * 50)
        if rsi > 0.3:
            return StrategySignal("BUY_CALL", score, "Mean reversion up (exhaustion)")
    return None

def orb_breakout_signal(ltp, orb_high, orb_low, vol_z):
    if not ltp:
        return None
    vol = float(vol_z or 0.0)
    if orb_high and ltp > orb_high and vol > 1.0:
        score = min(1.0, 0.60 + max(vol, 1.0) * 0.1)
        return StrategySignal("BUY_CALL", score, "ORB breakout up (strong volume)")
    if orb_low and ltp < orb_low and vol > 1.0:
        score = min(1.0, 0.60 + max(vol, 1.0) * 0.1)
        return StrategySignal("BUY_PUT", score, "ORB breakdown (strong volume)")
    return None

def volatility_filter(atr, ltp):
    if not atr or not ltp:
        return False
    return (atr / ltp) >= 0.0015

def event_breakout_signal(ltp, atr, ltp_change_window):
    if not ltp or not atr:
        return None
    try:
        from config import config as cfg
        thresh = atr * getattr(cfg, "BASELINE_LTP_ATR_MULT_WINDOW", 0.5)
        if abs(ltp_change_window) >= max(thresh, atr * 0.5):
            direction = "BUY_CALL" if ltp_change_window > 0 else "BUY_PUT"
            score = min(1.0, 0.70 + abs(ltp_change_window) / max(atr, 1e-6))
            return StrategySignal(direction, score, "Event strong breakout")
    except Exception:
        pass
    return None

def micro_pattern_signal(ltp_change_5m, ltp_change_10m):
    """
    5m impulse + 5m pullback pattern for range regime.
    """
    try:
        from config import config as cfg
        up_5m = getattr(cfg, "MICRO_5M_UP_PTS", 15)
        down_5m = getattr(cfg, "MICRO_5M_DOWN_PTS", -15)
        pull = getattr(cfg, "MICRO_10M_PULLBACK_PTS", 10)
        score = getattr(cfg, "MICRO_PATTERN_SCORE", 0.66)
        # If 5m up >= +X and 10m net gain <= +X-pull, expect bounce (buy call)
        if ltp_change_5m >= up_5m and ltp_change_10m <= (ltp_change_5m - pull):
            return StrategySignal("BUY_CALL", score, "Micro pattern pullback")
        # If 5m down <= -X and 10m net loss >= -X+pull (retraced), expect fade (buy put)
        if ltp_change_5m <= down_5m and ltp_change_10m >= (ltp_change_5m + pull):
            return StrategySignal("BUY_PUT", score, "Micro pattern pullback")
    except Exception:
        pass
    return None

def ensemble_signal(market_data):
    debug = _strategy_debug(market_data, "ensemble")
    ltp = market_data.get("ltp", 0)
    vwap = market_data.get("vwap", ltp)
    vwap_slope = market_data.get("vwap_slope", 0)
    rsi_mom = market_data.get("rsi_mom", 0)
    atr = market_data.get("atr", 0)
    orb_high = market_data.get("orb_high")
    orb_low = market_data.get("orb_low")
    vol_z = market_data.get("vol_z", 0)
    ltp_change = market_data.get("ltp_change", 0)
    ltp_change_window = market_data.get("ltp_change_window", 0)

    low_volatility = not volatility_filter(atr, ltp)
    if low_volatility:
        _debug_count(debug, rejected=1, reason="low_volatility_soft")

    regime = _normalize_regime(market_data.get("regime"))
    signals = []

    def _attempt(name, fn, *args):
        _debug_count(debug, considered=1)
        sig = fn(*args)
        if sig is None:
            _debug_count(debug, rejected=1, reason=name)
            return None
        _debug_count(debug, scored=1)
        return sig

    if regime == "EVENT":
        sig = _attempt("event_breakout", event_breakout_signal, ltp, atr, ltp_change_window)
        if sig:
            signals.append(sig)
        sig = _attempt("orb_breakout", orb_breakout_signal, ltp, orb_high, orb_low, vol_z)
        if sig:
            signals.append(sig)
    elif regime == "MEAN_REVERT":
        sig = _attempt("mean_reversion", mean_reversion_signal, ltp, vwap, rsi_mom)
        if sig:
            signals.append(sig)
        sig = _attempt(
            "micro_pattern",
            micro_pattern_signal,
            market_data.get("ltp_change_5m", 0),
            market_data.get("ltp_change_10m", 0),
        )
        if sig:
            signals.append(sig)
    elif regime == "TREND":
        sig = _attempt("trend_vwap", trend_vwap_signal, ltp, vwap, vwap_slope, atr)
        if sig:
            signals.append(sig)
        sig = _attempt("orb_breakout", orb_breakout_signal, ltp, orb_high, orb_low, vol_z)
        if sig:
            signals.append(sig)
    else:
        sig = _attempt("trend_vwap", trend_vwap_signal, ltp, vwap, vwap_slope, atr)
        if sig:
            signals.append(sig)
        sig = _attempt("orb_breakout", orb_breakout_signal, ltp, orb_high, orb_low, vol_z)
        if sig:
            signals.append(sig)
        sig = _attempt("mean_reversion", mean_reversion_signal, ltp, vwap, rsi_mom)
        if sig:
            signals.append(sig)
        sig = _attempt(
            "micro_pattern",
            micro_pattern_signal,
            market_data.get("ltp_change_5m", 0),
            market_data.get("ltp_change_10m", 0),
        )
        if sig:
            signals.append(sig)
        sig = _attempt("event_breakout", event_breakout_signal, ltp, atr, ltp_change_window)
        if sig:
            signals.append(sig)

    # Hard veto on low volatility to avoid chop
    if low_volatility:
        return None

    # Vote by average score, prefer majority direction
    buy_call_score = sum(s.score for s in signals if s.direction == "BUY_CALL")
    buy_put_score = sum(s.score for s in signals if s.direction == "BUY_PUT")
    
    if not signals:
        return None

    if buy_call_score == buy_put_score:
        return None  # Fail immediately on tie to avoid ambiguous conviction

    direction = "BUY_CALL" if buy_call_score > buy_put_score else "BUY_PUT"
    score = max(buy_call_score, buy_put_score) / max(1, len(signals))
    
    # Require strong ensemble conviction
    if score < 0.65:
        return None
        
    reason = "; ".join(s.reason for s in signals if s.direction == direction)
    return StrategySignal(direction, score, reason)

def equity_signal(market_data):
    """
    Simple equity trend filter: require strong VWAP trend and positive slope.
    """
    sig = trend_vwap_signal(
        market_data.get("ltp", 0),
        market_data.get("vwap", 0),
        market_data.get("vwap_slope", 0),
        market_data.get("atr", 0)
    )
    return sig if sig and sig.score >= 0.75 else None

def futures_signal(market_data):
    """
    Futures: allow ORB + trend confirmations.
    """
    sig = orb_breakout_signal(
        market_data.get("ltp", 0),
        market_data.get("orb_high"),
        market_data.get("orb_low"),
        market_data.get("vol_z", 0)
    )
    if sig and sig.score >= 0.7:
        return sig
    return trend_vwap_signal(
        market_data.get("ltp", 0),
        market_data.get("vwap", 0),
        market_data.get("vwap_slope", 0),
        market_data.get("atr", 0)
    )
