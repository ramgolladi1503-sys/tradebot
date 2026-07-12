from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pandas as pd

from core.option_backtest.exporter import build_option_backtest_frame, resolve_instrument_token


def test_resolve_instrument_token_from_instrument_dump(tmp_path: Path):
    path = tmp_path / "kite_instruments.json"
    path.write_text(
        json.dumps(
            {
                "NFO": [
                    {
                        "tradingsymbol": "NIFTY2650524200CE",
                        "instrument_token": 18986754,
                        "name": "NIFTY",
                        "expiry": "2026-05-05",
                        "strike": 24200,
                        "instrument_type": "CE",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    resolved = resolve_instrument_token(
        tradingsymbol="NIFTY2650524200CE",
        option_chain_path=tmp_path / "missing.json",
        instruments_path=path,
    )

    assert resolved["instrument_token"] == 18986754
    assert resolved["tradingsymbol"] == "NIFTY2650524200CE"


def test_build_option_backtest_frame_merges_ticks_and_depth(tmp_path: Path):
    db_path = tmp_path / "ticks.sqlite"
    with sqlite3.connect(str(db_path)) as conn:
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
        conn.execute(
            """
            CREATE TABLE depth_snapshots (
                timestamp TEXT,
                instrument_token INTEGER,
                depth_json TEXT,
                timestamp_iso TEXT,
                timestamp_epoch REAL
            )
            """
        )
        tick_rows = [
            ("2026-04-30T09:15:01Z", 123, 100.0, 10, 1000, 1777530301.0, "2026-04-30T09:15:01Z"),
            ("2026-04-30T09:15:20Z", 123, 102.0, 12, 1002, 1777530320.0, "2026-04-30T09:15:20Z"),
            ("2026-04-30T09:15:50Z", 123, 101.0, 14, 1003, 1777530350.0, "2026-04-30T09:15:50Z"),
            ("2026-04-30T09:16:10Z", 123, 103.0, 20, 1005, 1777530370.0, "2026-04-30T09:16:10Z"),
        ]
        conn.executemany("INSERT INTO ticks VALUES (?,?,?,?,?,?,?)", tick_rows)
        depth_payload_1 = json.dumps({"depth": {"buy": [{"price": 99.9}], "sell": [{"price": 100.2}]}})
        depth_payload_2 = json.dumps({"depth": {"buy": [{"price": 102.8}], "sell": [{"price": 103.1}]}})
        depth_rows = [
            ("2026-04-30T09:15:40Z", 123, depth_payload_1, "2026-04-30T09:15:40Z", 1777530340.0),
            ("2026-04-30T09:16:15Z", 123, depth_payload_2, "2026-04-30T09:16:15Z", 1777530375.0),
        ]
        conn.executemany("INSERT INTO depth_snapshots VALUES (?,?,?,?,?)", depth_rows)
        conn.commit()

    frame = build_option_backtest_frame(
        db_path=db_path,
        instrument_token=123,
        tradingsymbol="NIFTY2650524200CE",
    )

    assert list(frame.columns) == ["timestamp", "timestamp_epoch", "symbol", "open", "high", "low", "close", "volume", "oi", "bid", "ask"]
    assert frame.shape[0] == 2
    first = frame.iloc[0].to_dict()
    second = frame.iloc[1].to_dict()
    assert first["symbol"] == "NIFTY2650524200CE"
    assert first["open"] == 100.0
    assert first["high"] == 102.0
    assert first["low"] == 100.0
    assert first["close"] == 101.0
    assert first["volume"] == 14
    assert first["oi"] == 1003
    assert first["timestamp_epoch"] == 1777530350.0
    assert first["bid"] == 99.9
    assert first["ask"] == 100.2
    assert second["close"] == 103.0
    assert second["timestamp_epoch"] == 1777530370.0
    assert second["bid"] == 102.8
    assert second["ask"] == 103.1
