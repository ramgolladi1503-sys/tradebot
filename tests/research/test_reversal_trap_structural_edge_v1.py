from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT = Path(__file__).parents[2] / "scripts" / "run_reversal_trap_structural_edge_v1.py"
spec = importlib.util.spec_from_file_location("study", SCRIPT)
study = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = study
spec.loader.exec_module(study)


def make_frame(days: int = 40, bars: int = 120) -> pd.DataFrame:
    rows = []
    rng = np.random.default_rng(7)
    price = 20000.0
    for day in pd.date_range("2025-01-01", periods=days, freq="B"):
        for i in range(bars):
            ts = day + pd.Timedelta(hours=9, minutes=15 + i)
            move = rng.normal(0, 2)
            open_ = price
            close = max(1.0, open_ + move)
            high = max(open_, close) + abs(rng.normal(0.7, 0.2))
            low = min(open_, close) - abs(rng.normal(0.7, 0.2))
            rows.append((ts, open_, high, low, close, "NIFTY"))
            price = close
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "symbol"])
    frame["session"] = frame["timestamp"].dt.date.astype(str)
    return frame


def test_entry_is_strictly_after_signal() -> None:
    frame = make_frame(days=5)
    idx = 100
    frame.loc[idx, ["open", "high", "low", "close"]] = [19800, 19805, 19780, 19785]
    frame.loc[idx + 1, ["open", "high", "low", "close"]] = [19790, 20020, 19785, 20010]
    trades = study.generate_trades(frame, "synthetic", study.Params(multiplier=1.0), "TRAP")
    for trade in trades:
        assert trade.entry_index == trade.signal_index + 1
        assert pd.Timestamp(trade.entry_time) > pd.Timestamp(trade.signal_time)


def test_ambiguous_bar_is_stop_first() -> None:
    df = pd.DataFrame({"high": [120.0], "low": [80.0], "close": [100.0]})
    i, price, reason = study._resolve_exit(df, 0, "LONG", 100.0, 90.0, 110.0, 1)
    assert i == 0
    assert price == 90.0
    assert reason == "SAME_BAR_AMBIGUOUS_STOP_FIRST"


def test_split_is_chronological() -> None:
    sessions = [f"2025-01-{i:02d}" for i in range(1, 11)]
    trades = pd.DataFrame({"session": sessions, "side": ["LONG"] * 10, "net_bps": range(10), "rsi_bucket": [5] * 10})
    out = study.assign_splits(trades, sessions)
    assert out.iloc[0]["split"] == "train"
    assert out.iloc[-1]["split"] == "test"
    assert out[out["split"] == "train"]["session"].max() < out[out["split"] == "test"]["session"].min()


def test_empty_data_is_blocked(tmp_path: Path) -> None:
    result = study.run_study([], [], tmp_path)
    assert result["verdict"] == "DATA_BLOCKED"
    assert (tmp_path / "summary.json").exists()
