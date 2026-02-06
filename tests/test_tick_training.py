import sqlite3
from pathlib import Path

import json

from models.train_from_ticks import build_tick_dataset
from core.strategy_tracker import StrategyTracker


def _seed_ticks(conn):
    conn.execute("""
        CREATE TABLE ticks (
            timestamp TEXT,
            instrument_token INTEGER,
            last_price REAL,
            volume INTEGER,
            oi INTEGER
        )
    """)
    rows = [
        ("2024-01-01 09:15:00", 111, 100.0, 10, 1000),
        ("2024-01-01 09:15:01", 111, 100.5, 12, 1002),
        ("2024-01-01 09:15:02", 111, 101.0, 14, 1004),
        ("2024-01-01 09:15:03", 111, 100.8, 13, 1003),
        ("2024-01-01 09:15:04", 111, 101.2, 16, 1006),
        ("2024-01-01 09:15:05", 111, 101.4, 15, 1007),
    ]
    conn.executemany("INSERT INTO ticks VALUES (?,?,?,?,?)", rows)


def _seed_depth(conn):
    conn.execute("""
        CREATE TABLE depth_snapshots (
            timestamp TEXT,
            instrument_token INTEGER,
            depth_json TEXT
        )
    """)
    depth = {
        "depth": {
            "buy": [{"price": 100.9, "quantity": 10}],
            "sell": [{"price": 101.1, "quantity": 12}],
        },
        "imbalance": 0.25,
    }
    rows = [
        ("2024-01-01 09:15:02", 111, json.dumps(depth)),
        ("2024-01-01 09:15:04", 111, json.dumps(depth)),
    ]
    conn.executemany("INSERT INTO depth_snapshots VALUES (?,?,?)", rows)


def test_build_tick_dataset_with_depth(tmp_path):
    db_path = tmp_path / "trades.db"
    conn = sqlite3.connect(db_path)
    _seed_ticks(conn)
    _seed_depth(conn)
    conn.commit()
    conn.close()

    out = tmp_path / "tick_features.csv"
    df = build_tick_dataset(db_path, horizon=2, threshold=0.001, out_path=out, from_depth=True, depth_tolerance_sec=2)
    assert out.exists()
    assert "depth_imbalance" in df.columns
    assert df["depth_imbalance"].notna().any()
    assert "depth_spread_pct" in df.columns


def test_strategy_tracker_rolling_stats():
    tracker = StrategyTracker()
    for pnl in [1, -1, 1, 1, -1, -1, 1]:
        tracker.record("STRAT_A", pnl)
    roll = tracker.rolling_stats("STRAT_A", window=3)
    assert roll["trades"] == 3
    # last 3 outcomes: -1, -1, 1 -> wins=1 losses=2
    assert roll["wins"] == 1
    assert roll["losses"] == 2
