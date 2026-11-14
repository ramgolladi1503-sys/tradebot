from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import sqlite3

import pytest

from aixion_trade_intelligence.cas_a1_tick_points import (
    CasA1TickPointError,
    extract_frozen_futures_points,
)


IST = ZoneInfo("Asia/Kolkata")


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "ticks.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE ticks (timestamp TEXT, instrument_token INTEGER, last_price REAL, volume INTEGER, oi INTEGER, timestamp_epoch REAL, timestamp_iso TEXT)"
    )
    for clock, price in [("15:29:03", 25010.0), ("15:39:02", 25022.0)]:
        dt = datetime.fromisoformat(f"2026-08-18T{clock}+05:30")
        conn.execute(
            "INSERT INTO ticks(timestamp,instrument_token,last_price,volume,oi,timestamp_epoch,timestamp_iso) VALUES(?,?,?,?,?,?,?)",
            (dt.isoformat(), 12345, price, 0, 0, dt.timestamp(), dt.isoformat()),
        )
    conn.commit()
    conn.close()
    return path


def test_extracts_first_tick_inside_each_frozen_checkpoint_minute_read_only(tmp_path: Path):
    payload = extract_frozen_futures_points(
        db_path=_db(tmp_path),
        futures_token=12345,
        futures_instrument="NSE_FO|NIFTY_AUG_FUT",
        session_date="2026-08-18",
    )
    assert payload["evidence_kind"] == "CAS_A1_FUTURES_POINT_MARKS"
    assert [row["label"] for row in payload["point_marks"]] == ["15:29", "15:39"]
    assert payload["point_marks"][0]["price"] == 25010.0
    assert payload["point_marks"][1]["price"] == 25022.0
    assert payload["point_marks"][0]["lag_seconds_from_checkpoint"] == pytest.approx(3.0)
    assert payload["read_only_tick_db"] is True
    assert payload["broker_write_authority"] is False
    assert payload["order_authority"] is False


def test_missing_exact_checkpoint_minute_fails_closed(tmp_path: Path):
    db = _db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM ticks WHERE last_price = 25022.0")
    conn.commit()
    conn.close()
    with pytest.raises(CasA1TickPointError, match="15:39"):
        extract_frozen_futures_points(
            db_path=db,
            futures_token=12345,
            futures_instrument="NSE_FO|NIFTY_AUG_FUT",
            session_date="2026-08-18",
        )


def test_wrong_futures_token_fails_closed(tmp_path: Path):
    with pytest.raises(CasA1TickPointError, match="no exact futures tick"):
        extract_frozen_futures_points(
            db_path=_db(tmp_path),
            futures_token=99999,
            futures_instrument="NSE_FO|WRONG",
            session_date="2026-08-18",
        )
