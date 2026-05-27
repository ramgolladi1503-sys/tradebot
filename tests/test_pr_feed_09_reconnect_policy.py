from core.feed.reconnect_policy import (
    evaluate_soft_resubscribe_policy,
    evaluate_watchdog_stale_tick_policy,
    evaluate_ws_close_reconnect_policy,
    evaluate_ws_error_reconnect_policy,
    is_fatal_ws_fault,
    is_opening_handshake_error,
    normalize_ws_code,
    should_ignore_restart_cooldown_for_ws_fault,
)


def test_ws_fault_classifiers_are_deterministic():
    assert normalize_ws_code("1006") == 1006
    assert normalize_ws_code("bad") is None
    assert is_fatal_ws_fault(1006, "abnormal closure") is True
    assert is_fatal_ws_fault(2000, "connection closed by peer") is True
    assert is_fatal_ws_fault(2000, "temporary warning") is False
    assert is_opening_handshake_error(1006, "Error during opening handshake") is True
    assert is_opening_handshake_error(1011, "Error during opening handshake") is False
    assert should_ignore_restart_cooldown_for_ws_fault(code=1006, reason_text="anything") is True
    assert should_ignore_restart_cooldown_for_ws_fault(code=2000, reason_text="connection lost") is True
    assert should_ignore_restart_cooldown_for_ws_fault(code=2000, reason_text="minor") is False


def test_soft_resubscribe_policy_fail_closed_and_allows_fresh_connected_ws():
    assert evaluate_soft_resubscribe_policy(
        reason="manual hard block",
        ws_connected=True,
        last_ws_tick_epoch=100.0,
        now_epoch=101.0,
        hard_block_markers=("hard",),
    ).to_payload() == {
        "action": "SKIP",
        "reason": "hard_reason_marker:hard",
        "should_restart": False,
        "should_soft_resubscribe": False,
        "should_suppress_restart": False,
        "ignore_cooldown": False,
        "force_full_restart": False,
    }
    assert evaluate_soft_resubscribe_policy(
        reason="close",
        ws_connected=False,
        last_ws_tick_epoch=100.0,
        now_epoch=101.0,
    ).reason == "ws_disconnected"
    assert evaluate_soft_resubscribe_policy(
        reason="close",
        ws_connected=True,
        last_ws_tick_epoch=0.0,
        now_epoch=101.0,
    ).reason == "no_recent_ws_tick"
    stale = evaluate_soft_resubscribe_policy(
        reason="close",
        ws_connected=True,
        last_ws_tick_epoch=90.0,
        now_epoch=101.0,
        max_tick_age_sec=2.0,
    )
    assert stale.action == "SKIP"
    assert stale.reason.startswith("ws_tick_stale:")
    decision = evaluate_soft_resubscribe_policy(
        reason="close",
        ws_connected=True,
        last_ws_tick_epoch=100.0,
        now_epoch=101.0,
        max_tick_age_sec=2.0,
    )
    assert decision.action == "SOFT_RESUBSCRIBE"
    assert decision.should_soft_resubscribe is True


def test_watchdog_policy_tracks_stale_strikes_and_restart_threshold():
    closed = evaluate_watchdog_stale_tick_policy(
        market_open=False,
        db_tick_age_sec=99.0,
        ws_tick_age_sec=None,
        previous_stale_strikes=4,
        stale_restart_sec=5.0,
    )
    assert closed.action == "RESET_STALE"
    assert closed.stale_strikes == 0

    ws_ok = evaluate_watchdog_stale_tick_policy(
        market_open=True,
        db_tick_age_sec=99.0,
        ws_tick_age_sec=1.0,
        previous_stale_strikes=4,
        stale_restart_sec=5.0,
    )
    assert ws_ok.reason == "ws_ticks_flowing"
    assert ws_ok.stale_strikes == 0

    marked = evaluate_watchdog_stale_tick_policy(
        market_open=True,
        db_tick_age_sec=10.0,
        ws_tick_age_sec=None,
        previous_stale_strikes=0,
        stale_restart_sec=5.0,
        strikes_to_restart=2,
    )
    assert marked.action == "MARK_STALE"
    assert marked.stale_strikes == 1
    assert marked.should_restart is False

    restart = evaluate_watchdog_stale_tick_policy(
        market_open=True,
        db_tick_age_sec=10.0,
        ws_tick_age_sec=None,
        previous_stale_strikes=1,
        stale_restart_sec=5.0,
        strikes_to_restart=2,
    )
    assert restart.action == "RESTART"
    assert restart.should_restart is True
    assert restart.stale_strikes == 2

    recovered = evaluate_watchdog_stale_tick_policy(
        market_open=True,
        db_tick_age_sec=1.0,
        ws_tick_age_sec=None,
        previous_stale_strikes=2,
        stale_restart_sec=5.0,
    )
    assert recovered.reason == "db_ticks_recovered"
    assert recovered.stale_strikes == 0


