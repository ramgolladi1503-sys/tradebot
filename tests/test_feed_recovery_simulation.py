from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import core.engine_phase2_adapter as phase2_adapter
import core.orchestrator as orchestrator_module
from core.feed_recovery_coordinator import FeedRecoveryCoordinator
from core.orchestrator import Orchestrator
from core.runtime_status_overlay import derive_feed_ok, publish_feed_unhealthy_status_overlay
from core.expectancy.top_opportunity_selector import select_top_opportunities
from core.observability import build_observability_evidence_bundle, FeedStateEventEmitter, ObservabilityContext, ObservabilityIds


def test_ws1006_classification():
    """
    Verify WS 1006 classification:
    - Soft reconnect is accepted when session retry budget is not exhausted.
    - Subsequent connection drops block further reconnects once budget/window limit is hit.
    """
    coord = FeedRecoveryCoordinator(
        max_recoverable_attempts_per_session=2,
        recoverable_retry_cooldown_sec=0.0,
        max_recoveries_per_window=3,
        recovery_window_sec=600.0,
    )
    
    # Attempt 1: accepted as soft reconnect
    res1 = coord.request_recovery(
        source="on_close",
        code=1006,
        reason="connection was closed uncleanly (peer dropped the TCP connection)"
    )
    assert res1.accepted is True
    assert res1.action == "SOFT_RECONNECT"
    assert res1.state.recovery_in_progress is True
    
    coord.clear_recovery(source="test", reason="reconnect_verified")
    
    # Attempt 2: accepted as soft reconnect
    res2 = coord.request_recovery(
        source="on_close",
        code=1006,
        reason="peer dropped"
    )
    assert res2.accepted is True
    assert res2.action == "SOFT_RECONNECT"
    
    coord.clear_recovery(source="test", reason="reconnect_verified")
    
    # Attempt 3: blocked (exceeds session attempt budget)
    res3 = coord.request_recovery(
        source="on_close",
        code=1006,
        reason="peer dropped again"
    )
    assert res3.accepted is False
    assert res3.action == "RECOVERY_BLOCKED"
    assert res3.state.recovery_blocked is True


def test_reactor_not_restartable_classification():
    """
    Verify ReactorNotRestartable classification:
    - ReactorNotRestartable is immediately classified as terminal process restart state.
    """
    coord = FeedRecoveryCoordinator()
    res = coord.request_recovery(
        source="on_error",
        code=1006,
        reason="ReactorNotRestartable: reactor cannot be restarted"
    )
    assert res.accepted is False
    assert res.action == "TERMINAL"
    assert res.state.process_restart_required is True
    assert res.state.terminal_failure is True
    assert res.state.recovery_blocked is True


def test_no_restart_storm_after_fatal_reactor():
    """
    Verify that no restart storm occurs after a fatal reactor state is set.
    """
    coord = FeedRecoveryCoordinator()
    
    # Trigger terminal failure
    res1 = coord.request_recovery(
        source="on_error",
        code=1006,
        reason="ReactorNotRestartable: reactor stopped"
    )
    assert res1.action == "TERMINAL"
    assert res1.state.recovery_blocked is True
    
    # Subsequent reconnect attempts must be rejected/blocked immediately
    res2 = coord.request_recovery(
        source="watchdog",
        code=1006,
        reason="peer dropped connection"
    )
    assert res2.accepted is False
    assert res2.action == "TERMINAL"  # Stays in terminal block
    assert res2.state.recovery_blocked is True
    assert res2.state.process_restart_required is True


def test_feed_ok_remains_false_when_lifecycle_fatal():
    """
    Verify that feed_ok remains false when the lifecycle enters a fatal state.
    """
    payload = {
        "market_open": True,
        "ws_connected": False,
        "runtime_state": "FEED_LIFECYCLE_FATAL",
        "state_machine": {"state": "DOWN", "reason": "reactornotrestartable"},
        "option_feed_block_reason_by_symbol": {"NIFTY": "NO_LIVE_OPTION_FEED"},
    }
    assert derive_feed_ok(payload) is False


def test_phase2_remains_empty_when_feed_invalid(monkeypatch, tmp_path):
    """
    Verify that the Phase 2 candidate pool remains empty if feed_ok is false.
    """
    monkeypatch.setattr(phase2_adapter, "logs_dir", lambda: tmp_path)
    
    # Write a runtime state snapshot representing unhealthy feed
    feed_payload = {"feed_ok": False}
    (tmp_path / "feed_runtime_latest.json").write_text(json.dumps(feed_payload))
    
    raw_candidates = [{"trade_id": "trade-1", "symbol": "NIFTY"}]
    
    # Unwrap any CI wrappers to test the raw underlying build_candidates_phase2 logic
    func = phase2_adapter.build_candidates_phase2
    unwrapped = None
    
    def walk_closure(f):
        nonlocal unwrapped
        if unwrapped:
            return
        if hasattr(f, "__code__") and "engine_phase2_adapter.py" in f.__code__.co_filename and f.__name__ == "build_candidates_phase2":
            unwrapped = f
            return
        if hasattr(f, "__closure__") and f.__closure__:
            for cell in f.__closure__:
                val = cell.cell_contents
                if callable(val) and val != f:
                    walk_closure(val)
                    
    walk_closure(func)
    if unwrapped:
        func = unwrapped

    res = func(raw_candidates)
    assert res == []


