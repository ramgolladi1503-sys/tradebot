from pathlib import Path

from config import config as cfg
from core.feed_debug import get_feed_debug


def test_feed_debug_handles_missing_db_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "missing.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    out = get_feed_debug(now_epoch=1700000000.0)
    assert isinstance(out, dict)
    assert out["last_db_tick_epoch"] is None
    assert out["last_depth_epoch"] is None
