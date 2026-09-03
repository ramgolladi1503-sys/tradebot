from core.feed.ws_lifecycle_shell import (
    apply_transition,
    build_lifecycle_evidence,
    build_lifecycle_state,
    derive_phase_from_runtime,
    is_active_phase,
    is_terminal_stop_phase,
    normalize_action,
    normalize_event,
    normalize_phase,
    normalize_token_sample,
    positive_count,
    transition_for_connect_request,
    transition_for_connected,
    transition_for_disconnect,
    transition_for_error,
    transition_for_stop_request,
    transition_for_subscribe_request,
    transition_for_subscribed,
)


def test_normalizers_and_phase_helpers_are_deterministic():
    assert normalize_phase(" connected ") == "CONNECTED"
    assert normalize_phase("") == "UNKNOWN"
    assert normalize_event(" disconnect ") == "DISCONNECT"
    assert normalize_action(" subscribe ") == "SUBSCRIBE"
    assert positive_count("3") == 3
    assert positive_count("bad") == 0
    assert normalize_token_sample(["5", 3, 5, 0, None, "bad", 7], limit=3) == (5, 3, 7)
    assert is_terminal_stop_phase("stopped") is True
    assert is_terminal_stop_phase("connected") is False
    assert is_active_phase("subscribed") is True
    assert is_active_phase("market_closed") is False


def test_derive_phase_from_runtime_classifies_safe_states():
    assert derive_phase_from_runtime(
        market_open=True,
        auth_required=True,
        stop_requested=False,
        ws_connected=True,
    ) == "AUTH_BLOCKED"
    assert derive_phase_from_runtime(
        market_open=True,
        auth_required=False,
        stop_requested=True,
        ws_connected=True,
    ) == "STOPPING"
    assert derive_phase_from_runtime(
        market_open=True,
        auth_required=False,
        stop_requested=True,
        ws_connected=False,
    ) == "STOPPED"
    assert derive_phase_from_runtime(
        market_open=False,
        premarket=True,
        auth_required=False,
        stop_requested=False,
        ws_connected=False,
    ) == "PREMARKET"
    assert derive_phase_from_runtime(
        market_open=False,
        auth_required=False,
        stop_requested=False,
        ws_connected=True,
    ) == "MARKET_CLOSED"
    assert derive_phase_from_runtime(
        market_open=True,
        auth_required=False,
        stop_requested=False,
        ws_connected=True,
        subscribed_token_count=4,
        intended_token_count=4,
    ) == "SUBSCRIBED"
    assert derive_phase_from_runtime(
        market_open=True,
        auth_required=False,
        stop_requested=False,
        ws_connected=False,
    ) == "DISCONNECTED"


def test_connect_request_blocks_auth_stop_and_market_closed_before_connecting():
    auth_state = build_lifecycle_state(phase="STARTING", ws_connected=False, market_open=True, auth_required=True)
    assert transition_for_connect_request(auth_state).to_payload() == {
        "event": "CONNECT_REQUEST",
        "previous_phase": "STARTING",
        "next_phase": "AUTH_BLOCKED",
        "action": "BLOCK",
        "reason": "auth_required",
        "should_connect": False,
        "should_subscribe": False,
        "should_soft_resubscribe": False,
        "should_restart": False,
        "should_stop": False,
        "should_mark_connected": False,
        "should_mark_disconnected": False,
        "should_record_error": True,
        "is_order_action": False,
        "broker_api_called": False,
    }
    stopped = build_lifecycle_state(phase="STARTING", ws_connected=False, market_open=True, stop_requested=True)
    assert transition_for_connect_request(stopped).reason == "stop_requested"
    closed = build_lifecycle_state(phase="STARTING", ws_connected=False, market_open=False)
    assert transition_for_connect_request(closed).next_phase == "MARKET_CLOSED"
    premarket = build_lifecycle_state(phase="PREMARKET", ws_connected=False, market_open=False, premarket=True)
    premarket_decision = transition_for_connect_request(premarket)
    assert premarket_decision.reason == "premarket_observation_allowed"
    assert premarket_decision.should_connect is True
    assert premarket_decision.to_payload()["is_order_action"] is False
    allowed = build_lifecycle_state(phase="STARTING", ws_connected=False, market_open=True)
    decision = transition_for_connect_request(allowed)
    assert decision.next_phase == "CONNECTING"
    assert decision.should_connect is True


