from core.feed_supervisor import build_feed_supervisor_snapshot


def test_supervisor_booting_and_connecting_states_are_read_only():
    booting = build_feed_supervisor_snapshot({"runtime_state": "BOOTING"})
    connecting = build_feed_supervisor_snapshot({"runtime_state": "CONNECTING", "ws_connected": True})

    assert booting.state == "BOOTING"
    assert booting.read_only is True
    assert booting.append is False
    assert booting.is_order_action is False
    assert booting.broker_api_called is False
    assert booting.allowed_for_live_execution is False
    assert connecting.state == "CONNECTING"


def test_supervisor_transitions_through_connected_subscribing_and_verifying():
    connected = build_feed_supervisor_snapshot({
        "runtime_state": "CONNECTED",
        "ws_connected": True,
        "auth_ready": True,
        "subscribed_tokens_count": 0,
    })
    subscribing = build_feed_supervisor_snapshot({
        "runtime_state": "SUBSCRIBING",
        "ws_connected": True,
        "auth_ready": True,
        "subscribed_tokens_count": 0,
    })
    verifying = build_feed_supervisor_snapshot({
        "runtime_state": "VERIFYING_OPTION_TICKS",
        "ws_connected": True,
        "auth_ready": True,
        "subscribed_tokens_count": 4,
        "verified_option_symbols": ["nifty"],
        "missing_option_symbols": ["banknifty"],
    })

    assert connected.state == "CONNECTED"
    assert subscribing.state == "SUBSCRIBING"
    assert verifying.state == "VERIFYING"
    assert verifying.blockers == ("OPTION_TICKS_UNVERIFIED", "UNDERLYING_TICK_STALE", "DEPTH_STALE")


def test_supervisor_uses_freshness_to_promote_candidate_ready():
    snapshot = build_feed_supervisor_snapshot({
        "runtime_state": "SUBSCRIBED",
        "ws_connected": True,
        "auth_ready": True,
        "subscribed_tokens_count": 8,
        "subscribed_option_tokens_count": 12,
        "verified_option_symbols": ["BANKNIFTY", "NIFTY"],
        "missing_option_symbols": [],
        "option_ticks_verified": True,
        "underlying_tick_fresh": True,
        "depth_fresh": True,
        "warmup_clean_cycles": 3,
    })

    payload = snapshot.to_payload()

    assert snapshot.state == "CANDIDATE_READY"
    assert snapshot.blockers == ()
    assert payload["state"] == "CANDIDATE_READY"
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["allowed_for_live_execution"] is False


def test_supervisor_requires_full_feed_proof_after_reconnect():
    warming = build_feed_supervisor_snapshot({
        "runtime_state": "RUNNING",
        "ws_connected": True,
        "auth_ready": True,
        "subscribed_tokens_count": 8,
        "subscribed_option_tokens_count": 12,
        "verified_option_symbols": ["BANKNIFTY", "NIFTY"],
        "missing_option_symbols": [],
        "option_ticks_verified": True,
        "underlying_tick_fresh": True,
        "depth_fresh": True,
        "warmup_clean_cycles": 1,
        "warmup_required_clean_cycles": 3,
        "recovery_generation_id": 5,
        "last_recovery_generation_id": 4,
        "subscription_generation_id": 11,
        "last_subscription_generation_id": 10,
    })
    ready = build_feed_supervisor_snapshot({
        "runtime_state": "RUNNING",
        "ws_connected": True,
        "auth_ready": True,
        "subscribed_tokens_count": 8,
        "subscribed_option_tokens_count": 12,
        "verified_option_symbols": ["BANKNIFTY", "NIFTY"],
        "missing_option_symbols": [],
        "option_ticks_verified": True,
        "underlying_tick_fresh": True,
        "depth_fresh": True,
        "warmup_clean_cycles": 3,
        "warmup_required_clean_cycles": 3,
        "recovery_generation_id": 5,
        "last_recovery_generation_id": 5,
        "subscription_generation_id": 11,
        "last_subscription_generation_id": 11,
    })

    assert warming.state == "WARMING_UP"
    assert "WARMUP_INCOMPLETE" not in warming.blockers
    assert "RECOVERY_GENERATION_CHANGED" not in warming.blockers
    assert "SUBSCRIPTION_GENERATION_CHANGED" not in warming.blockers
    assert ready.state == "CANDIDATE_READY"
    assert ready.blockers == ()


def test_supervisor_marks_warming_up_before_candidate_readiness():
    snapshot = build_feed_supervisor_snapshot({
        "runtime_state": "SUBSCRIBED",
        "ws_connected": True,
        "auth_ready": True,
        "subscribed_tokens_count": 8,
        "subscribed_option_tokens_count": 12,
        "verified_option_symbols": ["NIFTY"],
        "missing_option_symbols": [],
        "option_ticks_verified": True,
        "underlying_tick_fresh": False,
        "depth_fresh": True,
        "warmup_clean_cycles": 1,
    })

    assert snapshot.state == "WARMING_UP"
    assert "UNDERLYING_TICK_STALE" in snapshot.blockers


def test_supervisor_handles_recovery_blocked_restart_required_auth_required_and_shutdown():
    recovery_blocked = build_feed_supervisor_snapshot({
        "runtime_state": "RECOVERY_BLOCKED",
        "recovery_blocked": True,
        "ws_connected": False,
    })
    restart_required = build_feed_supervisor_snapshot({
        "runtime_state": "WS1006_PROCESS_RESTART_REQUIRED",
        "process_restart_required": True,
        "ws_connected": False,
    })
    auth_required = build_feed_supervisor_snapshot({
        "runtime_state": "AUTH_REQUIRED",
        "auth_required": True,
        "ws_connected": False,
    })
    shutdown = build_feed_supervisor_snapshot({"runtime_state": "STOPPED"})

    assert recovery_blocked.state == "RECOVERY_BLOCKED"
    assert restart_required.state == "RESTART_REQUIRED"
    assert auth_required.state == "AUTH_REQUIRED"
    assert shutdown.state == "SHUTDOWN"


def test_supervisor_snapshot_payload_is_deterministic_and_serializable():
    snapshot = build_feed_supervisor_snapshot({
        "runtime_state": "SUBSCRIBED",
        "ws_connected": True,
        "auth_ready": True,
        "subscribed_tokens_count": 1,
        "subscribed_option_tokens_count": 2,
        "verified_option_symbols": ["nifty", "banknifty"],
        "missing_option_symbols": [],
        "option_ticks_verified": True,
        "underlying_tick_fresh": True,
        "depth_fresh": True,
    })

    payload = snapshot.to_payload()

    assert payload["verified_option_symbols"] == ["BANKNIFTY", "NIFTY"]
    assert payload["missing_option_symbols"] == []
    assert payload["runtime_state"] == "SUBSCRIBED"
