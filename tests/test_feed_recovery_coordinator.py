from core.feed_recovery_coordinator import FeedRecoveryCoordinator


class _Clock:
    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self.now = float(start)

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)

    def __call__(self) -> float:
        return float(self.now)


def _proof(now: float):
    return {
        "disconnect_started_at": now - 3.0,
        "reconnected_at": now - 2.0,
        "expected_tokens": ["NIFTY_CE", "NIFTY_PE"],
        "actual_tokens": ["NIFTY_PE", "NIFTY_CE"],
        "expected_token_count": 2,
        "actual_resubscribed_token_count": 2,
        "actual_subscription_evidence": "LOCAL_SUBSCRIBE_AND_MODE_CALL_RETURNED",
        "required_identity_tokens": ["NIFTY_CE"],
        "gap_duration_by_identity": {"NIFTY_CE": 1.0},
        "last_pre_disconnect_timestamp_by_required_identity": {
            "NIFTY_CE": now - 3.0,
        },
        "first_post_disconnect_timestamp_by_required_identity": {
            "NIFTY_CE": now - 2.0,
        },
        "state_rebuild_status": "REBUILT",
        "health_window_start": now - 2.0,
        "health_window_end": now,
        "health_window_status": "HEALTHY",
        "ws_connected": True,
        "runtime_state": "RUNNING",
        "required_feeds_fresh": True,
        "recovery_verdict": "RECOVERED",
    }


def test_plain_ws1006_peer_drop_is_recoverable_first():
    coord = FeedRecoveryCoordinator(
        max_recoverable_attempts_per_session=2,
        recoverable_retry_cooldown_sec=0.0,
    )

    result = coord.request_recovery(
        source="on_error",
        code=1006,
        reason="connection was closed uncleanly (peer dropped the TCP connection without previous WebSocket closing handshake)",
    )

    assert result.event == "FEED_RECOVERY_REQUESTED"
    assert result.accepted is True
    assert result.action == "SOFT_RECONNECT"
    assert result.events_emitted == [
        "FEED_RECOVERY_REQUESTED",
        "FEED_RECOVERY_ACCEPTED",
        "FEED_RECOVERY_ACTION_SELECTED",
        "FEED_WS_1006_RECOVERABLE",
        "FEED_WS_1006_RECOVERY_ATTEMPT",
    ]
    assert result.state.recovery_in_progress is True
    assert result.state.process_restart_required is False
    assert result.state.terminal_failure is False


def test_main_loop_terminated_is_terminal():
    coord = FeedRecoveryCoordinator(
        max_recoverable_attempts_per_session=2,
        recoverable_retry_cooldown_sec=0.0,
    )

    result = coord.request_recovery(
        source="on_error",
        code=1006,
        reason="main loop terminated after reactor shutdown",
    )

    assert result.action == "TERMINAL"
    assert result.accepted is False
    assert result.state.process_restart_required is True
    assert result.state.terminal_failure is True
    assert result.state.recovery_in_progress is False
    assert "FEED_WS_PROCESS_RESTART_REQUIRED" in result.events_emitted
    assert "FEED_WS_1006_RECOVERABLE" not in result.events_emitted


def test_recoverable_ws1006_escalates_after_attempts_exhausted():
    coord = FeedRecoveryCoordinator(
        max_recoverable_attempts_per_session=1,
        recoverable_retry_cooldown_sec=0.0,
    )

    first = coord.request_recovery(source="on_error", code=1006, reason="peer dropped")
    coord.clear_recovery(source="on_reconnect", reason="reconnect_verified", proof=_proof(coord._now_epoch()))
    second = coord.request_recovery(source="on_error", code=1006, reason="peer dropped again")

    assert first.action == "SOFT_RECONNECT"
    assert first.accepted is True
    assert second.action == "RECOVERY_BLOCKED"
    assert second.accepted is False
    assert second.state.process_restart_required is False
    assert second.state.terminal_failure is False
    assert second.state.recovery_in_progress is False
    assert "FEED_WS_1006_RECOVERY_ESCALATED" not in second.events_emitted


