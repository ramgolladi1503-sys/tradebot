from __future__ import annotations

import pandas as pd
import pytest

from research.option_e2e_recertification_v4.option_candle_backtest_v1 import (
    CandleBacktestConfig,
    run_option_candle_backtest,
)


def _catalog() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "session_date": "2026-07-14",
                "contract_symbol": "NIFTY26JUL25000CE",
                "underlying": "NIFTY",
                "option_type": "CE",
                "strike": 25000,
                "expiry": "2026-07-16",
            },
            {
                "session_date": "2026-07-14",
                "contract_symbol": "NIFTY26JUL25000PE",
                "underlying": "NIFTY",
                "option_type": "PE",
                "strike": 25000,
                "expiry": "2026-07-16",
            },
            {
                "session_date": "2026-07-14",
                "contract_symbol": "NIFTY26JUL25100CE",
                "underlying": "NIFTY",
                "option_type": "CE",
                "strike": 25100,
                "expiry": "2026-07-16",
            },
        ]
    )


def _bars(symbol: str, rows: list[tuple[str, float, float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "contract_symbol": symbol,
                "timestamp": timestamp,
                "open": opened,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
            for timestamp, opened, high, low, close, volume in rows
        ]
    )


def _signal(direction: str = "BULLISH", **extra: object) -> pd.DataFrame:
    row = {
        "signal_id": "sig-1",
        "signal_ts": "2026-07-14T09:15:00+05:30",
        "direction": direction,
        "underlying": "NIFTY",
        "underlying_price": 25040,
        "selected_for_execution": True,
    }
    row.update(extra)
    return pd.DataFrame([row])


def _config(**changes: object) -> CandleBacktestConfig:
    values = {
        "quantity": 1,
        "entry_slippage_bps": 0.0,
        "exit_slippage_bps": 0.0,
        "fixed_cost_per_order": 0.0,
        "require_session_catalog": True,
    }
    values.update(changes)
    return CandleBacktestConfig(**values)


def test_bullish_signal_selects_ce_and_enters_next_bar_open() -> None:
    bars = _bars(
        "NIFTY26JUL25000CE",
        [
            ("2026-07-14T09:15:00+05:30", 90, 95, 85, 92, 100),
            ("2026-07-14T09:16:00+05:30", 100, 103, 97, 101, 100),
            ("2026-07-14T09:17:00+05:30", 104, 110, 102, 108, 100),
        ],
    )
    result = run_option_candle_backtest(
        signals=_signal(option_target_price=105, option_stop_price=80),
        contract_catalog=_catalog(),
        option_bars=bars,
        config=_config(),
    )

    assert sum(1 for _ in result.trades) == 1
    trade = result.trades[0]
    assert trade.option_type == "CE"
    assert trade.contract_symbol == "NIFTY26JUL25000CE"
    assert trade.entry_ts.startswith("2026-07-14T09:16:00")
    assert trade.entry_reference_price == 100
    assert trade.exit_reason == "TARGET_HIT"
    assert trade.exit_fill_price == 105
    assert result.summary["result_label"] == "CANDLE_PROXY_ECONOMICS_ONLY"
    assert result.summary["executable_option_pnl_certified"] is False


def test_bearish_signal_selects_pe() -> None:
    bars = _bars(
        "NIFTY26JUL25000PE",
        [
            ("2026-07-14T09:16:00+05:30", 100, 101, 99, 100, 100),
            ("2026-07-14T09:17:00+05:30", 100, 110, 99, 108, 100),
        ],
    )
    result = run_option_candle_backtest(
        signals=_signal("BEARISH", option_target_price=105, option_stop_price=80),
        contract_catalog=_catalog(),
        option_bars=bars,
        config=_config(),
    )

    assert sum(1 for _ in result.trades) == 1
    assert result.trades[0].option_type == "PE"


def test_same_bar_target_and_stop_uses_stop_first() -> None:
    bars = _bars(
        "NIFTY26JUL25000CE",
        [("2026-07-14T09:16:00+05:30", 100, 130, 70, 110, 100)],
    )
    result = run_option_candle_backtest(
        signals=_signal(option_target_price=120, option_stop_price=80),
        contract_catalog=_catalog(),
        option_bars=bars,
        config=_config(),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "STOP_HIT"
    assert trade.exit_fill_price == 80
    assert trade.same_bar_ambiguity is True


def test_gap_through_stop_fills_at_worse_open() -> None:
    bars = _bars(
        "NIFTY26JUL25000CE",
        [
            ("2026-07-14T09:16:00+05:30", 100, 103, 95, 101, 100),
            ("2026-07-14T09:17:00+05:30", 70, 90, 65, 75, 100),
        ],
    )
    result = run_option_candle_backtest(
        signals=_signal(option_target_price=130, option_stop_price=80),
        contract_catalog=_catalog(),
        option_bars=bars,
        config=_config(),
    )

    assert result.trades[0].exit_reference_price == 70
    assert result.trades[0].exit_fill_price == 70


def test_slippage_is_adverse_on_entry_and_exit() -> None:
    bars = _bars(
        "NIFTY26JUL25000CE",
        [
            ("2026-07-14T09:16:00+05:30", 100, 103, 97, 101, 100),
            ("2026-07-14T09:17:00+05:30", 104, 110, 102, 108, 100),
        ],
    )
    result = run_option_candle_backtest(
        signals=_signal(option_target_price=105, option_stop_price=80),
        contract_catalog=_catalog(),
        option_bars=bars,
        config=_config(entry_slippage_bps=100, exit_slippage_bps=100),
    )

    trade = result.trades[0]
    assert trade.entry_fill_price == 101
    assert trade.exit_fill_price == 103.95
    assert trade.net_pnl < 4


def test_zero_volume_rejects_fill() -> None:
    bars = _bars(
        "NIFTY26JUL25000CE",
        [("2026-07-14T09:16:00+05:30", 100, 105, 95, 101, 0)],
    )
    result = run_option_candle_backtest(
        signals=_signal(),
        contract_catalog=_catalog(),
        option_bars=bars,
        config=_config(),
    )

    assert result.summary["trades"] == 0
    assert result.summary["rejections"]["zero_reported_volume"] == 1


def test_costs_are_deducted_from_option_pnl() -> None:
    bars = _bars(
        "NIFTY26JUL25000CE",
        [
            ("2026-07-14T09:16:00+05:30", 100, 103, 97, 101, 100),
            ("2026-07-14T09:17:00+05:30", 104, 110, 102, 108, 100),
        ],
    )
    result = run_option_candle_backtest(
        signals=_signal(option_target_price=105, option_stop_price=80),
        contract_catalog=_catalog(),
        option_bars=bars,
        config=_config(fixed_cost_per_order=20),
    )

    trade = result.trades[0]
    assert trade.gross_pnl == 5
    assert trade.total_costs == 40
    assert trade.net_pnl == -35


def test_neutral_signal_produces_no_trade() -> None:
    result = run_option_candle_backtest(
        signals=_signal("NEUTRAL"),
        contract_catalog=_catalog(),
        option_bars=_bars(
            "NIFTY26JUL25000CE",
            [("2026-07-14T09:16:00+05:30", 100, 105, 95, 101, 100)],
        ),
        config=_config(),
    )

    assert result.summary["trades"] == 0
    assert result.summary["rejections"]["neutral_no_trade"] == 1


def test_duplicate_contract_timestamp_fails_closed() -> None:
    bars = _bars(
        "NIFTY26JUL25000CE",
        [
            ("2026-07-14T09:16:00+05:30", 100, 105, 95, 101, 100),
            ("2026-07-14T09:16:00+05:30", 100, 105, 95, 101, 100),
        ],
    )
    with pytest.raises(ValueError, match="duplicate_contract_timestamp_rows"):
        run_option_candle_backtest(
            signals=_signal(),
            contract_catalog=_catalog(),
            option_bars=bars,
            config=_config(),
        )


def test_repeated_runs_are_deterministic() -> None:
    bars = _bars(
        "NIFTY26JUL25000CE",
        [
            ("2026-07-14T09:16:00+05:30", 100, 103, 97, 101, 100),
            ("2026-07-14T09:17:00+05:30", 104, 110, 102, 108, 100),
        ],
    )
    kwargs = {
        "signals": _signal(option_target_price=105, option_stop_price=80),
        "contract_catalog": _catalog(),
        "option_bars": bars,
        "config": _config(entry_slippage_bps=50, exit_slippage_bps=50),
    }
    first = run_option_candle_backtest(**kwargs)
    second = run_option_candle_backtest(**kwargs)

    assert first.summary == second.summary
    assert [trade.to_dict() for trade in first.trades] == [trade.to_dict() for trade in second.trades]
