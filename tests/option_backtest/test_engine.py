from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from core.option_backtest import OptionBacktestConfig, run_option_symbol_backtest
from core.option_backtest.models import OptionBacktestCostConfig, ResearchMode


def _base_row(**overrides):
    row = {
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
        "bid_qty": 50,
        "ask_qty": 50,
        "signal_score": 0.92,
        "selected_for_execution": True,
        "target_price": 103.0,
        "stop_price": 98.0,
    }
    row.update(overrides)
    return row


def test_backtest_fallback_rows_never_trade(tmp_path: Path):
    data_path = tmp_path / "fallback.csv"
    pd.DataFrame(
        [{
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
        }]
    ).to_csv(data_path, index=False)

    result = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, require_bid_ask=True, allow_derived_levels=False))
    assert result.summary["signals_total"] == 1
    assert result.summary["executable_signals"] == 0
    assert result.summary["trades_taken"] == 0
    assert result.summary["rejected_reasons"]["truth_quality_fallback"] == 1


def test_backtest_trades_executable_rows_and_hits_target(tmp_path: Path):
    data_path = tmp_path / "clean.csv"
    pd.DataFrame(
        [
            _base_row(),
            _base_row(timestamp="2026-04-01 09:16:00", open=100.5, high=102.5, low=100.0, close=100.4, volume=520, oi=910, bid=100.2, ask=100.5, signal_score=0.60, selected_for_execution=False, target_price=104.0, stop_price=99.0),
            _base_row(timestamp="2026-04-01 09:17:00", open=102.0, high=103.5, low=101.8, close=103.0, volume=530, oi=920, bid=102.8, ask=103.1, signal_score=0.40, selected_for_execution=False, target_price=104.0, stop_price=99.0),
        ]
    ).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, require_bid_ask=True, allow_derived_levels=False, quantity=1, max_hold_minutes=5))
    assert result.summary["signals_total"] == 3
    assert result.summary["executable_signals"] >= 1
    assert result.summary["trades_taken"] == 1
    assert result.trades[0].exit_reason == "TARGET_HIT"
    assert result.trades[0].entry_ts == "2026-04-01T09:16:00+05:30"
    assert result.trades[0].exit_fill_source == "quote_side"
    assert result.summary["win_rate"] == 1.0
    assert result.summary["profit_factor"] is None
    assert result.summary["profit_factor_unbounded"] is True


def test_certification_mode_rejects_missing_signal_timing_provenance(tmp_path: Path):
    data_path = tmp_path / "strict_missing_timing.csv"
    pd.DataFrame([
        _base_row(underlying="NIFTY", option_type="CE", strike=25500, expiry="2026-04-30", provider="upstox", dataset_hash="hash-1", bar_interval="1m", quote_timestamp="2026-04-01 09:14:40"),
        _base_row(timestamp="2026-04-01 09:16:00", underlying="NIFTY", option_type="CE", strike=25500, expiry="2026-04-30", provider="upstox", dataset_hash="hash-1", bar_interval="1m", quote_timestamp="2026-04-01 09:15:40", selected_for_execution=False, signal_score=0.2),
    ]).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH, allow_derived_levels=False))
    assert result.summary["trades_taken"] == 0
    assert result.summary["executable_signals"] == 0
    assert result.summary["rejected_reasons"]["missing_signal_timing_provenance"] == 2


def test_certification_mode_rejects_same_candle_earliest_entry_as_ambiguous(tmp_path: Path):
    data_path = tmp_path / "strict_ambiguous_timing.csv"
    pd.DataFrame([
        _base_row(underlying="NIFTY", option_type="CE", strike=25500, expiry="2026-04-30", provider="upstox", dataset_hash="hash-1", bar_interval="1m", quote_timestamp="2026-04-01 09:14:40", feature_cutoff_ts="2026-04-01 09:15:00", signal_ts="2026-04-01 09:15:00", earliest_entry_ts="2026-04-01 09:15:00"),
        _base_row(timestamp="2026-04-01 09:16:00", underlying="NIFTY", option_type="CE", strike=25500, expiry="2026-04-30", provider="upstox", dataset_hash="hash-1", bar_interval="1m", quote_timestamp="2026-04-01 09:15:40", feature_cutoff_ts="2026-04-01 09:16:00", signal_ts="2026-04-01 09:16:00", earliest_entry_ts="2026-04-01 09:16:00", selected_for_execution=False, signal_score=0.2),
    ]).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH, allow_derived_levels=False))
    assert result.summary["trades_taken"] == 0
    assert result.summary["rejected_reasons"]["ambiguous_signal_timing"] == 2


