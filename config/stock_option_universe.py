from __future__ import annotations

DEFAULT_STOCK_OPTION_UNIVERSE: dict[str, dict[str, float | int | str]] = {
    "RELIANCE": {
        "lot_size": 250,
        "strike_step": 20,
        "min_oi": 75000,
        "min_volume": 15000,
        "max_spread_pct": 0.90,
        "max_quote_age_sec": 2.0,
    },
    "HDFCBANK": {
        "lot_size": 550,
        "strike_step": 20,
        "min_oi": 60000,
        "min_volume": 12000,
        "max_spread_pct": 1.00,
        "max_quote_age_sec": 2.0,
    },
    "ICICIBANK": {
        "lot_size": 700,
        "strike_step": 10,
        "min_oi": 60000,
        "min_volume": 12000,
        "max_spread_pct": 1.00,
        "max_quote_age_sec": 2.0,
    },
    "SBIN": {
        "lot_size": 1500,
        "strike_step": 10,
        "min_oi": 50000,
        "min_volume": 10000,
        "max_spread_pct": 1.10,
        "max_quote_age_sec": 2.0,
    },
    "TCS": {
        "lot_size": 175,
        "strike_step": 20,
        "min_oi": 40000,
        "min_volume": 8000,
        "max_spread_pct": 1.20,
        "max_quote_age_sec": 2.5,
    },
}