def test_recovery_request_is_blocked_when_already_in_progress():
    coord = FeedRecoveryCoordinator(
        max_recoverable_attempts_per_session=2,
        recoverable_retry_cooldown_sec=0.0,
    )

    first = coord.request_recovery(source="on_error", code=1006, reason="peer dropped")
    second = coord.request_recovery(source="on_close", code=1006, reason="peer dropped again")

    assert first.accepted is True
    assert first.state.recovery_in_progress is True
    assert second.event == "FEED_RECOVERY_ALREADY_IN_PROGRESS"
    assert second.accepted is False
    assert second.action == "RECOVERY_BLOCKED"
    assert second.events_emitted == ["FEED_RECOVERY_ALREADY_IN_PROGRESS"]
    assert second.state.recovery_in_progress is True


def test_terminal_fault_still_escalates_while_recovery_is_in_progress():
    coord = FeedRecoveryCoordinator(
        max_recoverable_attempts_per_session=2,
        recoverable_retry_cooldown_sec=0.0,
    )

    first = coord.request_recovery(source="on_error", code=1006, reason="peer dropped")
    second = coord.request_recovery(source="on_close", code=1006, reason="main loop terminated after reactor shutdown")

    assert first.accepted is True
    assert first.state.recovery_in_progress is True
    assert second.action == "TERMINAL"
    assert second.accepted is False
    assert second.state.process_restart_required is True
    assert second.state.terminal_failure is True
    assert second.state.recovery_in_progress is False


def test_ws1006_recovery_uses_real_clock_and_clears_on_success():
    clock = _Clock()
    coord = FeedRecoveryCoordinator(
        max_recoverable_attempts_per_session=2,
        recoverable_retry_cooldown_sec=0.0,
        recovery_timeout_sec=90.0,
        max_recoveries_per_window=3,
        recovery_window_sec=600.0,
        now_epoch_fn=clock,
    )

    result = coord.request_recovery(source="on_error", code=1006, reason="peer dropped")

    assert result.accepted is True
    assert result.action == "SOFT_RECONNECT"
    assert result.state.recovery_started_epoch == clock()
    assert result.state.last_recovery_action_epoch == clock()

    clock.advance(12.0)
    cleared = coord.clear_recovery(source="verify", reason="option_verification_ok", proof=_proof(clock()))

    assert cleared.recovery_in_progress is False
    assert cleared.recovery_timeout is False
    assert cleared.recovery_blocked is False
    assert cleared.process_restart_required is False
    assert cleared.last_recovery_action == "CLEARED"
    assert cleared.last_recovery_action_epoch == clock()


def test_recovery_times_out_after_timeout_window():
    clock = _Clock()
    coord = FeedRecoveryCoordinator(
        max_recoverable_attempts_per_session=2,
        recoverable_retry_cooldown_sec=0.0,
        recovery_timeout_sec=90.0,
        max_recoveries_per_window=3,
        recovery_window_sec=600.0,
        now_epoch_fn=clock,
    )

    first = coord.request_recovery(source="on_error", code=1006, reason="peer dropped")
    assert first.accepted is True
    clock.advance(91.0)

    second = coord.request_recovery(source="on_error", code=1006, reason="peer dropped again")

    assert second.action == "RECOVERY_TIMEOUT"
    assert second.accepted is False
    assert second.state.recovery_timeout is True
    assert second.state.recovery_blocked is True
    assert second.state.recovery_in_progress is False