def test_signal_enters_on_first_eligible_later_candle_in_certification_mode(tmp_path: Path):
    data_path = tmp_path / "strict_timing.csv"
    pd.DataFrame([
        _base_row(underlying="NIFTY", option_type="CE", strike=25500, expiry="2026-04-30", provider="upstox", dataset_hash="hash-1", bar_interval="1m", quote_timestamp="2026-04-01 09:14:40", feature_cutoff_ts="2026-04-01 09:15:00", signal_ts="2026-04-01 09:15:00", earliest_entry_ts="2026-04-01 09:16:00", high=104.0, low=97.0),
        _base_row(timestamp="2026-04-01 09:16:00", underlying="NIFTY", option_type="CE", strike=25500, expiry="2026-04-30", provider="upstox", dataset_hash="hash-1", bar_interval="1m", quote_timestamp="2026-04-01 09:15:40", feature_cutoff_ts="2026-04-01 09:16:00", signal_ts="2026-04-01 09:16:00", earliest_entry_ts="2026-04-01 09:17:00", open=100.5, high=102.2, low=100.0, close=100.4, bid=100.2, ask=100.5, selected_for_execution=False, signal_score=0.2),
        _base_row(timestamp="2026-04-01 09:17:00", underlying="NIFTY", option_type="CE", strike=25500, expiry="2026-04-30", provider="upstox", dataset_hash="hash-1", bar_interval="1m", quote_timestamp="2026-04-01 09:16:40", feature_cutoff_ts="2026-04-01 09:17:00", signal_ts="2026-04-01 09:17:00", earliest_entry_ts="2026-04-01 09:18:00", open=101.8, high=103.5, low=101.6, close=103.0, bid=102.8, ask=103.1, bid_qty=50, ask_qty=50, selected_for_execution=False, signal_score=0.1),
    ]).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH, allow_derived_levels=False))
    trade = result.trades[0]
    assert result.summary["trades_taken"] == 1
    assert trade.entry_ts == "2026-04-01T09:16:00+05:30"
    assert trade.exit_ts == "2026-04-01T09:17:00+05:30"
    assert trade.exit_price == 102.8


def test_certification_mode_rejects_entry_quote_captured_before_signal(tmp_path: Path):
    data_path = tmp_path / "strict_pre_signal_entry_quote.csv"
    pd.DataFrame([
        _base_row(
            underlying="NIFTY",
            option_type="CE",
            strike=25500,
            expiry="2026-04-30",
            provider="upstox",
            dataset_hash="hash-1",
            bar_interval="1m",
            quote_timestamp="2026-04-01 09:14:55",
            feature_cutoff_ts="2026-04-01 09:15:00",
            signal_ts="2026-04-01 09:15:55",
            earliest_entry_ts="2026-04-01 09:15:55",
            setup_id="breakout",
            regime="trend",
            is_oos=False,
        ),
        _base_row(
            timestamp="2026-04-01 09:16:00",
            underlying="NIFTY",
            option_type="CE",
            strike=25500,
            expiry="2026-04-30",
            provider="upstox",
            dataset_hash="hash-1",
            bar_interval="1m",
            quote_timestamp="2026-04-01 09:15:50",
            bid=100.2,
            ask=100.5,
            bid_qty=50,
            ask_qty=50,
            close=100.4,
            selected_for_execution=False,
            signal_score=0.2,
            setup_id="breakout",
            regime="trend",
            is_oos=False,
        ),
        _base_row(
            timestamp="2026-04-01 09:17:00",
            underlying="NIFTY",
            option_type="CE",
            strike=25500,
            expiry="2026-04-30",
            provider="upstox",
            dataset_hash="hash-1",
            bar_interval="1m",
            quote_timestamp="2026-04-01 09:16:50",
            open=101.8,
            high=103.5,
            low=101.6,
            close=103.0,
            bid=102.8,
            ask=103.1,
            bid_qty=50,
            ask_qty=50,
            selected_for_execution=False,
            signal_score=0.1,
            setup_id="breakout",
            regime="trend",
            is_oos=False,
        ),
    ]).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(
        OptionBacktestConfig(
            symbol="NIFTY24APR25500CE",
            data_path=data_path,
            research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH,
            allow_derived_levels=False,
        )
    )
    assert result.summary["trades_taken"] == 0
    assert result.summary["rejected_reasons"]["entry_quote_before_signal"] == 1


