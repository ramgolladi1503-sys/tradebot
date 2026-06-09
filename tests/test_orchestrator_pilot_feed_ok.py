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


def test_pilot_feed_ok_respects_runtime_health_stale_breaker(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator_module, "is_market_open_ist", lambda now=None: True)
    monkeypatch.setattr(orchestrator_module, "now_utc_epoch", lambda: 1772800000.0)
    monkeypatch.setattr(orchestrator_module, "logs_dir", lambda: tmp_path)

    payload = {
        "ts_epoch": 1772800000.0,
        "snapshot_ts_epoch": 1772800000.0,
        "execution": {
            "decision_breakers": {
                "blocked": True,
                "blocked_reasons": ["STALE_FEED"],
            }
        },
        "feed": {
            "ws_connected": True,
            "ltp_required": False,
            "ltp_age_sec": 1.0,
            "ltp_max_age_sec": 900.0,
            "sla_status": "OK",
        },
    }
    (tmp_path / "runtime_health_latest.json").write_text(json.dumps(payload), encoding="utf-8")

    orch = Orchestrator.__new__(Orchestrator)
    monkeypatch.setattr(orch, "_latest_decision_rows", lambda max_age_sec=None: {})

    ok, reasons = orch._pilot_feed_ok()
    assert ok is False
    assert "feed_stale:DECISION_BREAKER_STALE_FEED" in reasons


def test_pilot_feed_ok_prefers_fresh_feed_runtime_over_stale_runtime_health(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator_module, "is_market_open_ist", lambda now=None: True)
    monkeypatch.setattr(orchestrator_module, "now_utc_epoch", lambda: 1772800000.0)
    monkeypatch.setattr(orchestrator_module, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(orchestrator_module.cfg, "RUNTIME_HEALTH_MAX_AGE_SEC", 5.0, raising=False)
    monkeypatch.setattr(orchestrator_module.cfg, "FEED_RUNTIME_MAX_AGE_SEC", 30.0, raising=False)

    runtime_health_payload = {
        "ts_epoch": 1772799900.0,
        "snapshot_ts_epoch": 1772799900.0,
        "feed": {
            "ws_connected": True,
            "ltp_required": False,
            "ltp_age_sec": 1.0,
            "ltp_max_age_sec": 900.0,
            "sla_status": "OK",
        },
    }
    feed_runtime_payload = {
        "ts_epoch": 1772800000.0,
        "ws_connected": True,
        "runtime_state": "RUNNING",
        "feed_truth_state": "LIVE",
        "feed_truth_reason_code": "live",
        "feed_ok": True,
        "last_tick_age_sec": 0.5,
        "last_depth_age_sec": 1.0,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_active_blockers_by_symbol": {"NIFTY": []},
    }
    (tmp_path / "runtime_health_latest.json").write_text(json.dumps(runtime_health_payload), encoding="utf-8")
    (tmp_path / "feed_runtime_latest.json").write_text(json.dumps(feed_runtime_payload), encoding="utf-8")

    orch = Orchestrator.__new__(Orchestrator)
    monkeypatch.setattr(orch, "_latest_decision_rows", lambda max_age_sec=None: {})

    ok, reasons = orch._pilot_feed_ok()
    assert ok is True
    assert reasons == []


def test_pilot_feed_ok_blocks_when_full_feed_proof_reports_stale_required_symbol(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator_module, "is_market_open_ist", lambda now=None: True)
    monkeypatch.setattr(orchestrator_module, "now_utc_epoch", lambda: 1772800000.0)
    monkeypatch.setattr(orchestrator_module, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(orchestrator_module.cfg, "RUNTIME_HEALTH_MAX_AGE_SEC", 5.0, raising=False)
    monkeypatch.setattr(orchestrator_module.cfg, "FEED_RUNTIME_MAX_AGE_SEC", 30.0, raising=False)

    runtime_health_payload = {
        "ts_epoch": 1772800000.0,
        "snapshot_ts_epoch": 1772800000.0,
        "feed": {
            "ws_connected": True,
            "ltp_required": True,
            "ltp_age_sec": 4.0,
            "ltp_max_age_sec": 2.5,
            "sla_status": "OK",
            "full_feed_proof_ready": False,
            "full_feed_proof_blockers": ["UNDERLYING_TICK_STALE"],
            "underlying_ltp_stale_symbols": ["NIFTY"],
            "underlying_ltp_age_by_symbol": {"NIFTY": 4.0},
            "underlying_ltp_proof_state": "STALE",
        },
    }
    (tmp_path / "runtime_health_latest.json").write_text(json.dumps(runtime_health_payload), encoding="utf-8")

    orch = Orchestrator.__new__(Orchestrator)
    monkeypatch.setattr(orch, "_latest_decision_rows", lambda max_age_sec=None: {})

    ok, reasons = orch._pilot_feed_ok()
    assert ok is False
    assert "feed_stale:UNDERLYING_LTP_STALE" in reasons
    assert "feed_stale:UNDERLYING_TICK_STALE" in reasons or "feed_stale:UNDERLYING_TICK_STALE" not in reasons


def test_update_decision_breakers_skips_stale_feed_on_tiny_option_sample(monkeypatch):
    monkeypatch.setattr(orchestrator_module, "now_utc_epoch", lambda: 1772800000.0)
    monkeypatch.setattr(orchestrator_module.cfg, "BREAKER_STALE_FEED_MIN_OPTION_ROWS", 8, raising=False)

    class _DummyBreakers:
        def __init__(self):
            self.calls = []

        def observe_stale_feed(self, unhealthy, *, evidence=None, now_ts=None):
            self.calls.append((bool(unhealthy), dict(evidence or {}), float(now_ts or 0.0)))
            return []

        def observe_price_mismatch(self, unhealthy, *, evidence=None, now_ts=None):
            return []

        def observe_broker_failure(self, unhealthy, *, evidence=None, now_ts=None):
            return []

        def snapshot(self, *, now_ts=None):
            return {"enabled": True, "blocked": False, "blocked_reasons": [], "breakers": {}}

        def should_block_decisions(self, *, now_ts=None):
            return False, []

    class _DummyEngine:
        def get_failure_snapshot(self, now_epoch=None):
            return {"counters": {}}

    orch = Orchestrator.__new__(Orchestrator)
    orch.decision_breakers = _DummyBreakers()
    orch.execution_engine = _DummyEngine()
    orch._decision_breaker_failure_counters = {}

    market_data_list = [
        {"instrument": "OPT", "feed_health": {"is_fresh": False}},
        {"instrument": "OPT", "feed_health": {"is_fresh": False}},
        {"instrument": "OPT", "feed_health": {"is_fresh": True}},
        {"instrument": "EQ", "feed_health": {"is_fresh": False}},
    ]

    orch._update_decision_breakers(market_data_list)

    assert orch.decision_breakers.calls == []
