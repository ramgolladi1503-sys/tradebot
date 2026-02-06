from dataclasses import dataclass

@dataclass
class StrategySignal:
    direction: str
    score: float
    reason: str

def trend_vwap_signal(ltp, vwap, vwap_slope, atr):
    if not ltp or not vwap:
        return None
    trend = (ltp - vwap) / vwap
    if trend > 0.002 and vwap_slope > 0:
        score = min(1.0, 0.5 + abs(trend) * 50)
        return StrategySignal("BUY_CALL", score, "VWAP trend up")
    if trend < -0.002 and vwap_slope < 0:
        score = min(1.0, 0.5 + abs(trend) * 50)
        return StrategySignal("BUY_PUT", score, "VWAP trend down")
    return None

def mean_reversion_signal(ltp, vwap, rsi_mom):
    if not ltp or not vwap:
        return None
    dev = (ltp - vwap) / vwap
    if dev > 0.004 and rsi_mom < 0:
        score = min(1.0, 0.4 + abs(dev) * 40)
        return StrategySignal("BUY_PUT", score, "Mean reversion down")
    if dev < -0.004 and rsi_mom > 0:
        score = min(1.0, 0.4 + abs(dev) * 40)
        return StrategySignal("BUY_CALL", score, "Mean reversion up")
    return None

def orb_breakout_signal(ltp, orb_high, orb_low, vol_z):
    if not ltp:
        return None
    if orb_high and ltp > orb_high and vol_z > 0.5:
        score = min(1.0, 0.6 + vol_z * 0.2)
        return StrategySignal("BUY_CALL", score, "ORB breakout up")
    if orb_low and ltp < orb_low and vol_z > 0.5:
        score = min(1.0, 0.6 + vol_z * 0.2)
        return StrategySignal("BUY_PUT", score, "ORB breakdown")
    return None

def volatility_filter(atr, ltp):
    if not atr or not ltp:
        return False
    return (atr / ltp) >= 0.001

def event_breakout_signal(ltp, atr, ltp_change_window):
    if not ltp or not atr:
        return None
    try:
        from config import config as cfg
        thresh = atr * getattr(cfg, "BASELINE_LTP_ATR_MULT_WINDOW", 0.005)
        if abs(ltp_change_window) >= thresh:
            direction = "BUY_CALL" if ltp_change_window > 0 else "BUY_PUT"
            score = min(1.0, 0.65 + abs(ltp_change_window) / max(atr, 1e-6))
            return StrategySignal(direction, score, "Event breakout")
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

    if not volatility_filter(atr, ltp):
        return None

    regime = market_data.get("regime")
    signals = []
    sig = trend_vwap_signal(ltp, vwap, vwap_slope, atr)
    if sig and regime in (None, "TREND"):
        signals.append(sig)
    sig = mean_reversion_signal(ltp, vwap, rsi_mom)
    if sig and regime in (None, "MEAN_REVERT"):
        signals.append(sig)
    sig = orb_breakout_signal(ltp, orb_high, orb_low, vol_z)
    if sig and regime in (None, "TREND"):
        signals.append(sig)

    if not signals:
        # fallback: short-term momentum when indicators missing
        try:
            from config import config as cfg
            atr = atr or 0
            if atr > 0 and abs(ltp_change) > atr * getattr(cfg, "LTP_MOM_ATR_MULT", 0.2):
                direction = "BUY_CALL" if ltp_change > 0 else "BUY_PUT"
                score = min(1.0, 0.6 + abs(ltp_change) / max(atr, 1e-6))
                reason = "LTP momentum fallback"
                return StrategySignal(direction, score, reason)
            if atr > 0 and abs(ltp_change_window) > atr * getattr(cfg, "BASELINE_LTP_ATR_MULT_WINDOW", 0.02):
                direction = "BUY_CALL" if ltp_change_window > 0 else "BUY_PUT"
                score = min(1.0, 0.58 + abs(ltp_change_window) / max(atr, 1e-6))
                reason = "LTP window momentum"
                return StrategySignal(direction, score, reason)
        except Exception:
            pass
        return None

    # Vote by average score, prefer majority direction
    buy_call_score = sum(s.score for s in signals if s.direction == "BUY_CALL")
    buy_put_score = sum(s.score for s in signals if s.direction == "BUY_PUT")
    if buy_call_score == buy_put_score:
        return None

    direction = "BUY_CALL" if buy_call_score > buy_put_score else "BUY_PUT"
    score = max(buy_call_score, buy_put_score) / max(1, len(signals))
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