def test_ws_error_policy_blocks_auth_and_handles_handshake_before_restart():
    auth = evaluate_ws_error_reconnect_policy(
        code=403,
        reason_text="token expired",
        is_auth_error=True,
        market_open=True,
        stop_requested=False,
        watchdog_stop_set=False,
        use_internal_reconnect=True,
        handshake_soft_reset_used=False,
    )
    assert auth.action == "AUTH_BLOCKED"
    assert auth.should_suppress_restart is True

    first_handshake = evaluate_ws_error_reconnect_policy(
        code=1006,
        reason_text="error during opening handshake",
        is_auth_error=False,
        market_open=True,
        stop_requested=False,
        watchdog_stop_set=False,
        use_internal_reconnect=True,
        handshake_soft_reset_used=False,
    )
    assert first_handshake.action == "HANDSHAKE_SOFT_RESET"
    assert first_handshake.should_soft_resubscribe is True
    assert first_handshake.should_suppress_restart is True

    second_handshake = evaluate_ws_error_reconnect_policy(
        code=1006,
        reason_text="error during opening handshake",
        is_auth_error=False,
        market_open=True,
        stop_requested=False,
        watchdog_stop_set=False,
        use_internal_reconnect=True,
        handshake_soft_reset_used=True,
    )
    assert second_handshake.action == "SUPPRESS_RESTART"

    stopped = evaluate_ws_error_reconnect_policy(
        code=1006,
        reason_text="abnormal closure",
        is_auth_error=False,
        market_open=True,
        stop_requested=True,
        watchdog_stop_set=False,
        use_internal_reconnect=True,
        handshake_soft_reset_used=True,
    )
    assert stopped.reason == "stop_requested"
    assert stopped.should_restart is False

    internal = evaluate_ws_error_reconnect_policy(
        code=1011,
        reason_text="server closed connection",
        is_auth_error=False,
        market_open=True,
        stop_requested=False,
        watchdog_stop_set=False,
        use_internal_reconnect=True,
        handshake_soft_reset_used=True,
    )
    assert internal.action == "SCHEDULE_FULL_RESTART"
    assert internal.should_restart is True
    assert internal.force_full_restart is True
    assert internal.ignore_cooldown is True

    external = evaluate_ws_error_reconnect_policy(
        code=1012,
        reason_text="service restart",
        is_auth_error=False,
        market_open=True,
        stop_requested=False,
        watchdog_stop_set=False,
        use_internal_reconnect=False,
        handshake_soft_reset_used=True,
    )
    assert external.action == "RESTART"
    assert external.should_restart is True
    assert external.force_full_restart is False


def test_ws_close_policy_distinguishes_auth_stop_soft_and_full_restart():
    auth = evaluate_ws_close_reconnect_policy(
        code=1006,
        reason_text="closed",
        auth_required_latch=True,
        stop_requested=False,
        watchdog_stop_set=False,
        market_open=True,
        use_internal_reconnect=True,
    )
    assert auth.action == "AUTH_BLOCKED"
    assert auth.should_suppress_restart is True

    stopped = evaluate_ws_close_reconnect_policy(
        code=1006,
        reason_text="closed",
        auth_required_latch=False,
        stop_requested=True,
        watchdog_stop_set=False,
        market_open=True,
        use_internal_reconnect=True,
    )
    assert stopped.action == "STOPPED"
    assert stopped.should_suppress_restart is True

    soft = evaluate_ws_close_reconnect_policy(
        code=1000,
        reason_text="normal close",
        auth_required_latch=False,
        stop_requested=False,
        watchdog_stop_set=False,
        market_open=True,
        use_internal_reconnect=True,
    )
    assert soft.action == "SOFT_RESUBSCRIBE"
    assert soft.should_soft_resubscribe is True

    full = evaluate_ws_close_reconnect_policy(
        code=1006,
        reason_text="connection closed by peer",
        auth_required_latch=False,
        stop_requested=False,
        watchdog_stop_set=False,
        market_open=True,
        use_internal_reconnect=True,
    )
    assert full.action == "SCHEDULE_FULL_RESTART"
    assert full.should_restart is True
    assert full.force_full_restart is True

    external = evaluate_ws_close_reconnect_policy(
        code=1000,
        reason_text="normal close",
        auth_required_latch=False,
        stop_requested=False,
        watchdog_stop_set=False,
        market_open=True,
        use_internal_reconnect=False,
    )
    assert external.action == "RESTART"
    assert external.should_restart is True
