from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.option_backtest import OptionBacktestConfig, run_option_symbol_backtest


def test_backtest_fallback_rows_never_trade(tmp_path: Path):
    data_path = tmp_path / "fallback.csv"
    pd.DataFrame(
        [
            {
                "timestamp": "2026-04-01 09:15:00",
                "symbol": "NIFTY24APR25500CE",
                "open": 100.0,
                "high": 104.0,
                "low": 99.0,
                "close": 103.0,
                "volume": 200,
                "oi": 300,
                "signal_score": 0.95,
                "target_price": 105.0,
                "stop_price": 98.0,
            }
        ]
    ).to_csv(data_path, index=False)

    result = run_option_symbol_backtest(
        OptionBacktestConfig(
            symbol="NIFTY24APR25500CE",
            data_path=data_path,
            require_bid_ask=True,
            allow_derived_levels=False,
        )
    )

    assert result.summary["signals_total"] == 1
    assert result.summary["executable_signals"] == 0
    assert result.summary["trades_taken"] == 0
    assert result.summary["rejected_reasons"]["truth_quality_fallback"] == 1


def test_backtest_trades_executable_rows_and_hits_target(tmp_path: Path):
    data_path = tmp_path / "clean.csv"
    pd.DataFrame(
        [
            {
                "timestamp": "2026-04-01 09:15:00",
                "symbol": "NIFTY24APR25500CE",
                "open": 100.0,
                "high": 101.0,
                "low": 99.5,
                "close": 100.5,
                "volume": 500,
                "oi": 900,
                "bid": 100.0,
                "ask": 100.5,
                "signal_score": 0.92,
                "selected_for_execution": True,
                "target_price": 103.0,
                "stop_price": 98.0,
            },
            {
                "timestamp": "2026-04-01 09:16:00",
                "symbol": "NIFTY24APR25500CE",
                "open": 100.5,
                "high": 103.5,
                "low": 100.2,
                "close": 103.0,
                "volume": 520,
                "oi": 910,
                "bid": 102.8,
                "ask": 103.1,
                "signal_score": 0.60,
                "selected_for_execution": False,
                "target_price": 104.0,
                "stop_price": 99.0,
            },
        ]
    ).to_csv(data_path, index=False)

    result = run_option_symbol_backtest(
        OptionBacktestConfig(
            symbol="NIFTY24APR25500CE",
            data_path=data_path,
            require_bid_ask=True,
            allow_derived_levels=False,
            quantity=1,
            max_hold_minutes=5,
        )
    )

    assert result.summary["signals_total"] == 2
    assert result.summary["executable_signals"] >= 1
    assert result.summary["trades_taken"] == 1
    assert result.trades[0].exit_reason == "TARGET_HIT"
    assert result.summary["win_rate"] == 1.0
    assert result.summary["profit_factor"] is None
    assert result.summary["profit_factor_unbounded"] is True
