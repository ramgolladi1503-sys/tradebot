import json

import core.orchestrator as orchestrator_module
from core.orchestrator import Orchestrator


def test_pilot_feed_ok_uses_runtime_health_when_no_decision_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator_module, "is_market_open_ist", lambda now=None: True)
    monkeypatch.setattr(orchestrator_module, "now_utc_epoch", lambda: 1772800000.0)
    monkeypatch.setattr(orchestrator_module, "logs_dir", lambda: tmp_path)

    payload = {
        "ts_epoch": 1772800000.0,
        "snapshot_ts_epoch": 1772800000.0,
        "feed": {
            "ws_connected": True,
            "ltp_required": False,
            "ltp_age_sec": 120.0,
            "ltp_max_age_sec": 900.0,
            "sla_status": "PLANNING",
        },
    }
    (tmp_path / "runtime_health_latest.json").write_text(json.dumps(payload), encoding="utf-8")

    orch = Orchestrator.__new__(Orchestrator)
    monkeypatch.setattr(orch, "_latest_decision_rows", lambda max_age_sec=None: {})

    ok, reasons = orch._pilot_feed_ok()
    assert ok is True
    assert reasons == []


def test_pilot_feed_ok_returns_truthful_unknown_when_no_health_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator_module, "is_market_open_ist", lambda now=None: True)
    monkeypatch.setattr(orchestrator_module, "now_utc_epoch", lambda: 1772800000.0)
    monkeypatch.setattr(orchestrator_module, "logs_dir", lambda: tmp_path)

    orch = Orchestrator.__new__(Orchestrator)
    monkeypatch.setattr(orch, "_latest_decision_rows", lambda max_age_sec=None: {})

    ok, reasons = orch._pilot_feed_ok()
    assert ok is False
    assert "feed_stale:UNKNOWN" in reasons