def test_connected_and_subscribe_transitions_preserve_fail_closed_boundaries():
    connected_state = build_lifecycle_state(phase="CONNECTING", ws_connected=False, market_open=True)
    connected = transition_for_connected(connected_state)
    assert connected.next_phase == "CONNECTED"
    assert connected.should_mark_connected is True

    disconnected = build_lifecycle_state(phase="CONNECTED", ws_connected=False, market_open=True)
    blocked = transition_for_subscribe_request(disconnected, requested_tokens=[101, 102])
    assert blocked.next_phase == "DISCONNECTED"
    assert blocked.reason == "ws_disconnected"
    assert blocked.should_subscribe is False

    connected = build_lifecycle_state(phase="CONNECTED", ws_connected=True, market_open=True)
    no_tokens = transition_for_subscribe_request(connected, requested_tokens=[])
    assert no_tokens.reason == "no_tokens"
    assert no_tokens.should_subscribe is False
    subscribe = transition_for_subscribe_request(connected, requested_tokens=[101, "102", 0, 101])
    assert subscribe.next_phase == "SUBSCRIBING"
    assert subscribe.should_subscribe is True

    no_confirm = transition_for_subscribed(connected, subscribed_token_count=0)
    assert no_confirm.next_phase == "CONNECTED"
    assert no_confirm.reason == "no_subscribed_tokens"
    confirmed = transition_for_subscribed(connected, subscribed_token_count=2)
    assert confirmed.next_phase == "SUBSCRIBED"
    assert confirmed.action == "MARK_SUBSCRIBED"


def test_disconnect_and_error_transitions_distinguish_restart_soft_and_record_paths():
    state = build_lifecycle_state(phase="SUBSCRIBED", ws_connected=True, market_open=True)
    restart = transition_for_disconnect(state, reason="closed", restart_requested=True)
    assert restart.next_phase == "RECOVERING"
    assert restart.should_restart is True
    assert restart.should_mark_disconnected is True

    soft = transition_for_disconnect(state, reason="refresh", soft_resubscribe_requested=True)
    assert soft.next_phase == "CONNECTED"
    assert soft.should_soft_resubscribe is True

    plain = transition_for_disconnect(state, reason="closed")
    assert plain.next_phase == "DISCONNECTED"
    assert plain.should_mark_disconnected is True

    auth = transition_for_error(state, reason="token expired", auth_error=True)
    assert auth.next_phase == "AUTH_BLOCKED"
    assert auth.should_record_error is True
    error_restart = transition_for_error(state, reason="fatal", restart_requested=True)
    assert error_restart.next_phase == "RECOVERING"
    assert error_restart.should_restart is True
    record_only = transition_for_error(state, reason="warning", restart_requested=False)
    assert record_only.next_phase == "SUBSCRIBED"
    assert record_only.action == "RECORD_ERROR"


def test_apply_transition_updates_read_only_state_without_runtime_side_effect_flags():
    state = build_lifecycle_state(
        phase="CONNECTING",
        ws_connected=False,
        market_open=True,
        subscribed_token_count=0,
        intended_token_count=2,
    )
    connected = apply_transition(state, transition_for_connected(state))
    assert connected.phase == "CONNECTED"
    assert connected.ws_connected is True
    assert connected.reconnect_pending is False

    restarting = apply_transition(connected, transition_for_disconnect(connected, reason="closed", restart_requested=True))
    assert restarting.phase == "RECOVERING"
    assert restarting.ws_connected is False
    assert restarting.reconnect_pending is True

    stopped = apply_transition(restarting, transition_for_stop_request(restarting))
    assert stopped.phase == "STOPPING"
    assert stopped.stop_requested is True
    assert stopped.reconnect_pending is False


def test_lifecycle_evidence_contains_safety_flags_and_normalized_token_sample():
    state = build_lifecycle_state(phase="CONNECTED", ws_connected=True, market_open=True)
    transition = transition_for_subscribe_request(state, requested_tokens=[101, 102])
    evidence = build_lifecycle_evidence(state=state, transition=transition, token_sample=[101, "102", 0, 101])
    assert evidence["state"]["phase"] == "CONNECTED"
    assert evidence["transition"]["action"] == "SUBSCRIBE"
    assert evidence["transition"]["is_order_action"] is False
    assert evidence["transition"]["broker_api_called"] is False
    assert evidence["token_sample"] == [101, 102]
    assert evidence["is_order_action"] is False
    assert evidence["broker_api_called"] is False
