import json

import pytest

import core.orchestrator as orch_mod
from core.time_utils import now_ist


def test_cycle_exception_still_writes_reports(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(orch_mod.Orchestrator, "_start_depth_ws", lambda self: None)
    monkeypatch.setattr(orch_mod, "fetch_live_market_data", lambda: (_ for _ in ()).throw(RuntimeError("forced_cycle_error")))
    monkeypatch.setattr(orch_mod.time, "sleep", lambda _: (_ for _ in ()).throw(StopIteration()))

    orch = orch_mod.Orchestrator(total_capital=100000, poll_interval=0)

    with pytest.raises(StopIteration):
        orch.live_monitoring()

    day = now_ist().date().isoformat()
    audit_path = tmp_path / "logs" / f"daily_audit_{day}.json"
    exec_path = tmp_path / "logs" / f"execution_report_{day}.json"

    assert audit_path.exists()
    assert exec_path.exists()

    audit_doc = json.loads(audit_path.read_text())
    exec_doc = json.loads(exec_path.read_text())

    assert audit_doc["date"] == day
    assert exec_doc["date"] == day
    assert isinstance(exec_doc.get("executions"), list)
    assert exec_doc.get("executions") == []
    assert exec_doc.get("reason")