def test_fallback_executable_remains_false():
    """
    Verify that fallback_executable remains False and fallback candidates are blocked.
    """
    # 1. Verify top opportunity selector filters/blocks fallback quotes
    fallback_candidate = {
        "candidate_id": "cand-fallback",
        "trade_id": "trade-fallback",
        "symbol": "NIFTY",
        "strategy_family": "breakout",
        "execution_truth_state": "LIVE",
        "execution_status": "executable",
        "reportable_executable": True,
        "execution_allowed": True,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "fallback_used": True,
        "quote_source": "REST_FALLBACK",
        "blockers": [],
    }
    
    report = select_top_opportunities([fallback_candidate])
    assert report.executable_count == 0
    assert report.rejected_count == 1
    assert "fallback_not_rankable" in report.rejected_opportunities[0].why_not_ranked

    # 2. Verify evidence bundle count of fallback_executable remains 0
    ctx = ObservabilityContext(
        ids=ObservabilityIds(run_id="run_1", cycle_id="cycle_1", trace_id="trace_1", span_id="span_1"),
        stage="runtime.cycle",
        execution_mode="paper",
    )
    
    emitter = FeedStateEventEmitter(ctx)
    events = [
        emitter.quote_fallback_used(timestamp=datetime.now(timezone.utc), candidate_id="cand-1").as_dict(),
        emitter.blocked_fallback(timestamp=datetime.now(timezone.utc), candidate_id="cand-1").as_dict(),
    ]
    
    bundle = build_observability_evidence_bundle(events)
    safety_report = bundle.reports["fallback_safety_report.json"]
    assert safety_report["fallback_executable_count"] == 0
    assert safety_report["safe"] is True


def test_no_order_path_enabled_when_feed_fatal(monkeypatch, tmp_path):
    """
    Verify that suggestions and engine status overlays prevent order execution (visible_executable_count=0)
    when the feed is fatal.
    """
    monkeypatch.setattr(orchestrator_module, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(orchestrator_module.cfg, "FEED_RUNTIME_STATUS_OVERLAY_ENABLE", True, raising=False)
    
    feed_payload = {
        "market_open": True,
        "ws_connected": False,
        "subscribed_tokens_count": 2,
        "intended_tokens_count": 2,
        "last_db_tick_epoch": 180.0,
        "last_db_tick_age_sec": 20.0,
        "last_ws_tick_epoch": None,
        "last_tick_age_sec": None,
        "last_depth_epoch": None,
        "last_depth_age_sec": None,
        "state_machine": {"state": "DOWN", "reason": "reactornotrestartable"},
        "option_feed_block_reason_by_symbol": {"NIFTY": "NO_LIVE_OPTION_FEED"},
        "runtime_state": "FEED_LIFECYCLE_FATAL",
    }
    
    publish_feed_unhealthy_status_overlay(feed_payload=feed_payload, logs_root=tmp_path)
    
    suggestions = json.loads((tmp_path / "suggestions_status.json").read_text())
    engine = json.loads((tmp_path / "engine_cycle_status.json").read_text())
    
    assert suggestions["status"] == "blocked"
    assert suggestions["visible_executable_count"] == 0
    assert engine["cycle_stage"] == "blocked"
    assert engine["visible_executable_count"] == 0


def test_orchestrator_hot_loop_prevention_on_fatal_state(monkeypatch, tmp_path):
    """
    Verify that the orchestrator live monitoring loop sleeps to prevent CPU hot-spinning
    when the feed state is fatal.
    """
    # Point logs_dir to a temp path
    monkeypatch.setattr(orchestrator_module, "logs_dir", lambda: tmp_path)
    
    # Write a fatal feed runtime payload
    feed_payload = {
        "runtime_state": "FEED_LIFECYCLE_FATAL",
        "ws_connected": False,
        "feed_ok": False,
        "state_machine": {"state": "DOWN", "reason": "reactornotrestartable"}
    }
    (tmp_path / "feed_runtime_latest.json").write_text(json.dumps(feed_payload))
    (tmp_path / "feed_truth_latest.json").write_text("{}")
    
    # Stub basic orchestrator properties
    orch = Orchestrator.__new__(Orchestrator)
    orch.poll_interval = 0.5
    
    # Stub logger functions to check calls if needed
    monkeypatch.setattr(orchestrator_module, "canonical_suggestions_log_path", lambda: tmp_path / "suggestions.jsonl")
    
    # Track sleep calls to verify that orchestrator slept for a safe period
    sleep_calls = []
    def fake_sleep(sec):
        sleep_calls.append(sec)
    monkeypatch.setattr(orchestrator_module.time, "sleep", fake_sleep)
    
    # Execute loop once
    orch._legacy_live_monitoring(run_once=True)
    
    num_sleeps = len(sleep_calls)
    assert num_sleeps > 0
    assert sleep_calls[0] >= 1.9
