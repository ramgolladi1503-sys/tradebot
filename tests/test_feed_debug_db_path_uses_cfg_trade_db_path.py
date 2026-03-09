import sqlite3

from config import config as cfg
from core.feed_debug import get_feed_debug
from core.fs_utils import ensure_parent_dir


def test_feed_debug_db_path_uses_cfg_trade_db_path(monkeypatch, tmp_path):
    isolated_logs = tmp_path / "logs"
    isolated_logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("core.feed_debug.logs_dir", lambda: isolated_logs)
    db_path = tmp_path / "runtime" / "custom_trades.sqlite"
    ensure_parent_dir(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS ticks (timestamp_epoch REAL)")
        conn.execute("INSERT INTO ticks (timestamp_epoch) VALUES (?)", (1_700_000_100.0,))

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)

    payload = get_feed_debug(now_epoch=1_700_000_101.0)
    assert payload["db_path"] == str(db_path.expanduser())
    assert payload["last_db_tick_epoch"] is not None


def test_feed_debug_falls_back_to_ws_last_tick_epoch(monkeypatch, tmp_path):
    isolated_logs = tmp_path / "logs"
    isolated_logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("core.feed_debug.logs_dir", lambda: isolated_logs)
    db_path = tmp_path / "runtime" / "fallback.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr("core.feed_debug.mem_last_tick_epoch", lambda: None)
    monkeypatch.setattr("core.feed_debug._ws_last_tick_epoch", lambda: 1_700_000_200.0)

    payload = get_feed_debug(now_epoch=1_700_000_201.0)
    assert payload["last_tick_epoch_memory"] == 1_700_000_200.0
    assert payload["last_tick_age_sec"] is not None
