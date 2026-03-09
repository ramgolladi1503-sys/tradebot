from __future__ import annotations

import hashlib
import random
import sqlite3

from config import config as cfg
from core.replay_engine import ReplayEngine, _date_bounds


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


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


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


def test_replay_engine_decision_trace_hash_is_stable_for_same_seed(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.chdir(tmp_path)

    # Replay symbol mapping.
    instruments_path = runtime_root / "kite_instruments.csv"
    instruments_path.write_text(
        "instrument_token,name,tradingsymbol\n"
        "101,NIFTY,NIFTY-I\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "replay.sqlite"
    _prepare_empty_replay_db(str(db_path))
    conn = sqlite3.connect(db_path)
    day_start, _ = _date_bounds("2026-02-10")
    conn.execute(
        "INSERT INTO ticks(timestamp_epoch, instrument_token, last_price, volume) VALUES(?, ?, ?, ?)",
        (day_start + 60.0, 101, 25000.0, 10),
    )
    conn.execute(
        "INSERT INTO ticks(timestamp_epoch, instrument_token, last_price, volume) VALUES(?, ?, ?, ?)",
        (day_start + 120.0, 101, 25001.0, 11),
    )
    conn.commit()
    conn.close()

    engine_a = ReplayEngine(db_path=db_path, seed=17)
    first_path = engine_a.replay_day("2026-02-10", ["NIFTY"], speed=0.0)
    first_hash = _sha256_file(first_path)

    engine_b = ReplayEngine(db_path=db_path, seed=17)
    second_path = engine_b.replay_day("2026-02-10", ["NIFTY"], speed=0.0)
    second_hash = _sha256_file(second_path)

    assert first_hash == second_hash

    engine_c = ReplayEngine(db_path=db_path, seed=18)
    third_path = engine_c.replay_day("2026-02-10", ["NIFTY"], speed=0.0)
    third_hash = _sha256_file(third_path)

    assert third_hash != second_hash
