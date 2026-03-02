from __future__ import annotations

import sys
from pathlib import Path

from config import config as cfg
from scripts import run_daily_audit


def test_run_daily_audit_skips_when_decision_events_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(sys, "argv", ["run_daily_audit.py"])
    monkeypatch.setattr(
        run_daily_audit,
        "build_truth_dataset",
        lambda out_parquet: (_ for _ in ()).throw(FileNotFoundError("No decision events found in JSONL or SQLite.")),
    )

    result = run_daily_audit.main()

    assert result["status"] == "ok_with_skips"
    assert result["reason"] == "NO_DECISION_EVENTS"
    assert (Path(cfg.LOGS_ROOT) / "daily_audit_status_latest.json").exists()


def test_run_daily_audit_skips_when_truth_parquet_unreadable(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    bad_truth = tmp_path / "data" / "truth_dataset.parquet"
    bad_truth.parent.mkdir(parents=True, exist_ok=True)
    bad_truth.write_text("not-a-parquet", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["run_daily_audit.py", "--truth", str(bad_truth)])

    result = run_daily_audit.main()

    assert result["status"] == "ok_with_skips"
    assert result["reason"] == "TRUTH_DATASET_UNREADABLE"
    assert (Path(cfg.LOGS_ROOT) / "daily_audit_status_latest.json").exists()