def test_recovery_blocks_after_three_attempts_in_window():
    clock = _Clock()
    coord = FeedRecoveryCoordinator(
        max_recoverable_attempts_per_session=5,
        recoverable_retry_cooldown_sec=0.0,
        recovery_timeout_sec=90.0,
        max_recoveries_per_window=3,
        recovery_window_sec=600.0,
        now_epoch_fn=clock,
    )

    first = coord.request_recovery(source="on_error", code=1006, reason="peer dropped")
    coord.clear_recovery(source="verify", reason="verified", proof=_proof(clock()))
    clock.advance(1.0)
    second = coord.request_recovery(source="on_error", code=1006, reason="peer dropped")
    coord.clear_recovery(source="verify", reason="verified", proof=_proof(clock()))
    clock.advance(1.0)
    third = coord.request_recovery(source="on_error", code=1006, reason="peer dropped")

    assert first.action == "SOFT_RECONNECT"
    assert second.action == "SOFT_RECONNECT"
    assert third.action == "RECOVERY_BLOCKED"
    assert third.accepted is False
    assert third.state.recovery_blocked is True


def test_auth_failure_is_fail_closed_and_does_not_reconnect():
    clock = _Clock()
    coord = FeedRecoveryCoordinator(now_epoch_fn=clock)

    result = coord.request_recovery(source="on_error", code=401, reason="invalid auth token")

    assert result.action == "AUTH_REQUIRED"
    assert result.accepted is False
    assert result.state.auth_required is True
    assert result.state.recovery_in_progress is False
    assert result.state.process_restart_required is False


def test_terminal_reactor_failure_requires_restart():
    clock = _Clock()
    coord = FeedRecoveryCoordinator(now_epoch_fn=clock)

    result = coord.request_recovery(source="on_error", code=1006, reason="ReactorNotRestartable: reactor stopped")

    assert result.action == "TERMINAL"
    assert result.accepted is False
    assert result.state.process_restart_required is True
    assert result.state.terminal_failure is True
    assert result.state.recovery_blocked is True


def test_public_state_snapshot_is_immutable():
    import dataclasses
    import pytest
    coord = FeedRecoveryCoordinator()
    
    snapshot = coord.get_state_snapshot()
    
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.recovery_in_progress = True
        
    assert coord.get_state_snapshot().recovery_in_progress is False


def test_recovery_clear_without_causal_proof_stays_blocked_and_retains_incident():
    clock = _Clock()
    coord = FeedRecoveryCoordinator(now_epoch_fn=clock)
    coord.request_recovery(source="on_error", code=1006, reason="peer dropped")
    before = coord.get_state_snapshot()

    after = coord.clear_recovery(source="ticks", reason="ticks resumed")

    assert after.recovery_in_progress is before.recovery_in_progress is True
    assert coord.incident_history[-1]["event"] == "RECOVERY_CLEAR_REJECTED"
    assert "recovery_proof_missing" in coord.incident_history[-1]["failures"]
    assert coord.incident_history[-1]["broker_api_called"] is False


def test_recovery_clear_rejects_missing_extra_tokens_gap_and_unbuilt_state():
    clock = _Clock()
    coord = FeedRecoveryCoordinator(now_epoch_fn=clock, max_recovery_gap_sec=2.0)
    coord.request_recovery(source="on_error", code=1006, reason="peer dropped")
    bad = _proof(clock())
    bad["actual_tokens"] = ["NIFTY_CE", "EXTRA"]
    bad["gap_duration_by_identity"]["NIFTY_CE"] = 20.0
    bad["state_rebuild_status"] = "UNKNOWN"

    result = coord.clear_recovery(source="test", reason="partial", proof=bad)

    assert result.recovery_in_progress is True
    failures = coord.incident_history[-1]["failures"]
    assert "required_token_set_mismatch" in failures
    assert "required_identity_gap_invalid:NIFTY_CE" in failures
    assert "state_rebuild_unproven" in failures


def test_complete_recovery_proof_clears_and_records_resolution():
    clock = _Clock()
    coord = FeedRecoveryCoordinator(now_epoch_fn=clock)
    coord.request_recovery(source="on_error", code=1006, reason="peer dropped")

    result = coord.clear_recovery(source="verified", reason="causal proof", proof=_proof(clock()))

    assert result.recovery_in_progress is False
    assert result.last_recovery_action == "CLEARED"
    assert coord.incident_history[-1]["event"] == "RECOVERY_RESOLVED"


