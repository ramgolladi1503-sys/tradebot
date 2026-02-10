import sqlite3
from pathlib import Path

from config import config as cfg
from core import trade_store


def test_trailing_stop_updates_persist(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path))
    Path(tmp_path / "logs").mkdir(exist_ok=True)

    trade_store.insert_trade(
        {
            "trade_id": "T-TRAIL-1",
            "timestamp": "2026-02-10T10:00:00Z",
            "symbol": "NIFTY",
            "underlying": "NIFTY",
            "instrument": "OPT",
            "instrument_type": "OPT",
            "instrument_token": 99,
            "strike": 22000,
            "expiry": "2026-02-14",
            "option_type": "CE",
            "right": "CE",
            "instrument_id": "NIFTY|2026-02-14|22000|CE",
            "side": "BUY",
            "entry": 100.0,
            "stop_loss": 90.0,
            "target": 130.0,
            "qty": 1,
            "qty_lots": 1,
            "qty_units": 50,
            "validity_sec": 180,
            "confidence": 0.8,
            "strategy": "SCALP",
            "regime": "TREND",
        }
    )

    trade_store.update_trailing_state(
        "T-TRAIL-1",
        trailing_enabled=True,
        trailing_method="ATR",
        trailing_atr_mult=0.8,
        trail_stop_init=90.0,
        trail_stop_last=90.0,
        trail_updates=0,
    )
    trade_store.insert_trail_event("T-TRAIL-1", 90.0, 100.0, "TRAIL_INIT")

    trade_store.update_trailing_state(
        "T-TRAIL-1",
        trailing_enabled=True,
        trailing_method="ATR",
        trailing_atr_mult=0.8,
        trail_stop_init=90.0,
        trail_stop_last=95.0,
        trail_updates=1,
    )
    trade_store.insert_trail_event("T-TRAIL-1", 95.0, 106.0, "TRAIL_UPDATE")

    con = sqlite3.connect(str(db_path))
    row = con.execute(
        "SELECT trailing_enabled, trail_stop_init, trail_stop_last, trail_updates FROM trades WHERE trade_id='T-TRAIL-1'"
    ).fetchone()
    ev_count = con.execute(
        "SELECT COUNT(1) FROM trail_events WHERE trace_id='T-TRAIL-1'"
    ).fetchone()[0]
    con.close()

    assert row is not None
    assert row[0] == 1
    assert float(row[1]) == 90.0
    assert float(row[2]) == 95.0
    assert int(row[3]) == 1
    assert int(ev_count) == 2
