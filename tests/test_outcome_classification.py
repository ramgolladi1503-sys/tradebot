import json
import sqlite3
from pathlib import Path

from config import config as cfg
from core import trade_store
from core.trade_logger import update_trade_outcome


def test_trailing_exit_above_entry_is_win(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "trades.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path))
    Path("data").mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(parents=True, exist_ok=True)

    trade_store.insert_trade(
        {
            "trade_id": "T-WIN-1",
            "timestamp": "2026-02-10T10:00:00Z",
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

    with open("data/trade_log.json", "w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "trade_id": "T-WIN-1",
                    "timestamp": "2026-02-10T10:00:00Z",
                    "symbol": "NIFTY",
                    "instrument": "OPT",
                    "side": "BUY",
                    "entry": 100.0,
                    "stop_loss": 90.0,
                    "target": 130.0,
                    "qty": 1,
                    "qty_units": 50,
                    "strategy": "SCALP",
                }
            )
            + "\n"
        )

    # Did not hit target (actual=0), but trailing stop exits above entry.
    update_trade_outcome("T-WIN-1", 105.0, 0, exit_reason="TRAIL_STOP")

    con = sqlite3.connect(str(db_path))
    outcome = con.execute(
        """
        SELECT realized_pnl, outcome_label, exit_reason
        FROM outcomes
        WHERE trade_id='T-WIN-1'
        ORDER BY rowid DESC
        LIMIT 1
        """
    ).fetchone()
    trade = con.execute(
        """
        SELECT realized_pnl, outcome_label, exit_reason
        FROM trades
        WHERE trade_id='T-WIN-1'
        """
    ).fetchone()
    con.close()

    assert outcome is not None
    assert outcome[0] > 0
    assert outcome[1] == "WIN"
    assert outcome[2] == "TRAIL_STOP"

    assert trade is not None
    assert trade[0] > 0
    assert trade[1] == "WIN"
    assert trade[2] == "TRAIL_STOP"
