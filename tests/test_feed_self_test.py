from pathlib import Path

from config import config as cfg
from core import feed_self_test


def test_self_test_does_not_crash_when_db_missing_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "missing.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    report = feed_self_test.run_self_test(now_epoch=1700000000.0)
    assert isinstance(report, dict)
    assert report["db_tick_epoch"] is None
    assert report["depth_epoch"] is None
