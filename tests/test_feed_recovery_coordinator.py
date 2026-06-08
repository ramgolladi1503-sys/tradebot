from core.feed_recovery_coordinator import FeedRecoveryCoordinator


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
    assert second.action == "TERMINAL"
    assert second.accepted is False
    assert second.state.process_restart_required is True
    assert second.state.terminal_failure is True
    assert second.state.recovery_in_progress is False
    assert "FEED_WS_1006_RECOVERY_ESCALATED" in second.events_emitted
    assert "FEED_WS_PROCESS_RESTART_REQUIRED" in second.events_emitted


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
    assert second.action == "BLOCKED"
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