def test_trade_cannot_exit_using_signal_candle_range(tmp_path: Path):
    data_path = tmp_path / "signal_candle_cheat.csv"
    pd.DataFrame([
        _base_row(high=105.0, low=97.5, feature_cutoff_ts="2026-04-01 09:15:00", signal_ts="2026-04-01 09:15:00", earliest_entry_ts="2026-04-01 09:16:00"),
        _base_row(timestamp="2026-04-01 09:16:00", open=100.5, high=102.0, low=100.0, close=100.4, bid=100.2, ask=100.5, selected_for_execution=False, signal_score=0.3),
        _base_row(timestamp="2026-04-01 09:17:00", open=101.5, high=103.5, low=101.2, close=103.0, bid=102.8, ask=103.1, selected_for_execution=False, signal_score=0.2),
    ]).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, allow_derived_levels=False))
    assert result.summary["trades_taken"] == 1
    assert result.trades[0].entry_ts != "2026-04-01T09:15:00+05:30"
    assert result.trades[0].exit_ts != "2026-04-01T09:15:00+05:30"
    assert result.trades[0].exit_price == 102.8


def test_timeout_uses_elapsed_time_not_row_count_with_missing_bars(tmp_path: Path):
    data_path = tmp_path / "elapsed_timeout.csv"
    pd.DataFrame([
        _base_row(feature_cutoff_ts="2026-04-01 09:15:00", signal_ts="2026-04-01 09:15:00", earliest_entry_ts="2026-04-01 09:16:00"),
        _base_row(timestamp="2026-04-01 09:16:00", open=100.5, high=101.5, low=100.0, close=100.4, bid=100.2, ask=100.5, selected_for_execution=False, signal_score=0.2),
        _base_row(timestamp="2026-04-01 10:30:00", open=101.0, high=101.2, low=100.9, close=101.1, bid=101.0, ask=101.2, selected_for_execution=False, signal_score=0.1),
    ]).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, allow_derived_levels=False, max_hold_minutes=30))
    trade = result.trades[0]
    assert trade.exit_reason == "TIME_EXIT"
    assert trade.hold_minutes == 30.0
    assert trade.exit_ts == "2026-04-01T09:46:00+05:30"
    assert trade.exit_price == 100.2


def test_same_entry_candle_stop_target_ambiguity_remains_conservative(tmp_path: Path):
    data_path = tmp_path / "entry_ambiguity.csv"
    pd.DataFrame([
        _base_row(feature_cutoff_ts="2026-04-01 09:15:00", signal_ts="2026-04-01 09:15:00", earliest_entry_ts="2026-04-01 09:16:00"),
        _base_row(timestamp="2026-04-01 09:16:00", open=100.5, high=103.5, low=97.5, close=100.4, bid=100.2, ask=100.5, selected_for_execution=False, signal_score=0.2),
    ]).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, allow_derived_levels=False, max_hold_minutes=5))
    trade = result.trades[0]
    assert trade.exit_reason == "STOP_HIT"
    assert trade.timing_ambiguity is True
    assert result.summary["diagnostics"]["timing_ambiguity_count"] == 1
    assert trade.exit_price == 100.2


def test_proxy_mode_derives_timing_but_remains_proxy_research(tmp_path: Path):
    data_path = tmp_path / "proxy_timing.csv"
    pd.DataFrame([
        _base_row(),
        _base_row(timestamp="2026-04-01 09:16:00", open=100.5, high=102.0, low=100.0, close=100.4, bid=100.2, ask=100.5, selected_for_execution=False, signal_score=0.2),
        _base_row(timestamp="2026-04-01 09:17:00", open=101.8, high=103.5, low=101.6, close=103.0, bid=102.8, ask=103.1, selected_for_execution=False, signal_score=0.1),
    ]).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, research_mode=ResearchMode.PROXY_RESEARCH, allow_derived_levels=False))
    assert result.config.research_mode == ResearchMode.PROXY_RESEARCH
    assert result.summary["trades_taken"] == 1
    assert result.summary["diagnostics"]["derived_timing_rows"] >= 1
    assert result.summary["result_label"] == "PROXY_RESEARCH_ONLY"


