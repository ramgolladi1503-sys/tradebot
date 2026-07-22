import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from core.research_backtest_integrity import (
    causal_completed_htf_sma,
    is_immediate_next_bar,
)


SCRIPT_PATH = (
    Path(__file__).parents[1] / "scripts" / "generate_mean_reversion_trade_ledger.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("mean_reversion_ledger", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_causal_htf_sma_ignores_future_close_in_current_bucket():
    idx = pd.date_range(
        "2026-01-05 09:15", periods=270, freq="1min", tz="Asia/Kolkata"
    )
    base = pd.Series(100.0, index=idx)
    mutated = base.copy()
    observation = pd.Timestamp("2026-01-05 13:20", tz="Asia/Kolkata")
    mutated.loc[pd.Timestamp("2026-01-05 13:29", tz="Asia/Kolkata")] = 1000.0

    actual_base = causal_completed_htf_sma(base, period_minutes=15, window=15)
    actual_mutated = causal_completed_htf_sma(
        mutated, period_minutes=15, window=15
    )

    assert np.isfinite(actual_base.loc[observation])
    assert actual_base.loc[observation] == actual_mutated.loc[observation]
    assert base.loc[pd.Timestamp("2026-01-05 13:29", tz="Asia/Kolkata")] != (
        mutated.loc[pd.Timestamp("2026-01-05 13:29", tz="Asia/Kolkata")]
    )


def test_immediate_next_bar_contract():
    assert is_immediate_next_bar(signal_bar_index=10, current_bar_index=11)
    assert not is_immediate_next_bar(signal_bar_index=10, current_bar_index=12)
    assert not is_immediate_next_bar(signal_bar_index=10, current_bar_index=10)


def test_opening_range_boundary_is_exclusive_for_start_labelled_candles():
    module = _load_script_module()
    assert module._is_opening_range_bar(pd.Timestamp("2026-01-05 09:15"), 45)
    assert module._is_opening_range_bar(pd.Timestamp("2026-01-05 09:59"), 45)
    assert not module._is_opening_range_bar(pd.Timestamp("2026-01-05 10:00"), 45)


def test_inferred_interval_uses_positive_median_and_rejects_single_row():
    module = _load_script_module()
    timestamps = pd.Series(
        pd.to_datetime(
            [
                "2026-01-05 09:15:00",
                "2026-01-05 09:16:00",
                "2026-01-05 09:17:00",
            ]
        )
    )
    assert module._infer_bar_interval(timestamps) == pd.Timedelta(minutes=1)

    try:
        module._infer_bar_interval(pd.Series(pd.to_datetime(["2026-01-05 09:15"])))
    except ValueError as exc:
        assert str(exc) == "cannot infer candle interval from fewer than two timestamps"
    else:
        raise AssertionError("single-row input must not invent a candle interval")


def test_entry_bar_ambiguity_is_conservatively_stopped_at_bar_end():
    module = _load_script_module()
    active_trade = {
        "entry_ts": pd.Timestamp("2026-01-05 10:00"),
        "direction": "LONG",
        "stop_loss": 95.0,
        "target": 105.0,
    }
    row = pd.Series({"high": 106.0, "low": 94.0, "close": 100.0})

    outcome = module._resolve_bar_exit(
        active_trade=active_trade,
        row=row,
        bar_start=pd.Timestamp("2026-01-05 10:00"),
        bar_interval=pd.Timedelta(minutes=1),
        time_stop_minutes=30,
    )

    assert outcome == (
        95.0,
        "SAME_CANDLE_AMBIGUOUS_ASSUMED_STOP",
        pd.Timestamp("2026-01-05 10:01"),
    )


def test_time_stop_uses_bar_close_time_not_start_time():
    module = _load_script_module()
    active_trade = {
        "entry_ts": pd.Timestamp("2026-01-05 09:15"),
        "direction": "LONG",
        "stop_loss": 90.0,
        "target": 110.0,
    }
    row = pd.Series({"high": 102.0, "low": 98.0, "close": 101.0})

    outcome = module._resolve_bar_exit(
        active_trade=active_trade,
        row=row,
        bar_start=pd.Timestamp("2026-01-05 09:44"),
        bar_interval=pd.Timedelta(minutes=1),
        time_stop_minutes=30,
    )

    assert outcome == (101.0, "TIME_STOP", pd.Timestamp("2026-01-05 09:45"))


def test_ledger_uses_causal_state_dimensional_cost_and_bar_end_timestamp(
    tmp_path, monkeypatch
):
    module = _load_script_module()
    base_dir = (
        tmp_path
        / "runtime"
        / "strategy_validation"
        / "MEAN_REVERSION_EXTENSION"
    )
    replay_underlying = (
        tmp_path
        / "runtime"
        / "upstox_candidate_replay"
        / "20260105"
        / "underlying"
    )
    config_dir = tmp_path / "configs" / "strategy_risk_contracts"
    base_dir.mkdir(parents=True)
    replay_underlying.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    parquet_path = replay_underlying / "NIFTY_20260105.parquet"
    parquet_path.write_text("fixture")

    (base_dir / "upstox_candle_file_audit.json").write_text(
        json.dumps({"classification": "UPSTOX_CANDLE_FILES_VALID"})
    )
    (config_dir / "MEAN_REVERSION_EXTENSION.json").write_text(
        json.dumps(
            {
                "v2_signal_version": "1.0",
                "entry": {
                    "opening_range_minutes": 45,
                    "min_wick_rejection_ratio": 0.5,
                    "max_trades_per_symbol_day": 4,
                },
                "htf_filter": {"period_minutes": 15},
                "stop_loss": {"atr_multiple": 1.0},
                "target": {"minimum_rr": 1.5},
                "time_stop": {"max_holding_minutes": 30},
                "cost_model": {
                    "proxy_option_delta": 0.5,
                    "proxy_option_execution_cost": 1.5,
                    "underlying_cost_proxy": 8.5,
                },
            }
        )
    )

    idx = pd.date_range("2026-01-05 09:15", periods=270, freq="1min")
    frame = pd.DataFrame(
        {
            "timestamp": idx,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
        }
    )
    signal_index = 245
    entry_index = signal_index + 1
    exit_index = entry_index + 1
    frame.loc[signal_index, ["open", "high", "low", "close"]] = [
        100.0,
        105.0,
        99.5,
        100.0,
    ]
    frame.loc[entry_index, ["open", "high", "low", "close"]] = [
        100.0,
        105.0,
        99.5,
        100.0,
    ]
    frame.loc[exit_index, ["open", "high", "low", "close"]] = [
        100.0,
        101.0,
        80.0,
        90.0,
    ]

    monkeypatch.setattr(module.pd, "read_parquet", lambda _: frame.copy())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_mean_reversion_trade_ledger.py",
            "--start-date",
            "20260105",
            "--end-date",
            "20260105",
        ],
    )

    module.main()

    ledger = [
        json.loads(line)
        for line in (base_dir / "phase_4_trade_ledger.jsonl")
        .read_text()
        .splitlines()
        if line.strip()
    ]
    candidates = [
        json.loads(line)
        for line in (base_dir / "phase_4_candidates.jsonl")
        .read_text()
        .splitlines()
        if line.strip()
    ]

    assert [trade["entry_delay_bars"] for trade in ledger] == [1]
    trade = ledger[0]
    expected_exit = pd.Timestamp(frame.loc[exit_index, "timestamp"]) + pd.Timedelta(
        minutes=1
    )
    assert pd.Timestamp(trade["exit_time"]) == expected_exit
    assert pd.Timestamp(trade["exit_time"]) > pd.Timestamp(trade["entry_time"])
    assert trade["pnl_model"] == "UNDERLYING_INDEX_PROXY_FIXED_HURDLE"
    assert trade["costs"] == 8.5
    assert trade["net_pnl"] == trade["underlying_net_pnl_after_index_cost"]
    assert trade["gross_pnl"] == trade["underlying_gross_pnl"]
    assert trade["proxy_option_net_pnl"] == (
        trade["proxy_option_gross_pnl"] - trade["proxy_option_execution_cost"]
    )

    passed = [
        candidate for candidate in candidates if candidate.get("status") == "PASSED"
    ]
    assert [candidate["signal_bar_index"] for candidate in passed] == [signal_index]
    assert not any(
        candidate.get("signal_bar_index") == entry_index for candidate in candidates
    )
