from __future__ import annotations

import json
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

    def _fake_run(args, check=True, cwd=None):
        calls.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(daily_ops.subprocess, "run", _fake_run)

    result = daily_ops.main()

    assert (tmp_path / "logs" / "trade_log.jsonl").exists()
    assert len(calls) == 2
    assert result["status"] == "ok_with_skips"
    assert "trade_log_empty" in result["reasons"]


def test_daily_ops_optional_step_failure_returns_ok_with_skips(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "TRADE_LOG_PATH", "logs/trade_log.jsonl", raising=False)
    monkeypatch.setattr(
        daily_ops,
        "STEPS",
        [
            (["scripts/hash_trade_log.py"], True),
            (["scripts/backfill_trades_db.py"], False),
        ],
        raising=False,
    )

    def _fake_run(args, check=True, cwd=None):
        if any(str(a).endswith("hash_trade_log.py") for a in args):
            raise subprocess.CalledProcessError(returncode=2, cmd=args)
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(daily_ops.subprocess, "run", _fake_run)

    result = daily_ops.main()

    assert result["status"] == "ok_with_skips"


def test_daily_ops_ingests_daily_audit_ok_with_skips_status(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "TRADE_LOG_PATH", "logs/trade_log.jsonl", raising=False)
    monkeypatch.setattr(daily_ops, "STEPS", [], raising=False)

    status_path = tmp_path / "logs" / "daily_audit_status_latest.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps({"status": "ok_with_skips", "reason_code": "NO_DECISION_EVENTS"}),
        encoding="utf-8",
    )

    result = daily_ops.main()

    assert result["status"] == "ok_with_skips"
    assert "daily_audit:NO_DECISION_EVENTS" in result["reasons"]


def test_daily_ops_ingests_outcome_truth_degraded_status(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "TRADE_LOG_PATH", "logs/trade_log.jsonl", raising=False)
    monkeypatch.setattr(cfg, "OUTCOME_TRUTH_STATUS_PATH", str(tmp_path / "logs" / "outcome_truth_status_latest.json"), raising=False)
    monkeypatch.setattr(daily_ops, "STEPS", [], raising=False)

    status_path = tmp_path / "logs" / "outcome_truth_status_latest.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps({"status": "DEGRADED", "blockers": ["OUTCOME_ROWS_INSUFFICIENT"]}),
        encoding="utf-8",
    )

    result = daily_ops.main()

    assert result["status"] == "ok_with_skips"
    assert "outcome_truth:OUTCOME_ROWS_INSUFFICIENT" in result["reasons"]


def test_daily_ops_executes_steps_from_repo_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "TRADE_LOG_PATH", "logs/trade_log.jsonl", raising=False)
    monkeypatch.setattr(daily_ops, "ROOT", tmp_path / "repo_root", raising=False)
    monkeypatch.setattr(
        daily_ops,
        "STEPS",
        [(["scripts/backfill_trades_db.py"], False)],
        raising=False,
    )
    calls: list[dict] = []

    def _fake_run(args, check=True, cwd=None):
        calls.append({"args": list(args), "cwd": cwd})
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(daily_ops.subprocess, "run", _fake_run)
    result = daily_ops.main()

    assert result["status"] == "ok_with_skips"
    assert len(calls) == 1
    assert calls[0]["cwd"] == (tmp_path / "repo_root")
    assert str(calls[0]["args"][1]).endswith("/scripts/backfill_trades_db.py")


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
