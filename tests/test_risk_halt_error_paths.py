from __future__ import annotations

import json
import sys
import types

import pytest

from config import config as cfg
from core import risk_halt


@pytest.fixture
def halt_file(monkeypatch, tmp_path):
    path = tmp_path / "risk" / "halt.json"
    monkeypatch.setattr(cfg, "RISK_HALT_FILE", str(path))
    return path


@pytest.mark.safety
def test_load_halt_fails_closed_on_corrupt_json(halt_file):
    halt_file.parent.mkdir(parents=True)
    halt_file.write_text("{not-valid-json", encoding="utf-8")

    assert risk_halt.load_halt() == {}


@pytest.mark.safety
def test_is_halted_fails_closed_on_corrupt_json(halt_file):
    halt_file.parent.mkdir(parents=True)
    halt_file.write_text("{not-valid-json", encoding="utf-8")

    assert risk_halt.is_halted() is False


@pytest.mark.safety
def test_set_halt_persists_halt_even_when_incident_notification_fails(
    monkeypatch, halt_file, caplog
):
    incidents = types.ModuleType("core.incidents")

    def fail_notification(_payload):
        raise RuntimeError("incident sink unavailable")

    incidents.trigger_hard_halt = fail_notification
    monkeypatch.setitem(sys.modules, "core.incidents", incidents)

    payload = risk_halt.set_halt("manual_stop", {"source": "qa"})

    assert payload["halted"] is True
    assert payload["reason"] == "manual_stop"
    assert json.loads(halt_file.read_text(encoding="utf-8"))["halted"] is True
    assert risk_halt.is_halted() is True
    assert "incident_hard_halt_error" in caplog.text
