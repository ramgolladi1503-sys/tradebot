from __future__ import annotations

from datetime import datetime
import sqlite3
from zoneinfo import ZoneInfo

from config import config as cfg
import core.reject_shadow as reject_shadow


IST = ZoneInfo("Asia/Kolkata")


def _ts_ist(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> float:
    return float(datetime(year, month, day, hour, minute, second, tzinfo=IST).timestamp())


def _base_event(symbol: str, ts_epoch: float) -> dict:
    return {
        "ts_epoch": ts_epoch,
        "symbol": symbol,
        "side": "BUY_CALL",
        "entry": 100.0,
        "stop": 95.0,
        "target": 105.0,
        "regime": "TREND",
        "confidence_score": 0.82,
        "gates_failed": ["quote_missing"],
        "soft_vetos": ["quote_missing"],
        "first_blocking_gate": "quote_missing",
        "hard_reject_reason": "quote_missing",
        "execution_allowed": False,
        "mode": "PAPER",
    }


def test_reject_shadow_insert_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "shadow.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(reject_shadow, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)

    ts_epoch = _ts_ist(2026, 2, 24, 10, 5)
    event = _base_event("NIFTY", ts_epoch)
    first = reject_shadow.record_candidate_decision(event)
    second = reject_shadow.record_candidate_decision(event)
    assert first["status"] == "ok"
    assert second["status"] == "ok"

    conn = sqlite3.connect(db_path)
    try:
        reject_shadow.ensure_tables(conn)
        shadow_rows = conn.execute("SELECT COUNT(1) FROM rejected_trades_shadow").fetchone()[0]
        decision_rows = conn.execute("SELECT COUNT(1) FROM candidate_decision_events").fetchone()[0]
        assert int(shadow_rows) == 1
        assert int(decision_rows) == 1
    finally:
        conn.close()


def test_reject_shadow_evaluate_resolves_win_loss_timeout(tmp_path, monkeypatch):
    db_path = tmp_path / "shadow_eval.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(reject_shadow, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "REJECT_SHADOW_TIMEOUT_MIN", 30, raising=False)

    ts_win = _ts_ist(2026, 2, 24, 10, 0)
    ts_loss = _ts_ist(2026, 2, 24, 10, 2)
    ts_timeout = _ts_ist(2026, 2, 24, 10, 4)

    reject_shadow.record_candidate_decision(_base_event("NIFTY_WIN", ts_win))
    reject_shadow.record_candidate_decision(_base_event("NIFTY_LOSS", ts_loss))
    reject_shadow.record_candidate_decision(_base_event("NIFTY_TIMEOUT", ts_timeout))

    reject_shadow.record_price_trace(symbol="NIFTY_WIN", price=101.0, ts_epoch=ts_win + 10, mode="PAPER")
    reject_shadow.record_price_trace(symbol="NIFTY_WIN", price=105.2, ts_epoch=ts_win + 40, mode="PAPER")
    reject_shadow.record_price_trace(symbol="NIFTY_LOSS", price=99.0, ts_epoch=ts_loss + 8, mode="PAPER")
    reject_shadow.record_price_trace(symbol="NIFTY_LOSS", price=94.9, ts_epoch=ts_loss + 20, mode="PAPER")

    payload = reject_shadow.evaluate_pending(date="2026-02-24", batch_limit=200)
    assert payload["status"] == "ok"
    assert payload["processed"] >= 3

    conn = sqlite3.connect(db_path)
    try:
        status_map = {
            str(sym): str(status)
            for sym, status in conn.execute(
                "SELECT symbol, shadow_status FROM rejected_trades_shadow WHERE trade_date='2026-02-24'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert status_map["NIFTY_WIN"] == "WIN"
    assert status_map["NIFTY_LOSS"] == "LOSS"
    assert status_map["NIFTY_TIMEOUT"] == "TIMEOUT"
