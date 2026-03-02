from __future__ import annotations

import importlib
import json
from pathlib import Path


def test_reconcile_outputs_use_logs_dir(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))

    import scripts.reconcile_fills as reconcile_fills

    importlib.reload(reconcile_fills)

    assert reconcile_fills.OUT_JSON == logs_root / "reconciliation_summary.json"
    assert reconcile_fills.OUT_CSV == logs_root / "reconciliation_report.csv"
    assert reconcile_fills.OUT_HIST == logs_root / "reconciliation_history.json"
    assert reconcile_fills.UPDATES_PATH == logs_root / "trade_updates.jsonl"


def test_trade_updates_write_to_logs_dir(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))

    import core.trade_logger as trade_logger

    importlib.reload(trade_logger)
    trade_logger._append_update({"trade_id": "t-1", "type": "outcome", "actual": 1})

    updates_path = logs_root / "trade_updates.jsonl"
    assert updates_path.exists()
    lines = updates_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    payload = json.loads(lines[-1])
    assert payload["trade_id"] == "t-1"
