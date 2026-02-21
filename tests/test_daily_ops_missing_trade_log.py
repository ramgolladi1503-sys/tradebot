from __future__ import annotations

import subprocess
from pathlib import Path

from config import config as cfg
from scripts import backfill_trades_db, daily_ops
from core.trade_log_paths import ensure_trade_log_exists


def test_ensure_trade_log_exists_creates_missing_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "TRADE_LOG_PATH", "logs/trade_log.jsonl", raising=False)
    out = ensure_trade_log_exists()
    assert out.exists()
    assert out.is_file()



def test_daily_ops_creates_missing_trade_log_and_completes(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "TRADE_LOG_PATH", "logs/trade_log.jsonl", raising=False)
    monkeypatch.setattr(
        daily_ops,
        "STEPS",
        [
            (["scripts/backfill_trades_db.py"], False),
            (["scripts/hash_trade_log.py"], True),
        ],
        raising=False,
    )

    calls: list[list[str]] = []

    def _fake_run(args, check=True):
        calls.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(daily_ops.subprocess, "run", _fake_run)

    daily_ops.main()

    assert (tmp_path / "logs" / "trade_log.jsonl").exists()
    assert len(calls) == 2


def test_backfill_trades_db_missing_log_does_not_crash(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "TRADE_LOG_PATH", "logs/trade_log.jsonl", raising=False)
    seen = {"trades": 0, "outcomes": 0}
    monkeypatch.setattr(backfill_trades_db, "insert_trade", lambda _entry: seen.__setitem__("trades", seen["trades"] + 1))
    monkeypatch.setattr(backfill_trades_db, "insert_outcome", lambda _entry: seen.__setitem__("outcomes", seen["outcomes"] + 1))

    result = backfill_trades_db.main()

    assert result["inserted"] == 0
    assert result["outcomes"] == 0
    assert seen["trades"] == 0
    assert seen["outcomes"] == 0
    assert Path(result["path"]).exists()