def test_strict_mode_loader_rejects_missing_exit_bid_ask_rows(tmp_path: Path):
    data_path = tmp_path / "strict_missing_exit_quotes.csv"
    pd.DataFrame([
        _base_row(underlying="NIFTY", option_type="CE", strike=25500, expiry="2026-04-30", provider="upstox", dataset_hash="hash-1", bar_interval="1m", quote_timestamp="2026-04-01 09:14:40", feature_cutoff_ts="2026-04-01 09:15:00", signal_ts="2026-04-01 09:15:00", earliest_entry_ts="2026-04-01 09:16:00"),
        _base_row(timestamp="2026-04-01 09:16:00", underlying="NIFTY", option_type="CE", strike=25500, expiry="2026-04-30", provider="upstox", dataset_hash="hash-1", bar_interval="1m", quote_timestamp="2026-04-01 09:15:40", bid=100.2, ask=100.5, bid_qty=50, ask_qty=50, close=100.4, selected_for_execution=False, signal_score=0.2),
        _base_row(timestamp="2026-04-01 09:17:00", underlying="NIFTY", option_type="CE", strike=25500, expiry="2026-04-30", provider="upstox", dataset_hash="hash-1", bar_interval="1m", quote_timestamp="2026-04-01 09:16:40", bid="", ask="", open=101.8, high=103.5, low=101.6, close=103.0, selected_for_execution=False, signal_score=0.1),
    ]).to_csv(data_path, index=False)
    with pytest.raises(ValueError, match="missing_required_bid_ask_rows"):
        run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH, allow_derived_levels=False))


def test_strict_mode_missing_book_qty_fails_closed_without_liquidity_fallback(tmp_path: Path):
    data_path = tmp_path / "strict_missing_book_qty.csv"
    pd.DataFrame([
        _base_row(underlying="NIFTY", option_type="CE", strike=25500, expiry="2026-04-30", provider="upstox", dataset_hash="hash-1", bar_interval="1m", quote_timestamp="2026-04-01 09:14:40", feature_cutoff_ts="2026-04-01 09:15:00", signal_ts="2026-04-01 09:15:00", earliest_entry_ts="2026-04-01 09:16:00"),
        _base_row(timestamp="2026-04-01 09:16:00", underlying="NIFTY", option_type="CE", strike=25500, expiry="2026-04-30", provider="upstox", dataset_hash="hash-1", bar_interval="1m", quote_timestamp="2026-04-01 09:15:40", bid=100.2, ask=100.5, bid_qty=10, ask_qty=0, volume=5000, oi=9000, close=100.4, selected_for_execution=False, signal_score=0.2),
        _base_row(timestamp="2026-04-01 09:17:00", underlying="NIFTY", option_type="CE", strike=25500, expiry="2026-04-30", provider="upstox", dataset_hash="hash-1", bar_interval="1m", quote_timestamp="2026-04-01 09:16:40", bid=102.8, ask=103.1, bid_qty=10, ask_qty=10, open=101.8, high=103.5, low=101.6, close=103.0, selected_for_execution=False, signal_score=0.1),
    ]).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH, allow_derived_levels=False))
    assert result.summary["trades_taken"] == 0
    assert result.summary["rejected_reasons"]["missing_book_qty"] == 1
    assert result.trades == []


def test_gap_through_stop_uses_conservative_exit_bid(tmp_path: Path):
    data_path = tmp_path / "gap_stop.csv"
    pd.DataFrame([
        _base_row(feature_cutoff_ts="2026-04-01 09:15:00", signal_ts="2026-04-01 09:15:00", earliest_entry_ts="2026-04-01 09:16:00"),
        _base_row(timestamp="2026-04-01 09:16:00", bid=100.2, ask=100.5, close=100.4, selected_for_execution=False, signal_score=0.2),
        _base_row(timestamp="2026-04-01 09:17:00", high=100.8, low=95.0, close=95.5, bid=95.2, ask=95.6, selected_for_execution=False, signal_score=0.1),
    ]).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, allow_derived_levels=False))
    trade = result.trades[0]
    assert trade.exit_reason == "STOP_HIT"
    assert trade.exit_price == 95.2
    assert trade.exit_reference_price == 95.2


