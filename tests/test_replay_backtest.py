import pandas as pd

from core.replay_backtest import ReplayBacktestEngine


def test_replay_backtest_basic():
    data = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=10, freq="T"),
            "open": [100] * 10,
            "high": [101] * 10,
            "low": [99] * 10,
            "close": [100 + i for i in range(10)],
            "volume": [1000] * 10,
        }
    )

    def strat(m):
        return {"entry": m["close"], "target": m["close"] * 1.01, "stop": m["close"] * 0.99}

    engine = ReplayBacktestEngine(data, strat)
    res = engine.run()

    assert not res.empty
    assert "pl" in res.columns
