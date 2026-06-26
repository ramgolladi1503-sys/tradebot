import pytest
from core.feed_restart_policy import evaluate_restart_policy, RestartPolicyDecision
from core.feed_state_model import FeedVerdict, FeedLifecycleState, FeedOperationalState
from core.feed_snapshot_reader import normalize_legacy_snapshot

def test_evaluate_restart_policy_process_restart():
    snapshot = normalize_legacy_snapshot({
        "ts_epoch": 1000.0,
        "start_epoch": 1000.0,
        "runtime_state": "LIVE",
        "ws_connected": True,
        "effective_ws_connected": True,
        "market_open": True,
        "process_restart_required": True,
        "feed_ok_hysteresis_state": True,
    })
    verdict = FeedVerdict(
        lifecycle_state=FeedLifecycleState.LIVE,
        operational_state=FeedOperationalState.LIVE,
        restart_required=False,
        feed_ok=True,
        reason_code="OK",
        blockers=()
    )
    decision = evaluate_restart_policy(snapshot, verdict)
    assert decision.restart_required is True
    assert decision.restart_reason == "process_restart_flag_set"

def test_evaluate_restart_policy_lifecycle_restart():
    snapshot = normalize_legacy_snapshot({
        "ts_epoch": 1000.0,
        "start_epoch": 1000.0,
        "runtime_state": "AUTH_BLOCKED",
        "ws_connected": True,
        "effective_ws_connected": True,
        "market_open": True,
        "process_restart_required": False,
        "feed_ok_hysteresis_state": False,
    })
    verdict = FeedVerdict(
        lifecycle_state=FeedLifecycleState.RESTART_REQUIRED,
        operational_state=FeedOperationalState.DEAD,
        restart_required=True,
        feed_ok=False,
        reason_code="AUTH_BLOCKED",
        blockers=("auth_blocked",)
    )
    decision = evaluate_restart_policy(snapshot, verdict)
    assert decision.restart_required is True
    assert decision.restart_reason == "lifecycle_restart_required: AUTH_BLOCKED"

def test_evaluate_restart_policy_market_closed():
    snapshot = normalize_legacy_snapshot({
        "ts_epoch": 1000.0,
        "start_epoch": 1000.0,
        "runtime_state": "LIVE",
        "ws_connected": True,
        "effective_ws_connected": True,
        "market_open": False,
        "process_restart_required": False,
        "feed_ok_hysteresis_state": True,
    })
    verdict = FeedVerdict(
        lifecycle_state=FeedLifecycleState.MARKET_CLOSED,
        operational_state=FeedOperationalState.DEAD,
        restart_required=False,
        feed_ok=True,
        reason_code="MARKET_CLOSED",
        blockers=()
    )
    decision = evaluate_restart_policy(snapshot, verdict)
    assert decision.restart_required is False
    assert decision.should_sleep is True

def test_evaluate_restart_policy_down_non_fatal():
    snapshot = normalize_legacy_snapshot({
        "ts_epoch": 1000.0,
        "start_epoch": 1000.0,
        "runtime_state": "DOWN",
        "ws_connected": False,
        "effective_ws_connected": False,
        "market_open": True,
        "process_restart_required": False,
        "feed_ok_hysteresis_state": False,
    })
    verdict = FeedVerdict(
        lifecycle_state=FeedLifecycleState.DEGRADED,
        operational_state=FeedOperationalState.DEAD,
        restart_required=False,
        feed_ok=False,
        reason_code="WS_DISCONNECTED",
        blockers=("ws_disconnected",)
    )
    decision = evaluate_restart_policy(snapshot, verdict)
    assert decision.restart_required is False
    assert decision.restart_reason == "degraded_ws_disconnected"