def test_gross_costs_and_net_pnl_are_reconciled(tmp_path: Path):
    data_path = tmp_path / "costs.csv"
    pd.DataFrame([
        _base_row(feature_cutoff_ts="2026-04-01 09:15:00", signal_ts="2026-04-01 09:15:00", earliest_entry_ts="2026-04-01 09:16:00"),
        _base_row(timestamp="2026-04-01 09:16:00", bid=100.2, ask=100.5, close=100.4, selected_for_execution=False, signal_score=0.2),
        _base_row(timestamp="2026-04-01 09:17:00", open=101.8, high=103.5, low=101.6, close=103.0, bid=102.8, ask=103.1, selected_for_execution=False, signal_score=0.1),
    ]).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, allow_derived_levels=False))
    trade = result.trades[0]
    assert trade.gross_pnl_value == pytest.approx(2.3)
    assert trade.total_costs == pytest.approx(1.2)
    assert trade.net_pnl_value == trade.gross_pnl_value - trade.total_costs
    assert result.summary["gross_pnl_value"] == trade.gross_pnl_value
    assert result.summary["total_costs"] == trade.total_costs
    assert result.summary["net_pnl_value"] == trade.net_pnl_value
    assert result.summary["after_cost_expectancy"] == trade.net_pnl_value


def test_increasing_costs_never_improves_net_pnl(tmp_path: Path):
    data_path = tmp_path / "higher_costs.csv"
    pd.DataFrame([
        _base_row(feature_cutoff_ts="2026-04-01 09:15:00", signal_ts="2026-04-01 09:15:00", earliest_entry_ts="2026-04-01 09:16:00"),
        _base_row(timestamp="2026-04-01 09:16:00", bid=100.2, ask=100.5, close=100.4, selected_for_execution=False, signal_score=0.2),
        _base_row(timestamp="2026-04-01 09:17:00", open=101.8, high=103.5, low=101.6, close=103.0, bid=102.8, ask=103.1, selected_for_execution=False, signal_score=0.1),
    ]).to_csv(data_path, index=False)
    base = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, allow_derived_levels=False))
    higher = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, allow_derived_levels=False, cost_config=OptionBacktestCostConfig(brokerage_per_order=40.0, exchange_fee_per_contract=1.0, tax_per_contract=1.0)))
    assert higher.summary["net_pnl_value"] <= base.summary["net_pnl_value"]


def test_partial_fill_uses_filled_quantity_only(tmp_path: Path):
    data_path = tmp_path / "partial_qty.csv"
    pd.DataFrame([
        _base_row(feature_cutoff_ts="2026-04-01 09:15:00", signal_ts="2026-04-01 09:15:00", earliest_entry_ts="2026-04-01 09:16:00", volume=10, oi=10),
        _base_row(timestamp="2026-04-01 09:16:00", bid=100.2, ask=100.5, bid_qty=5, ask_qty=5, close=100.4, volume=10, oi=10, selected_for_execution=False, signal_score=0.2),
        _base_row(timestamp="2026-04-01 09:17:00", open=101.8, high=103.5, low=101.6, close=103.0, bid=102.8, ask=103.1, bid_qty=5, ask_qty=5, volume=10, oi=10, selected_for_execution=False, signal_score=0.1),
    ]).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, allow_derived_levels=False, quantity=100))
    trade = result.trades[0]
    assert trade.entry_fill_qty < 100
    assert trade.exit_fill_qty < 100
    assert trade.quantity == min(trade.entry_fill_qty, trade.exit_fill_qty)
    assert trade.gross_pnl_value == trade.pnl_points * trade.quantity


def test_proxy_mode_marks_weaker_exit_assumption_explicitly(tmp_path: Path):
    data_path = tmp_path / "proxy_exit_mark.csv"
    pd.DataFrame([
        _base_row(feature_cutoff_ts="2026-04-01 09:15:00", signal_ts="2026-04-01 09:15:00", earliest_entry_ts="2026-04-01 09:16:00"),
        _base_row(timestamp="2026-04-01 09:16:00", bid=100.2, ask=100.5, close=100.4, selected_for_execution=False, signal_score=0.2),
        _base_row(timestamp="2026-04-01 09:17:00", bid="", ask="", open=101.8, high=103.5, low=101.6, close=103.0, selected_for_execution=False, signal_score=0.1),
    ]).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(OptionBacktestConfig(symbol="NIFTY24APR25500CE", data_path=data_path, research_mode=ResearchMode.PROXY_RESEARCH, allow_derived_levels=False))
    trade = result.trades[0]
    assert trade.exit_fill_source == "mark_fallback"
    assert result.summary["diagnostics"]["proxy_exit_mark_rows"] == 1


