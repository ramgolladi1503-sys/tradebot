import json
from pathlib import Path

import pytest

import core.orchestrator as orch_mod
from config import config as cfg
from core.time_utils import now_ist


def test_cycle_exception_still_writes_reports(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "DATA_ROOT", str(tmp_path / "data"), raising=False)
    (Path(cfg.LOGS_ROOT)).mkdir(parents=True, exist_ok=True)
    (Path(cfg.DATA_ROOT)).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(orch_mod.Orchestrator, "_start_depth_ws", lambda self: None)
    from core.recovery_state_machine import RecoveryState
    monkeypatch.setattr("core.recovery_state_machine.evaluate_feed_state", lambda _: RecoveryState.HEALTHY, raising=False)
    monkeypatch.setattr(orch_mod, "fetch_live_market_data", lambda: (_ for _ in ()).throw(RuntimeError("forced_cycle_error")))
    monkeypatch.setattr(orch_mod.time, "sleep", lambda _: (_ for _ in ()).throw(StopIteration()))
    monkeypatch.setattr(orch_mod.RunLock, "acquire", lambda self: (True, "ok"))
    monkeypatch.setattr(orch_mod.RunLock, "release", lambda self: None)

    monkeypatch.setattr(cfg, "ORCHESTRATOR_FAST_LOOP_ENABLE", False, raising=False)
    orch = orch_mod.Orchestrator(total_capital=100000, poll_interval=1)

    orch.live_monitoring(run_once=True)

    day = now_ist().date().isoformat()
    audit_path = Path(cfg.LOGS_ROOT) / f"daily_audit_{day}.json"
    exec_path = Path(cfg.LOGS_ROOT) / f"execution_report_{day}.json"
    suggestions_status_path = Path(cfg.LOGS_ROOT) / "suggestions_status.json"
    engine_cycle_status_path = Path(cfg.LOGS_ROOT) / "engine_cycle_status.json"

    assert audit_path.exists()
    assert exec_path.exists()
    assert suggestions_status_path.exists()
    assert engine_cycle_status_path.exists()

    audit_doc = json.loads(audit_path.read_text())
    exec_doc = json.loads(exec_path.read_text())
    suggestions_status = json.loads(suggestions_status_path.read_text())
    engine_cycle_status = json.loads(engine_cycle_status_path.read_text())

    assert audit_doc["date"] == day
    assert exec_doc["date"] == day
    assert isinstance(exec_doc.get("executions"), list)
    assert exec_doc.get("executions") == []
    assert exec_doc.get("reason")
    assert suggestions_status["status"] == "error"
    assert engine_cycle_status["cycle_ok"] is False
    assert engine_cycle_status["last_error"]
