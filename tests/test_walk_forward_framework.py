from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from core.walk_forward import run_walk_forward


def _make_history(days=20):
    rows = []
    start = datetime(2026, 1, 1, 9, 15)
    for day_idx in range(days):
        ts = start + timedelta(days=day_idx)
        base = 100 + day_idx
        rows.append(
            {
                "datetime": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "open": base,
                "high": base + 2,
                "low": base - 2,
                "close": base + 1,
                "volume": 1000 + day_idx * 10,
            }
        )
    return pd.DataFrame(rows)


@dataclass
class _DummyEngine:
    test_df: pd.DataFrame
    capital: float
    train_stats: dict

    def run(self):
        # deterministic 2 trades per window
        c0 = float(self.capital)
        rows = [
            {"pl": 100.0, "rr": 1.2, "capital": c0 + 100.0},
            {"pl": -40.0, "rr": 0.6, "capital": c0 + 60.0},
        ]
        return pd.DataFrame(rows)


def _factory(test_df, capital, train_stats):
    return _DummyEngine(test_df=test_df, capital=capital, train_stats=train_stats)


def test_walk_forward_expected_window_count_and_metrics(tmp_path):
    history = _make_history(days=20)
    result = run_walk_forward(
        historical_data=history,
        train_window_days=5,
        test_window_days=3,
        step_days=3,
        output_dir=str(tmp_path / "wf"),
        backtest_factory=_factory,
        write_outputs=True,
    )

    window_df = result["window_df"]
    assert len(window_df) == 5
    assert {"return", "max_drawdown", "win_rate", "avg_r", "trade_count", "sharpe_proxy"}.issubset(window_df.columns)
    assert (window_df["trade_count"] > 0).all()

    artifacts = result.get("artifacts", {})
    assert artifacts.get("json")
    assert artifacts.get("csv")


def test_walk_forward_non_empty_metrics(tmp_path):
    history = _make_history(days=15)
    result = run_walk_forward(
        historical_data=history,
        train_window_days=5,
        test_window_days=5,
        step_days=5,
        output_dir=str(tmp_path / "wf2"),
        backtest_factory=_factory,
        write_outputs=False,
    )
    assert result["config"]["window_count"] == 2
    aggregate = result["aggregate"]
    assert aggregate["total_trades"] > 0
    assert aggregate["avg_win_rate"] >= 0
