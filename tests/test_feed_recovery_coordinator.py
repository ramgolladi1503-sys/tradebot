from core.feed_recovery_coordinator import FeedRecoveryCoordinator


class _Clock:
    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self.now = float(start)

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)

    def __call__(self) -> float:
        return float(self.now)


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
    coord.clear_recovery(source="on_reconnect", reason="reconnect_verified")
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
    cleared = coord.clear_recovery(source="verify", reason="option_verification_ok")

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
    coord.clear_recovery(source="verify", reason="verified")
    clock.advance(1.0)
    second = coord.request_recovery(source="on_error", code=1006, reason="peer dropped")
    coord.clear_recovery(source="verify", reason="verified")
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
