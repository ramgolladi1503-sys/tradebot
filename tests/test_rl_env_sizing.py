import sqlite3
from pathlib import Path

import pytest

from rl.env_sizing import SizingEnv


def test_rl_env_sizing_step(tmp_path):
    db_path = tmp_path / "trades.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE decision_events (
            trade_id TEXT PRIMARY KEY,
            ts TEXT,
            symbol TEXT,
            score_0_100 REAL,
            regime_probs TEXT,
            shock_score REAL,
            spread_pct REAL,
            depth_imbalance REAL,
            drawdown_pct REAL,
            loss_streak REAL,
            open_risk REAL,
            delta_exposure REAL,
            gamma_exposure REAL,
            vega_exposure REAL,
            bid REAL,
            ask REAL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO decision_events (trade_id, ts, symbol, score_0_100, regime_probs, shock_score, spread_pct,
        depth_imbalance, drawdown_pct, loss_streak, open_risk, delta_exposure, gamma_exposure, vega_exposure, bid, ask)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "T1",
            "2026-02-05T10:00:00",
            "NIFTY",
            80,
            '{"RANGE": 0.7}',
            0.1,
            0.02,
            0.1,
            -0.01,
            0,
            0,
            0,
            0,
            0,
            100,
            102,
        ),
    )
    conn.commit()
    conn.close()

    env = SizingEnv(source=str(db_path))
    obs = env.reset()
    assert len(obs) > 0
    step = env.step(0.5)
    assert step.done is True
    assert "filled" in step.info
