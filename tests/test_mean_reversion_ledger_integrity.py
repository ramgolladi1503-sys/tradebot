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


def test_immediate_next_bar_contract():
    assert is_immediate_next_bar(signal_bar_index=10, current_bar_index=11)
    assert not is_immediate_next_bar(signal_bar_index=10, current_bar_index=12)
    assert not is_immediate_next_bar(signal_bar_index=10, current_bar_index=10)


def test_ledger_uses_causal_state_and_dimensional_cost_contract(
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
    # This entry bar would also create a second signal under the old fall-through.
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

    assert len(ledger) == 1
    trade = ledger[0]
    assert trade["entry_delay_bars"] == 1
    assert trade["pnl_model"] == "UNDERLYING_INDEX_PROXY_FIXED_HURDLE"
    assert trade["costs"] == 8.5
    assert trade["net_pnl"] == trade["underlying_net_pnl_after_index_cost"]
    assert trade["gross_pnl"] == trade["underlying_gross_pnl"]
    assert trade["proxy_option_net_pnl"] == (
        trade["proxy_option_gross_pnl"] - trade["proxy_option_execution_cost"]
    )

    passed = [candidate for candidate in candidates if candidate.get("status") == "PASSED"]
    assert len(passed) == 1
    assert passed[0]["signal_bar_index"] == signal_index
    assert not any(
        candidate.get("signal_bar_index") == entry_index for candidate in candidates
    )
