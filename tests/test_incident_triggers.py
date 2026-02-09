import json
from pathlib import Path

from config import config as cfg
import core.audit_log as audit
import core.incidents as incidents
import core.risk_halt as risk_halt


def test_db_write_fail_triggers_halt(tmp_path, monkeypatch):
    monkeypatch.setattr(incidents, "INCIDENTS_PATH", tmp_path / "incidents.jsonl")
    monkeypatch.setattr(audit, "AUDIT_LOG", tmp_path / "audit_log.jsonl")
    monkeypatch.setattr(cfg, "RISK_HALT_FILE", str(tmp_path / "risk_halt.json"))

    incident_id = incidents.trigger_db_write_fail({"detail": "test"})
    assert incident_id
    assert (tmp_path / "incidents.jsonl").exists()
    assert (tmp_path / "risk_halt.json").exists()

    payload = json.loads((tmp_path / "risk_halt.json").read_text())
    assert payload.get("halted") is True
