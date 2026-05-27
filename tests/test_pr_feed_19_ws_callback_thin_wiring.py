from core.feed.ws_callback_thin_wiring import (
    callback_state_from_runtime,
    handle_close_callback,
    handle_connected_callback,
    handle_error_callback,
    handle_subscribe_callback,
)


def test_callback_state_from_runtime_normalizes_runtime_facts():
    state = callback_state_from_runtime(
        phase=" connected ",
        ws_connected=True,
        market_open=True,
        stop_requested=False,
        auth_required=False,
        reconnect_pending=False,
        subscribed_token_count="3",
        intended_token_count="4",
        last_error="x" * 1005,
    )
    assert state.phase == "CONNECTED"
    assert state.ws_connected is True
    assert state.subscribed_token_count == 3
    assert state.intended_token_count == 4
    assert state.last_error == "x" * 1000


def test_connected_callback_maps_to_running_without_order_or_broker_flags():
    state = callback_state_from_runtime(phase="CONNECTING", ws_connected=False, market_open=True)
    result = handle_connected_callback(state=state, token_sample=[101, "102", 0, 101])
    payload = result.to_payload()

    assert result.transition.event == "CONNECTED"
    assert result.transition.next_phase == "CONNECTED"
    assert result.transition.should_mark_connected is True
    assert result.next_state.ws_connected is True
    assert result.runtime_state == "RUNNING"
    assert result.runtime_error == ""
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["evidence"]["token_sample"] == [101, 102]


def test_subscribe_callback_blocks_disconnected_and_allows_connected_tokens():
    disconnected = callback_state_from_runtime(phase="CONNECTED", ws_connected=False, market_open=True)
    blocked = handle_subscribe_callback(state=disconnected, requested_tokens=[101, 102])
    assert blocked.transition.next_phase == "DISCONNECTED"
    assert blocked.transition.reason == "ws_disconnected"
    assert blocked.runtime_state == "SUBSCRIBE_FAILED"
    assert blocked.snapshot_connected is False

    connected = callback_state_from_runtime(phase="CONNECTED", ws_connected=True, market_open=True)
    allowed = handle_subscribe_callback(state=connected, requested_tokens=[101, "102", 0, 101])
    assert allowed.transition.next_phase == "SUBSCRIBING"
    assert allowed.transition.should_subscribe is True
    assert allowed.runtime_state == "RUNNING"
    assert allowed.runtime_error == ""
    assert allowed.snapshot_connected is True


def test_error_callback_maps_auth_restart_and_record_only_paths():
    state = callback_state_from_runtime(phase="SUBSCRIBED", ws_connected=True, market_open=True)

    auth = handle_error_callback(state=state, reason="token expired", auth_error=True)
    assert auth.transition.next_phase == "AUTH_BLOCKED"
    assert auth.runtime_state == "AUTH_BLOCKED"
    assert auth.snapshot_connected is False
    assert auth.next_state.auth_required is True

    restart = handle_error_callback(state=state, reason="fatal websocket", restart_requested=True)
    assert restart.transition.next_phase == "RECOVERING"
    assert restart.transition.should_restart is True
    assert restart.runtime_state == "RECOVERING"
    assert restart.next_state.reconnect_pending is True

    record_only = handle_error_callback(state=state, reason="warning", restart_requested=False)
    assert record_only.transition.next_phase == "SUBSCRIBED"
    assert record_only.transition.action == "RECORD_ERROR"
    assert record_only.runtime_state == "SUBSCRIBE_FAILED"
    assert record_only.runtime_error == "warning"


def test_close_callback_maps_stop_restart_soft_and_plain_disconnect_paths():
    subscribed = callback_state_from_runtime(phase="SUBSCRIBED", ws_connected=True, market_open=True)

    stopped_state = callback_state_from_runtime(
        phase="SUBSCRIBED",
        ws_connected=True,
        market_open=True,
        stop_requested=True,
    )
    stopped = handle_close_callback(state=stopped_state, reason="manual stop")
    assert stopped.transition.next_phase == "STOPPED"
    assert stopped.runtime_state == "STOPPED"
    assert stopped.next_state.stop_requested is True

    restart = handle_close_callback(state=subscribed, reason="closed", restart_requested=True)
    assert restart.transition.next_phase == "RECOVERING"
    assert restart.transition.should_restart is True
    assert restart.runtime_state == "RECOVERING"
    assert restart.snapshot_connected is False

    soft = handle_close_callback(state=subscribed, reason="soft", soft_resubscribe_requested=True)
    assert soft.transition.next_phase == "CONNECTED"
    assert soft.transition.should_soft_resubscribe is True
    assert soft.runtime_state == "RUNNING"
    assert soft.snapshot_connected is True

    plain = handle_close_callback(state=subscribed, reason="closed")
    assert plain.transition.next_phase == "DISCONNECTED"
    assert plain.runtime_state == "SUBSCRIBE_FAILED"
    assert plain.snapshot_connected is False
