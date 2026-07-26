from __future__ import annotations

import pandas as pd
import pytest

from research.option_e2e_recertification_v4.option_candle_backtest_v1 import (
    CandleBacktestConfig,
    run_option_candle_backtest,
)


def test_duplicate_explicit_signal_ids_fail_closed() -> None:
    signals = pd.DataFrame(
        [
            {
                "signal_id": "duplicate",
                "signal_ts": "2026-07-14T09:15:00+05:30",
                "direction": "BULLISH",
                "underlying": "NIFTY",
                "underlying_price": 25000,
            },
            {
                "signal_id": "duplicate",
                "signal_ts": "2026-07-14T09:16:00+05:30",
                "direction": "BEARISH",
                "underlying": "NIFTY",
                "underlying_price": 25000,
            },
        ]
    )
    catalog = pd.DataFrame(
        [
            {
                "session_date": "2026-07-14",
                "contract_symbol": "NIFTY26JUL25000CE",
                "underlying": "NIFTY",
                "option_type": "CE",
                "strike": 25000,
                "expiry": "2026-07-16",
            }
        ]
    )
    bars = pd.DataFrame(
        [
            {
                "contract_symbol": "NIFTY26JUL25000CE",
                "timestamp": "2026-07-14T09:17:00+05:30",
                "open": 100,
                "high": 105,
                "low": 95,
                "close": 101,
                "volume": 100,
            }
        ]
    )

    with pytest.raises(ValueError, match="duplicate_signal_ids"):
        run_option_candle_backtest(
            signals=signals,
            contract_catalog=catalog,
            option_bars=bars,
            config=CandleBacktestConfig(
                fixed_cost_per_order=0,
                entry_slippage_bps=0,
                exit_slippage_bps=0,
                require_session_catalog=True,
            ),
        )
