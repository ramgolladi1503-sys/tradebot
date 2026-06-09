from __future__ import annotations

from core.feed_recovery_runtime import classify_feed_recovery_runtime


def _payload(**updates):
    payload = {
        "market_open": True,
        "feed_ok": False,
        "ws_connected": True,
        "effective_ws_connected": True,
        "runtime_state": "RUNNING",
        "state_machine": {"state": "LIVE", "reason": "ticks_flowing"},
        "subscribed_tokens_count": 24,
        "intended_tokens_count": 24,
        "subscribed_option_tokens_count": 18,
        "missing_option_tokens_count": 0,
        "last_tick_age_sec": 0.5,
        "last_depth_age_sec": 0.8,
        "warmup_clean_cycles": 3,
        "warmup_required_clean_cycles": 3,
        "verified_option_symbols": ["NIFTY", "BANKNIFTY"],
        "missing_option_symbols": [],
        "option_ticks_verified": True,
        "restart_count_1h": 0,
        "stale_strikes": 0,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_active_blockers_by_symbol": {"NIFTY": []},
    }
    payload.update(updates)
    return payload


def test_market_closed_never_requests_recovery():
    decision = classify_feed_recovery_runtime(_payload(market_open=False, feed_ok=False))

    assert decision.recovery_state == "MARKET_CLOSED"
    assert decision.action_hint == "no_recovery_market_closed"
    assert decision.should_attempt_recovery is False


def test_auth_blocked_requires_manual_auth_not_recovery():
    decision = classify_feed_recovery_runtime(_payload(runtime_state="AUTH_BLOCKED"))

    assert decision.recovery_state == "AUTH_BLOCKED"
    assert decision.action_hint == "manual_auth_required"
    assert decision.should_attempt_recovery is False


def test_healthy_feed_has_no_recovery_action():
    decision = classify_feed_recovery_runtime(_payload(feed_ok=True))

    assert decision.recovery_state == "HEALTHY"
    assert decision.action_hint == "no_recovery_needed"
    assert decision.should_attempt_recovery is False


def test_feed_with_warmup_incomplete_proves_not_yet_healthy():
    decision = classify_feed_recovery_runtime(_payload(feed_ok=True, warmup_clean_cycles=1))

    assert decision.recovery_state == "RECOVERY_PROOF_PENDING"
    assert decision.action_hint == "await_full_feed_proof"
    assert decision.should_attempt_recovery is False
    assert "WARMUP_INCOMPLETE" in decision.context["full_feed_proof_blockers"]


def test_feed_with_stale_underlying_does_not_unlock_healthy():
    decision = classify_feed_recovery_runtime(_payload(feed_ok=True, last_tick_age_sec=4.0))

    assert decision.recovery_state == "RECOVERY_PROOF_PENDING"
    assert decision.action_hint == "await_full_feed_proof"
    assert decision.should_attempt_recovery is False
    assert "UNDERLYING_TICK_STALE" in decision.context["full_feed_proof_blockers"]


def test_disconnected_websocket_is_full_recovery_candidate():
    decision = classify_feed_recovery_runtime(
        _payload(
            ws_connected=False,
            effective_ws_connected=False,
            state_machine={"state": "DOWN", "reason": "ws_disconnected"},
        )
    )

    assert decision.recovery_state == "WS_DISCONNECTED"
    assert decision.action_hint == "full_restart_candidate"
    assert decision.should_attempt_recovery is True
    assert decision.force_full_restart is True


def test_silent_feed_is_reconnect_candidate_without_full_restart_force():
    decision = classify_feed_recovery_runtime(
        _payload(
            feed_ok=False,
            state_machine={"state": "DOWN", "reason": "no_ws_messages"},
            last_tick_age_sec=12.0,
        )
    )

    assert decision.recovery_state == "SILENT_FEED"
    assert decision.action_hint == "silent_reconnect_candidate"
    assert decision.should_attempt_recovery is True
    assert decision.force_full_restart is False


def test_missing_option_subscriptions_are_option_recovery_candidate():
    decision = classify_feed_recovery_runtime(
        _payload(
            feed_ok=False,
            subscribed_option_tokens_count=0,
            missing_option_tokens_count=6,
        )
    )

    assert decision.recovery_state == "OPTION_SUBSCRIPTIONS_MISSING"
    assert decision.action_hint == "option_resubscribe_candidate"
    assert decision.should_attempt_recovery is True
    assert decision.context["missing_option_tokens_count"] == 6


def test_option_feed_blocker_is_preserved_in_reason_and_context():
    decision = classify_feed_recovery_runtime(
        _payload(option_feed_block_reason_by_symbol={"BANKNIFTY": "OPTION_TICKS_STALE"})
    )

    assert decision.recovery_state == "OPTION_FEED_BLOCKED"
    assert decision.reason == "option_ticks_stale"
    assert decision.context["primary_option_blocker"] == "OPTION_TICKS_STALE"


def test_invalid_payload_is_safe_unknown():
    decision = classify_feed_recovery_runtime(None)

    assert decision.recovery_state == "UNKNOWN"
    assert decision.action_hint == "inspect_runtime_payload"
    assert decision.should_attempt_recovery is False
