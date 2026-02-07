"""
Risk utility helpers.
All percentages are expressed as decimals (e.g., 0.02 = 2%).
"""

from __future__ import annotations


def safe_div(numer: float | int | None, denom: float | int | None, default: float = 0.0) -> float:
    try:
        n = float(numer or 0.0)
        d = float(denom or 0.0)
        if d == 0.0:
            return float(default)
        return n / d
    except Exception:
        return float(default)


def to_pct(value_rupees: float | int | None, equity_high: float | int | None) -> float:
    """
    Convert rupees to percent of equity_high.
    """
    return safe_div(value_rupees, equity_high, default=0.0)
