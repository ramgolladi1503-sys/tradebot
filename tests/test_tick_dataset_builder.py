from __future__ import annotations

import sqlite3

import pandas as pd

from models.tick_dataset import _safe_to_datetime, build_tick_dataset


def test_safe_to_datetime_parses_mixed_iso_formats():
    values = pd.Series(
        [
            "2026-02-27T12:00:00Z",
            "2026-02-27T12:00:00.123456Z",
            "2026-02-27 12:00:01+00:00",
        ]
    )

    out = _safe_to_datetime(values)

    assert out.notna().sum() == 3


def test_build_tick_dataset_uses_timestamp_epoch_when_available(tmp_path):
    db_path = tmp_path / "ticks.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE ticks (
            timestamp TEXT,
            instrument_token INTEGER,
            last_price REAL,
            volume INTEGER,
            oi INTEGER,
            timestamp_epoch REAL,
            timestamp_iso TEXT
        )
        """
    )
    rows = [
        ("2026-02-27T12:00:00Z", 111, 100.0, 10, 1000, 1772193600.0, "2026-02-27T12:00:00Z"),
        ("2026-02-27T12:00:01.100000Z", 111, 101.0, 12, 1002, 1772193601.1, "2026-02-27T12:00:01.100000Z"),
        ("2026-02-27T12:00:00Z", 222, 50.0, 5, 900, 1772193600.0, "2026-02-27T12:00:00Z"),
        ("2026-02-27T12:00:01Z", 222, 49.5, 6, 901, 1772193601.0, "2026-02-27T12:00:01Z"),
    ]
    conn.executemany("INSERT INTO ticks VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()

    df = build_tick_dataset(db_path=db_path, horizon=1, threshold=0.001)

    assert len(df) == 4
    assert df["ts"].notna().sum() == 4
    assert int((df["target"] == 1).sum()) >= 1
    assert int(df["future_price"].notna().sum()) == 2


def test_build_tick_dataset_legacy_schema_without_timestamp_epoch(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE ticks (
            timestamp TEXT,
            instrument_token INTEGER,
            last_price REAL,
            volume INTEGER,
            oi INTEGER
        )
        """
    )
    rows = [
        ("2026-02-27T12:00:00Z", 111, 100.0, 10, 1000),
        ("2026-02-27T12:00:01Z", 111, 101.0, 12, 1002),
    ]
    conn.executemany("INSERT INTO ticks VALUES (?,?,?,?,?)", rows)
    conn.commit()
    conn.close()

    df = build_tick_dataset(db_path=db_path, horizon=1, threshold=0.001)

    assert len(df) == 2
    assert "target" in df.columns
    assert int(df["target"].iloc[0]) == 1
