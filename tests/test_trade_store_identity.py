import sqlite3
from pathlib import Path

from core import trade_store
from config import config as cfg


def test_trade_store_writes_identity_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path))
    entry = {
        "trade_id": "T-1",
        "timestamp": "2026-02-07T10:00:00Z",
        "symbol": "NIFTY",
        "underlying": "NIFTY",
        "instrument": "OPT",
        "instrument_type": "OPT",
        "instrument_token": 123,
        "strike": 22000,
        "expiry": "2026-02-14",
        "option_type": "CE",
        "right": "CE",
        "instrument_id": "NIFTY|2026-02-14|22000|CE",
        "side": "BUY",
        "entry": 100.0,
        "stop_loss": 90.0,
        "target": 140.0,
        "qty": 1,
        "qty_lots": 1,
        "qty_units": 50,
        "validity_sec": 120,
        "tradable": True,
        "tradable_reasons_blocking": "[]",
        "source_flags_json": "{\"chain_source\":\"live\"}",
        "confidence": 0.8,
        "strategy": "SCALP",
        "regime": "TREND",
        "execution_quality_score": 80.0,
    }
    trade_store.insert_trade(entry)
    assert db_path.exists()
    con = sqlite3.connect(db_path)
    row = con.execute(
        "SELECT strike, expiry, option_type, right, instrument_id, tradable, tradable_reasons_blocking, source_flags_json FROM trades WHERE trade_id='T-1'"
    ).fetchone()
    con.close()
    assert row == (
        22000,
        "2026-02-14",
        "CE",
        "CE",
        "NIFTY|2026-02-14|22000|CE",
        1,
        "[]",
        "{\"chain_source\":\"live\"}",
    )
