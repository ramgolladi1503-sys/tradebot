from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = ROOT / "research" / "nifty_45dte_vrp_v1"


def _load_module(name: str, filename: str):
    path = MODULE_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


build_vrp_state = _load_module("nifty_45dte_build_vrp_state", "build_vrp_state.py")
evaluate_buyonly_gate = _load_module("nifty_45dte_evaluate_buyonly_gate", "evaluate_buyonly_gate.py")


def test_rv20_excludes_current_session_close():
    dates = pd.date_range("2026-01-01", periods=24, freq="D", tz="Asia/Kolkata")
    closes = [100.0 * (1.001 ** i) * (1.0 + (0.002 if i % 2 else -0.001)) for i in range(24)]
    frame = pd.DataFrame({"timestamp": dates + pd.Timedelta(hours=15, minutes=30), "close": closes})
    daily = build_vrp_state.normalize_underlying(frame, assume_ist=False)
    row = daily.iloc[21]
    raw_returns = np.log(np.asarray(closes[1:21]) / np.asarray(closes[:20]))
    expected = float(np.std(raw_returns, ddof=1) * np.sqrt(252.0))
    assert np.isclose(float(row["rv20_prior"]), expected)
    current_session_return = np.log(closes[21] / closes[20])
    with_current = float(np.std(np.r_[raw_returns[1:], current_session_return], ddof=1) * np.sqrt(252.0))
    assert not np.isclose(float(row["rv20_prior"]), with_current)


def test_morning_trade_uses_previous_state_not_same_day_1500_state():
    baseline = pd.DataFrame({
        "entry_timestamp": [pd.Timestamp("2026-08-24 09:20", tz="Asia/Kolkata"), pd.Timestamp("2026-08-24 15:10", tz="Asia/Kolkata")],
        "net_pnl": [1.0, -1.0],
    })
    states = pd.DataFrame({
        "state_timestamp": [pd.Timestamp("2026-08-21 15:00", tz="Asia/Kolkata"), pd.Timestamp("2026-08-24 15:00", tz="Asia/Kolkata")],
        "vrp_zscore": [-1.0, 1.0],
        "primary_gate_admit": [True, False],
    })
    joined, metrics = evaluate_buyonly_gate.evaluate(baseline, states, entry_timestamp_column="entry_timestamp", pnl_column="net_pnl", assume_ist_baseline=False, assume_ist_states=False)
    morning = joined.loc[joined["entry_timestamp"].dt.hour == 9].iloc[0]
    afternoon = joined.loc[joined["entry_timestamp"].dt.hour == 15].iloc[0]
    assert morning["state_timestamp"] == pd.Timestamp("2026-08-21 15:00", tz="Asia/Kolkata")
    assert bool(morning["vrp_gate_admit"]) is True
    assert afternoon["state_timestamp"] == pd.Timestamp("2026-08-24 15:00", tz="Asia/Kolkata")
    assert bool(afternoon["vrp_gate_admit"]) is False
    assert metrics["state_available_baseline"]["trades"] == 2
    assert metrics["primary_gated"]["trades"] == 1


def test_unavailable_state_is_not_silently_counted_as_rejected_trade():
    baseline = pd.DataFrame({
        "entry_timestamp": [pd.Timestamp("2026-08-20 09:20", tz="Asia/Kolkata"), pd.Timestamp("2026-08-24 09:20", tz="Asia/Kolkata")],
        "net_pnl": [-5.0, 2.0],
    })
    states = pd.DataFrame({
        "state_timestamp": [pd.Timestamp("2026-08-21 15:00", tz="Asia/Kolkata")],
        "vrp_zscore": [-0.5],
        "primary_gate_admit": [True],
    })
    _, metrics = evaluate_buyonly_gate.evaluate(baseline, states, entry_timestamp_column="entry_timestamp", pnl_column="net_pnl", assume_ist_baseline=False, assume_ist_states=False)
    assert metrics["total_input_trades"] == 2
    assert metrics["trades_without_usable_prior_state"] == 1
    assert metrics["state_available_baseline"]["trades"] == 1
    assert metrics["primary_gated"]["trades"] == 1
    assert metrics["state_available_baseline"]["mean"] == 2.0


def test_buyonly_drawdown_counts_first_loss_from_zero():
    assert evaluate_buyonly_gate._max_drawdown(pd.Series([-7.0, 2.0])) == -7.0
