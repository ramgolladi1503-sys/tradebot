from __future__ import annotations

from config import config as cfg
import core.orchestrator as orchestrator_mod
from core.orchestrator import Orchestrator


def _orch_stub() -> Orchestrator:
    orch = Orchestrator.__new__(Orchestrator)
    orch._feed_auto_repair_state = {}
    orch._last_suggestion_reliability_eval_ts = 0.0
    return orch


def test_auto_repair_skips_non_live_modes(monkeypatch):
    orch = _orch_stub()
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_ENABLE", True, raising=False)
    result = orch._maybe_auto_repair_live_feed(
        {"symbol": "NIFTY", "market_context": {"execution_mode": "PAPER", "market_open": True}},
        gate_reasons=["FEED_STALE"],
    )
    assert result["action"] == "skipped_non_live"


def test_auto_repair_waits_for_streak_then_restarts(monkeypatch):
    orch = _orch_stub()
    restart_calls = []
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_TRIGGER_STRIKES", 2, raising=False)
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_MAX_RETRIES", 3, raising=False)
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_AUTH_RECHECK_SEC", 10_000.0, raising=False)
    monkeypatch.setattr(orchestrator_mod, "refresh_index_quote_from_rest", lambda symbol, force=False: True)
    monkeypatch.setattr(
        orchestrator_mod,
        "restart_depth_ws",
        lambda reason="unknown": restart_calls.append(reason) or True,
    )
    monkeypatch.setattr(orchestrator_mod, "now_utc_epoch", lambda: 1000.0)

    market_data = {
        "symbol": "NIFTY",
        "market_context": {"execution_mode": "LIVE", "market_open": True},
        "quote_ok": False,
    }
    first = orch._maybe_auto_repair_live_feed(market_data, gate_reasons=["FEED_STALE"])
    assert first["action"] == "waiting_streak"
    second = orch._maybe_auto_repair_live_feed(market_data, gate_reasons=["FEED_STALE"])
    assert second["action"] == "restart_attempted"
    assert second["restarted"] is True
    assert restart_calls, "expected restart_depth_ws to be called"


def test_auto_repair_requires_longer_streak_for_ltp_stale(monkeypatch):
    orch = _orch_stub()
    restart_calls = []
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_TRIGGER_STRIKES", 2, raising=False)
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_LTP_STALE_TRIGGER_STRIKES", 4, raising=False)
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_MAX_RETRIES", 3, raising=False)
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_AUTH_RECHECK_SEC", 10_000.0, raising=False)
    monkeypatch.setattr(orchestrator_mod, "refresh_index_quote_from_rest", lambda symbol, force=False: True)
    monkeypatch.setattr(
        orchestrator_mod,
        "restart_depth_ws",
        lambda reason="unknown": restart_calls.append(reason) or True,
    )
    monkeypatch.setattr(orchestrator_mod, "now_utc_epoch", lambda: 1000.0)

    market_data = {
        "symbol": "SENSEX",
        "market_context": {"execution_mode": "LIVE", "market_open": True},
        "quote_ok": False,
    }
    first = orch._maybe_auto_repair_live_feed(market_data, gate_reasons=["LTP_STALE"])
    second = orch._maybe_auto_repair_live_feed(market_data, gate_reasons=["LTP_STALE"])
    third = orch._maybe_auto_repair_live_feed(market_data, gate_reasons=["LTP_STALE"])
    fourth = orch._maybe_auto_repair_live_feed(market_data, gate_reasons=["LTP_STALE"])

    assert first["action"] == "waiting_streak"
    assert second["action"] == "waiting_streak"
    assert third["action"] == "waiting_streak"
    assert fourth["action"] == "restart_attempted"
    assert fourth["restarted"] is True
    assert restart_calls, "expected restart_depth_ws to be called"


def test_auto_repair_halts_on_auth_required(monkeypatch):
    orch = _orch_stub()
    restart_calls = []
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_TRIGGER_STRIKES", 1, raising=False)
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_MAX_RETRIES", 3, raising=False)
    monkeypatch.setattr(cfg, "FEED_AUTO_REPAIR_AUTH_RECHECK_SEC", 0.0, raising=False)
    monkeypatch.setattr(orchestrator_mod, "refresh_index_quote_from_rest", lambda symbol, force=False: False)
    monkeypatch.setattr(
        orchestrator_mod,
        "restart_depth_ws",
        lambda reason="unknown": restart_calls.append(reason) or True,
    )
    monkeypatch.setattr(orchestrator_mod, "is_auth_error", lambda **kwargs: True)
    monkeypatch.setattr(orchestrator_mod, "create_incident", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_mod, "now_utc_epoch", lambda: 2000.0)

    import core.auth_health as auth_health

    monkeypatch.setattr(
        auth_health,
        "get_kite_auth_health",
        lambda force=True: {"ok": False, "auth_state": "AUTH_REQUIRED", "error": "invalid session"},
    )

    result = orch._maybe_auto_repair_live_feed(
        {
            "symbol": "NIFTY",
            "market_context": {"execution_mode": "LIVE", "market_open": True},
            "quote_ok": False,
        },
        gate_reasons=["FEED_STALE"],
    )
    assert result["action"] == "auth_required"
    assert not restart_calls


def test_allow_planning_no_signal_fallback_tracks_market_context(monkeypatch):
    orch = _orch_stub()
    monkeypatch.setattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", True, raising=False)
    assert orch._allow_planning_no_signal_fallback(
        {"market_context": {"execution_mode": "PAPER", "market_open": True}}
    )
    assert not orch._allow_planning_no_signal_fallback(
        {"market_context": {"execution_mode": "LIVE", "market_open": True}}
    )


def test_suggestion_reliability_scheduler_respects_interval(monkeypatch):
    orch = _orch_stub()
    persisted = []
    calls = []
    now_values = iter([1000.0, 1010.0])
    monkeypatch.setattr(cfg, "SUGGESTION_RELIABILITY_CHECK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_RELIABILITY_INTERVAL_SEC", 60.0, raising=False)
    monkeypatch.setattr(orchestrator_mod, "now_utc_epoch", lambda: next(now_values))
    monkeypatch.setattr(orchestrator_mod, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(
        orchestrator_mod,
        "evaluate_suggestion_reliability",
        lambda **kwargs: calls.append(kwargs) or {
            "status": "OK",
            "allowed_to_candidate_ratio": 0.6,
            "allowed_count": 10,
            "candidate_count": 6,
            "top_reject_reasons": {},
        },
    )
    monkeypatch.setattr(
        orchestrator_mod,
        "persist_suggestion_reliability",
        lambda payload: persisted.append(payload),
    )

    orch._maybe_run_suggestion_reliability_check()
    orch._maybe_run_suggestion_reliability_check()

    assert len(calls) == 1
    assert len(persisted) == 1
