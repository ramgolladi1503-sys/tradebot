import json
import sqlite3
from pathlib import Path

from config import config as cfg
from core import db_guard, risk_halt


def test_db_probe_creates_and_clears_halt(tmp_path, monkeypatch):
    db_path = tmp_path / "db" / "trading_bot.sqlite"
    halt_path = tmp_path / "risk_halt.json"
    halt_path.write_text(json.dumps({"halted": True, "reason": "db_write_fail"}))

    monkeypatch.setattr(cfg, "DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "RISK_HALT_FILE", str(halt_path), raising=False)

    result = db_guard.ensure_db_ready()
    assert result["ok"] is True
    assert Path(result["db_path"]).exists()
    con = sqlite3.connect(result["db_path"])
    try:
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='__db_probe'"
        ).fetchone()
        assert row is not None
    finally:
        con.close()
    state = risk_halt.load_halt()
    assert state.get("halted") is False
