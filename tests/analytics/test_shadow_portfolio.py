from __future__ import annotations

import pandas as pd

from core.analytics.shadow_portfolio import simulate_shadow_trade


def test_simulate_shadow_trade_hits_target():
    trade = {
        "ts_epoch_ms": 1772164800000,
        "entry_price": 100.0,
        "target_price": 104.0,
        "stop_price": 97.0,
        "is_sell": False,
        "qty_units": 1.0,
        "spread_pct": 0.002,
    }
    candles = pd.DataFrame(
        [
            {"time_ms": 1772164800000, "open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5},
            {"time_ms": 1772164860000, "open": 100.5, "high": 104.2, "low": 100.2, "close": 103.9},
        ]
    )

    result = simulate_shadow_trade(
        trade,
        candles,
        lookahead_minutes=30,
        slippage_model="bps",
        slippage_bps=0.0,
        spread_slippage_mult=0.0,
        entry_mode="MARK",
    )

    assert result["status"] == "SIMULATED"
    assert result["target_hit"] is True
    assert result["exit_reason"] == "TARGET_HIT"
