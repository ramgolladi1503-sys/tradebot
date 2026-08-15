import core.orchestrator as orchestrator_module
from core.orchestrator import Orchestrator
from tests.fixtures.canonical_feed_factory import make_valid_canonical_feed_pair


def _configure_market_open(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator_module, "is_market_open_ist", lambda now=None: True)
    monkeypatch.setattr(orchestrator_module, "now_utc_epoch", lambda: 1772800000.0)
    monkeypatch.setattr(orchestrator_module, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(orchestrator_module.cfg, "RUNTIME_HEALTH_MAX_AGE_SEC", 30.0, raising=False)
    monkeypatch.setattr(orchestrator_module.cfg, "FEED_RUNTIME_MAX_AGE_SEC", 30.0, raising=False)


def _orch_without_decisions(monkeypatch):
    orch = Orchestrator.__new__(Orchestrator)
    monkeypatch.setattr(orch, "_latest_decision_rows", lambda max_age_sec=None: {})
    return orch


def test_pilot_feed_ok_uses_canonical_runtime_when_no_decision_rows(monkeypatch, tmp_path):
    _configure_market_open(monkeypatch, tmp_path)
    make_valid_canonical_feed_pair(
        tmp_path,
        feed_ok=True,
        runtime_updates={
            "ts_epoch": 1772800000.0,
            "runtime_state": "RUNNING",
            "ws_connected": True,
            "last_tick_age_sec": 0.5,
            "last_db_tick_age_sec": 0.5,
        },
    )

    ok, reasons = _orch_without_decisions(monkeypatch)._pilot_feed_ok()
    assert ok is True
    assert reasons == []


def test_pilot_feed_ok_fails_closed_when_canonical_runtime_missing(monkeypatch, tmp_path):
    _configure_market_open(monkeypatch, tmp_path)

    ok, reasons = _orch_without_decisions(monkeypatch)._pilot_feed_ok()
    assert ok is False
    assert reasons == ["feed_runtime:MISSING_ARTIFACT"]


def test_pilot_feed_ok_respects_canonical_feed_not_ok(monkeypatch, tmp_path):
    _configure_market_open(monkeypatch, tmp_path)
    make_valid_canonical_feed_pair(
        tmp_path,
        feed_ok=False,
        runtime_updates={
            "ts_epoch": 1772800000.0,
            "runtime_state": "RUNNING",
            "ws_connected": True,
            "feed_reasons": ["STALE_FEED"],
            "last_tick_age_sec": 1.0,
        },
    )

    ok, reasons = _orch_without_decisions(monkeypatch)._pilot_feed_ok()
    assert ok is False
    assert "feed_stale:FEED_RUNTIME_DEAD" in reasons or "feed_stale:STALE_FEED" in reasons


def test_pilot_feed_ok_accepts_fresh_canonical_runtime_without_legacy_health(monkeypatch, tmp_path):
    _configure_market_open(monkeypatch, tmp_path)
    make_valid_canonical_feed_pair(
        tmp_path,
        feed_ok=True,
        runtime_updates={
            "ts_epoch": 1772800000.0,
            "ws_connected": True,
            "runtime_state": "RUNNING",
            "feed_truth_state": "LIVE",
            "feed_truth_reason_code": "OK",
            "last_tick_age_sec": 0.5,
            "last_depth_age_sec": 1.0,
            "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
            "option_active_blockers_by_symbol": {"NIFTY": []},
        },
    )

    ok, reasons = _orch_without_decisions(monkeypatch)._pilot_feed_ok()
    assert ok is True
    assert reasons == []


def test_pilot_feed_ok_blocks_stale_canonical_runtime(monkeypatch, tmp_path):
    _configure_market_open(monkeypatch, tmp_path)
    monkeypatch.setattr(orchestrator_module.cfg, "RUNTIME_HEALTH_MAX_AGE_SEC", 5.0, raising=False)
    monkeypatch.setattr(orchestrator_module.cfg, "FEED_RUNTIME_MAX_AGE_SEC", 5.0, raising=False)
    make_valid_canonical_feed_pair(
        tmp_path,
        feed_ok=True,
        runtime_updates={
            "ts_epoch": 1772799900.0,
            "ws_connected": True,
            "runtime_state": "RUNNING",
            "last_tick_age_sec": 1.0,
        },
    )

    ok, reasons = _orch_without_decisions(monkeypatch)._pilot_feed_ok()
    assert ok is False
    assert "feed_stale:RUNTIME_HEALTH_STALE" in reasons


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
