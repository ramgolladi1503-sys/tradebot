from __future__ import annotations

from typing import Any


def _safe_float(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:
        return None


def estimate_fill_probability(candidate: dict[str, Any]) -> float:
    spread = _safe_float(candidate.get("spread_pct")) or 5.0
    volume = _safe_float(candidate.get("volume")) or 0.0
    oi = _safe_float(candidate.get("oi")) or 0.0
    quote_age = _safe_float(candidate.get("quote_age_sec")) or 5.0

    spread_factor = max(0.0, min(1.0, 1 - (spread / 2.0)))
    liquidity_factor = max(0.0, min(1.0, (volume / 20000.0 + oi / 100000.0) / 2))
    freshness_factor = max(0.0, min(1.0, 1 - (quote_age / 3.0)))

    return round(0.4 * spread_factor + 0.4 * liquidity_factor + 0.2 * freshness_factor, 4)


def estimate_slippage(candidate: dict[str, Any]) -> float:
    spread = _safe_float(candidate.get("spread_pct")) or 1.0
    base_slippage = spread * 0.5
    return round(base_slippage, 4)


def simulate_fill(candidate: dict[str, Any]) -> dict[str, Any]:
    fill_prob = estimate_fill_probability(candidate)
    slippage = estimate_slippage(candidate)

    entry = _safe_float(candidate.get("entry_price")) or 0.0
    simulated_fill_price = entry * (1 + (slippage / 100.0))

    return {
        "fill_probability": fill_prob,
        "expected_slippage_pct": slippage,
        "simulated_fill_price": round(simulated_fill_price, 2),
        "executable": fill_prob > 0.6,
    }
