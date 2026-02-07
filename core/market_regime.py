# core/market_regime.py
# LEGACY WRAPPER; DO NOT ADD LOGIC

from core.market_data import get_current_regime


def detect_market_regime():
    """
    Legacy API wrapper. Returns canonical regime output plus legacy fields.
    """
    snap = get_current_regime("NIFTY")
    probs = snap.get("regime_probs") or {}
    max_prob = max(probs.values()) if probs else 0.0
    return {
        "regime": snap.get("primary_regime", "NEUTRAL"),
        "confidence": int(round(max_prob * 100)),
        "reason": "LEGACY WRAPPER; DO NOT ADD LOGIC",
        "regime_probs": snap.get("regime_probs"),
        "regime_entropy": snap.get("regime_entropy"),
        "unstable_regime_flag": snap.get("unstable_regime_flag"),
        "regime_ts": snap.get("regime_ts"),
    }