def test_certification_mode_retains_all_decisions_without_truncation(tmp_path: Path):
    data_path = tmp_path / "strict_decisions.csv"
    rows = []
    for idx in range(250):
        ts = pd.Timestamp("2026-04-01 09:15:00") + pd.Timedelta(minutes=idx)
        quote_ts = ts - pd.Timedelta(seconds=20)
        rows.append(
            _base_row(
                timestamp=ts.strftime("%Y-%m-%d %H:%M:%S"),
                underlying="NIFTY",
                option_type="CE",
                strike=25500,
                expiry="2026-04-30",
                provider="upstox",
                dataset_hash="hash-1",
                bar_interval="1m",
                quote_timestamp=quote_ts.strftime("%Y-%m-%d %H:%M:%S"),
                feature_cutoff_ts=ts.strftime("%Y-%m-%d %H:%M:%S"),
                signal_ts=ts.strftime("%Y-%m-%d %H:%M:%S"),
                earliest_entry_ts=(ts + pd.Timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"),
                selected_for_execution=False,
                signal_score=0.1,
                setup_id="breakout",
                regime="trend",
                is_oos=False,
            )
        )
    pd.DataFrame(rows).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(
        OptionBacktestConfig(
            symbol="NIFTY24APR25500CE",
            data_path=data_path,
            research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH,
            allow_derived_levels=False,
        )
    )
    assert result.summary["signals_total"] == 250
    assert result.summary["decision_rows"] == 250
    assert result.summary["reconciliation"]["decision_rows"] == 250
    assert result.sampled_decisions[0]["decision_index"] == 0
    assert result.sampled_decisions[-1]["decision_index"] == 249
    assert result.sampled_decisions[-1]["timestamp"] == "2026-04-01T13:24:00+05:30"


def test_rejected_candidates_preserve_reason_and_reconcile_counts(tmp_path: Path):
    data_path = tmp_path / "strict_rejections.csv"
    pd.DataFrame(
        [
            _base_row(
                underlying="NIFTY",
                option_type="CE",
                strike=25500,
                expiry="2026-04-30",
                provider="upstox",
                dataset_hash="hash-1",
                bar_interval="1m",
                quote_timestamp="2026-04-01 09:14:40",
                feature_cutoff_ts="2026-04-01 09:15:00",
                signal_ts="2026-04-01 09:15:00",
                earliest_entry_ts="2026-04-01 09:15:00",
                setup_id="breakout",
                regime="trend",
                is_oos=False,
            ),
            _base_row(
                timestamp="2026-04-01 09:16:00",
                underlying="NIFTY",
                option_type="CE",
                strike=25500,
                expiry="2026-04-30",
                provider="upstox",
                dataset_hash="hash-1",
                bar_interval="1m",
                quote_timestamp="2026-04-01 09:15:40",
                feature_cutoff_ts="2026-04-01 09:16:00",
                signal_ts="2026-04-01 09:16:00",
                earliest_entry_ts="2026-04-01 09:16:00",
                selected_for_execution=False,
                signal_score=0.2,
                setup_id="breakout",
                regime="trend",
                is_oos=False,
            ),
        ]
    ).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(
        OptionBacktestConfig(
            symbol="NIFTY24APR25500CE",
            data_path=data_path,
            research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH,
            allow_derived_levels=False,
        )
    )
    rejected = [row for row in result.sampled_decisions if row["execution_status"] != "executable"]
    assert rejected
    assert all(row["rejection_reason"] for row in rejected)
    assert result.summary["reconciliation"]["rejected_decisions"] == sum(result.summary["rejected_reasons"].values())


def test_summary_and_journal_reconcile_trade_and_pnl_fields(tmp_path: Path):
    data_path = tmp_path / "strict_reconcile_trade.csv"
    pd.DataFrame(
        [
            _base_row(
                underlying="NIFTY",
                option_type="CE",
                strike=25500,
                expiry="2026-04-30",
                provider="upstox",
                dataset_hash="hash-1",
                bar_interval="1m",
                quote_timestamp="2026-04-01 09:14:40",
                feature_cutoff_ts="2026-04-01 09:15:00",
                signal_ts="2026-04-01 09:15:00",
                earliest_entry_ts="2026-04-01 09:16:00",
                setup_id="breakout",
                regime="trend",
                is_oos=False,
            ),
            _base_row(
                timestamp="2026-04-01 09:16:00",
                underlying="NIFTY",
                option_type="CE",
                strike=25500,
                expiry="2026-04-30",
                provider="upstox",
                dataset_hash="hash-1",
                bar_interval="1m",
                quote_timestamp="2026-04-01 09:15:40",
                bid=100.2,
                ask=100.5,
                bid_qty=50,
                ask_qty=50,
                close=100.4,
                selected_for_execution=False,
                signal_score=0.2,
                setup_id="breakout",
                regime="trend",
                is_oos=False,
            ),
            _base_row(
                timestamp="2026-04-01 09:17:00",
                underlying="NIFTY",
                option_type="CE",
                strike=25500,
                expiry="2026-04-30",
                provider="upstox",
                dataset_hash="hash-1",
                bar_interval="1m",
                quote_timestamp="2026-04-01 09:16:40",
                open=101.8,
                high=103.5,
                low=101.6,
                close=103.0,
                bid=102.8,
                ask=103.1,
                bid_qty=50,
                ask_qty=50,
                selected_for_execution=False,
                signal_score=0.1,
                setup_id="breakout",
                regime="trend",
                is_oos=False,
            ),
        ]
    ).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(
        OptionBacktestConfig(
            symbol="NIFTY24APR25500CE",
            data_path=data_path,
            research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH,
            allow_derived_levels=False,
        )
    )
    trade = result.trades[0]
    assert result.summary["trade_rows"] == 1
    assert result.summary["reconciliation"]["trade_rows"] == 1
    assert result.summary["gross_pnl_value"] == trade.gross_pnl_value
    assert result.summary["total_costs"] == trade.total_costs
    assert result.summary["net_pnl_value"] == trade.net_pnl_value
    assert result.summary["reconciliation"]["trade_count_reconciles"] is True


def test_ambiguity_count_reconciles_with_trade_rows(tmp_path: Path):
    data_path = tmp_path / "strict_ambiguity_reconcile.csv"
    pd.DataFrame(
        [
            _base_row(
                feature_cutoff_ts="2026-04-01 09:15:00",
                signal_ts="2026-04-01 09:15:00",
                earliest_entry_ts="2026-04-01 09:16:00",
                underlying="NIFTY",
                option_type="CE",
                strike=25500,
                expiry="2026-04-30",
                provider="upstox",
                dataset_hash="hash-1",
                bar_interval="1m",
                quote_timestamp="2026-04-01 09:14:40",
                setup_id="breakout",
                regime="trend",
                is_oos=False,
            ),
            _base_row(
                timestamp="2026-04-01 09:16:00",
                open=100.5,
                high=103.5,
                low=97.5,
                close=100.4,
                bid=100.2,
                ask=100.5,
                selected_for_execution=False,
                signal_score=0.2,
                underlying="NIFTY",
                option_type="CE",
                strike=25500,
                expiry="2026-04-30",
                provider="upstox",
                dataset_hash="hash-1",
                bar_interval="1m",
                quote_timestamp="2026-04-01 09:15:40",
                setup_id="breakout",
                regime="trend",
                is_oos=False,
            ),
        ]
    ).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(
        OptionBacktestConfig(
            symbol="NIFTY24APR25500CE",
            data_path=data_path,
            research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH,
            allow_derived_levels=False,
        )
    )
    assert result.trades[0].ambiguity_count == 1
    assert result.summary["ambiguity_count"] == 1
    assert result.summary["reconciliation"]["ambiguity_count"] == 1
    assert result.summary["diagnostics"]["timing_ambiguity_count"] == 1


def test_unknown_setup_regime_oos_blocks_certification_candidate(tmp_path: Path):
    data_path = tmp_path / "strict_missing_metadata.csv"
    pd.DataFrame(
        [
            _base_row(
                underlying="NIFTY",
                option_type="CE",
                strike=25500,
                expiry="2026-04-30",
                provider="upstox",
                dataset_hash="hash-1",
                bar_interval="1m",
                quote_timestamp="2026-04-01 09:14:40",
                feature_cutoff_ts="2026-04-01 09:15:00",
                signal_ts="2026-04-01 09:15:00",
                earliest_entry_ts="2026-04-01 09:16:00",
            ),
            _base_row(
                timestamp="2026-04-01 09:16:00",
                underlying="NIFTY",
                option_type="CE",
                strike=25500,
                expiry="2026-04-30",
                provider="upstox",
                dataset_hash="hash-1",
                bar_interval="1m",
                quote_timestamp="2026-04-01 09:15:40",
                bid=100.2,
                ask=100.5,
                bid_qty=50,
                ask_qty=50,
                close=100.4,
                selected_for_execution=False,
                signal_score=0.2,
            ),
            _base_row(
                timestamp="2026-04-01 09:17:00",
                underlying="NIFTY",
                option_type="CE",
                strike=25500,
                expiry="2026-04-30",
                provider="upstox",
                dataset_hash="hash-1",
                bar_interval="1m",
                quote_timestamp="2026-04-01 09:16:40",
                open=101.8,
                high=103.5,
                low=101.6,
                close=103.0,
                bid=102.8,
                ask=103.1,
                bid_qty=50,
                ask_qty=50,
                selected_for_execution=False,
                signal_score=0.1,
            ),
        ]
    ).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(
        OptionBacktestConfig(
            symbol="NIFTY24APR25500CE",
            data_path=data_path,
            research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH,
            allow_derived_levels=False,
        )
    )
    assert result.summary["certifiable"] is False
    assert result.summary["result_label"] == "OPTION_REPLAY_RESEARCH"
    blockers = set(result.summary["certification_blockers"])
    assert "missing_setup_id_column" in blockers
    assert "missing_regime_column" in blockers
    assert "missing_oos_label_column" in blockers


def test_strict_result_label_can_be_certification_candidate(tmp_path: Path):
    data_path = tmp_path / "strict_cert_candidate.csv"
    pd.DataFrame(
        [
            _base_row(
                underlying="NIFTY",
                option_type="CE",
                strike=25500,
                expiry="2026-04-30",
                provider="upstox",
                dataset_hash="hash-1",
                bar_interval="1m",
                quote_timestamp="2026-04-01 09:14:40",
                feature_cutoff_ts="2026-04-01 09:15:00",
                signal_ts="2026-04-01 09:15:00",
                earliest_entry_ts="2026-04-01 09:16:00",
                setup_id="breakout",
                regime="trend",
                is_oos=False,
            ),
            _base_row(
                timestamp="2026-04-01 09:16:00",
                underlying="NIFTY",
                option_type="CE",
                strike=25500,
                expiry="2026-04-30",
                provider="upstox",
                dataset_hash="hash-1",
                bar_interval="1m",
                quote_timestamp="2026-04-01 09:15:40",
                bid=100.2,
                ask=100.5,
                bid_qty=50,
                ask_qty=50,
                close=100.4,
                selected_for_execution=False,
                signal_score=0.2,
                setup_id="breakout",
                regime="trend",
                is_oos=False,
            ),
            _base_row(
                timestamp="2026-04-01 09:17:00",
                underlying="NIFTY",
                option_type="CE",
                strike=25500,
                expiry="2026-04-30",
                provider="upstox",
                dataset_hash="hash-1",
                bar_interval="1m",
                quote_timestamp="2026-04-01 09:16:40",
                open=101.8,
                high=103.5,
                low=101.6,
                close=103.0,
                bid=102.8,
                ask=103.1,
                bid_qty=50,
                ask_qty=50,
                selected_for_execution=False,
                signal_score=0.1,
                setup_id="breakout",
                regime="trend",
                is_oos=False,
            ),
        ]
    ).to_csv(data_path, index=False)
    result = run_option_symbol_backtest(
        OptionBacktestConfig(
            symbol="NIFTY24APR25500CE",
            data_path=data_path,
            research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH,
            allow_derived_levels=False,
        )
    )
    assert result.summary["certifiable"] is True
    assert result.summary["result_label"] == "CERTIFICATION_CANDIDATE"
    assert result.summary["certification_blockers"] == []
    assert result.trades[0].setup_id == "breakout"
    assert result.trades[0].regime == "trend"
    assert result.trades[0].oos_label_known is True