def test_recovery_proof_rejects_nan_and_infinite_timestamps_or_gaps():
    import math

    clock = _Clock()
    coord = FeedRecoveryCoordinator(now_epoch_fn=clock, max_recovery_gap_sec=2.0)
    coord.request_recovery(source="on_error", code=1006, reason="peer dropped")
    proof = _proof(clock())
    proof["disconnect_started_at"] = math.nan
    proof["gap_duration_by_identity"]["NIFTY_CE"] = math.nan
    proof["first_post_disconnect_timestamp_by_required_identity"]["NIFTY_CE"] = math.inf

    result = coord.clear_recovery(source="test", reason="non-finite evidence", proof=proof)

    assert result.recovery_in_progress is True
    failures = coord.incident_history[-1]["failures"]
    assert "recovery_timestamps_invalid" in failures
    assert "required_identity_gap_invalid:NIFTY_CE" in failures


def test_recovery_proof_requires_explicit_healthy_window_and_recovered_verdict():
    clock = _Clock()
    coord = FeedRecoveryCoordinator(now_epoch_fn=clock)
    coord.request_recovery(source="on_error", code=1006, reason="peer dropped")
    proof = _proof(clock())
    proof["health_window_status"] = "UNKNOWN"
    proof["required_feeds_fresh"] = False
    proof["recovery_verdict"] = "UNKNOWN"

    result = coord.clear_recovery(source="test", reason="unproven health", proof=proof)

    assert result.recovery_in_progress is True
    failures = coord.incident_history[-1]["failures"]
    assert "health_window_not_healthy" in failures
    assert "health_window_required_feeds_not_fresh" in failures
    assert "recovery_verdict_unproven" in failures


def test_recovery_proof_rejects_short_healthy_window_and_unproven_subscription_apply():
    clock = _Clock()
    coord = FeedRecoveryCoordinator(now_epoch_fn=clock)
    coord.request_recovery(source="on_error", code=1006, reason="peer dropped")
    proof = _proof(clock())
    proof["health_window_start"] = clock() - 1.0
    proof.pop("actual_subscription_evidence")

    result = coord.clear_recovery(source="test", reason="short or unproven", proof=proof)

    assert result.recovery_in_progress is True
    failures = coord.incident_history[-1]["failures"]
    assert "health_window_unproven" in failures
    assert "actual_subscription_evidence_unproven" in failures


def test_recovery_history_defensively_copies_nested_proof_on_ingress_and_egress():
    clock = _Clock()
    coord = FeedRecoveryCoordinator(now_epoch_fn=clock)
    coord.request_recovery(source="on_error", code=1006, reason="peer dropped")
    proof = _proof(clock())
    original_gap = proof["gap_duration_by_identity"]["NIFTY_CE"]

    coord.clear_recovery(source="verified", reason="causal proof", proof=proof)
    proof["gap_duration_by_identity"]["NIFTY_CE"] = 99_999.0
    proof["expected_tokens"].append("INJECTED_AFTER_CLEAR")

    history_snapshot = coord.incident_history
    recorded_proof = history_snapshot[-1]["proof"]
    assert recorded_proof["gap_duration_by_identity"]["NIFTY_CE"] == original_gap
    assert "INJECTED_AFTER_CLEAR" not in recorded_proof["expected_tokens"]

    recorded_proof["gap_duration_by_identity"]["NIFTY_CE"] = -1.0
    recorded_proof["expected_tokens"].clear()
    next_snapshot = coord.incident_history[-1]["proof"]
    assert next_snapshot["gap_duration_by_identity"]["NIFTY_CE"] == original_gap
    assert next_snapshot["expected_tokens"] == ["NIFTY_CE", "NIFTY_PE"]
