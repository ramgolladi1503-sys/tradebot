from __future__ import annotations

import random
import sqlite3

from config import config as cfg
from core.replay_engine import ReplayEngine


def _prepare_empty_replay_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS ticks (timestamp_epoch REAL, instrument_token INTEGER, last_price REAL, volume INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS depth_snapshots (timestamp_epoch REAL, instrument_token INTEGER, depth_json TEXT)"
    )
    conn.commit()
    conn.close()


def test_replay_engine_does_not_mutate_global_cfg_or_rng(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "replay.sqlite"
    _prepare_empty_replay_db(str(db_path))

    original_exec_mode = getattr(cfg, "EXECUTION_MODE", None)
    original_require_cross = getattr(cfg, "REQUIRE_CROSS_ASSET", None)

    # Expected next draw if global RNG state remains untouched by replay_day.
    random.seed(123456)
    _ = random.random()
    expected_next = random.random()

    random.seed(123456)
    _ = random.random()
    engine = ReplayEngine(db_path=db_path, seed=99)
    out_path = engine.replay_day("2026-02-10", ["NIFTY"], speed=0.0)
    actual_next = random.random()

    assert out_path.exists()
    assert actual_next == expected_next
    assert getattr(cfg, "EXECUTION_MODE", None) == original_exec_mode
    assert getattr(cfg, "REQUIRE_CROSS_ASSET", None) == original_require_cross
