from core.feed_supervisor import build_feed_supervisor_snapshot


def _base_payload():
    return {
        "runtime_state": "SUBSCRIBED",
        "ws_connected": True,
        "auth_ready": True,
        "subscribed_tokens_count": 8,
        "subscribed_option_tokens_count": 12,
        "verified_option_symbols": ["NIFTY", "BANKNIFTY"],
        "missing_option_symbols": [],
        "option_ticks_verified": True,
        "underlying_tick_fresh": True,
        "depth_fresh": True,
        "warmup_required_clean_cycles": 3,
        "recovery_generation_id": 1,
        "last_recovery_generation_id": 1,
        "subscription_generation_id": 4,
        "last_subscription_generation_id": 4,
    }


def test_reconnect_enters_warming_up_not_candidate_ready():
    payload = _base_payload()
    payload.update({"warmup_clean_cycles": 0, "runtime_state": "RECONNECTING", "recovery_in_progress": True})
    snapshot = build_feed_supervisor_snapshot(payload)

    assert snapshot.state == "RECOVERING"
    assert snapshot.is_order_action is False
    assert snapshot.read_only is True


def test_one_clean_cycle_is_insufficient():
    payload = _base_payload()
    payload.update({"warmup_clean_cycles": 1})
    snapshot = build_feed_supervisor_snapshot(payload)

    assert snapshot.state == "WARMING_UP"
    assert snapshot.blockers == ()


def test_required_clean_cycles_unlock_candidate_ready():
    payload = _base_payload()
    payload.update({"warmup_clean_cycles": 3})
    snapshot = build_feed_supervisor_snapshot(payload)

    assert snapshot.state == "CANDIDATE_READY"
    assert snapshot.blockers == ()
    assert snapshot.to_payload()["is_order_action"] is False


def test_stale_option_tick_resets_warmup():
    payload = _base_payload()
    payload.update({"warmup_clean_cycles": 3, "option_ticks_verified": False})
    snapshot = build_feed_supervisor_snapshot(payload)

    assert snapshot.state == "VERIFYING"
    assert "OPTION_TICKS_UNVERIFIED" in snapshot.blockers


def test_stale_depth_resets_warmup():
    payload = _base_payload()
    payload.update({"warmup_clean_cycles": 3, "depth_fresh": False})
    snapshot = build_feed_supervisor_snapshot(payload)

    assert snapshot.state == "WARMING_UP"
    assert "DEPTH_STALE" in snapshot.blockers


def test_recovery_during_warmup_resets_quarantine():
    payload = _base_payload()
    payload.update({"warmup_clean_cycles": 2, "recovery_in_progress": True, "runtime_state": "RECOVERING"})
    snapshot = build_feed_supervisor_snapshot(payload)

    assert snapshot.state == "RECOVERING"
    assert "RECOVERING" in snapshot.blockers


def test_legacy_recovery_generation_change_is_diagnostic_only():
    payload = _base_payload()
    payload.update({
        "warmup_clean_cycles": 3,
        "recovery_generation_id": 3,
        "last_recovery_generation_id": 2,
    })
    snapshot = build_feed_supervisor_snapshot(payload)

    assert snapshot.state == "CANDIDATE_READY"
    assert "RECOVERY_GENERATION_CHANGED" not in snapshot.blockers


def test_auth_required_blocks_immediately():
    payload = _base_payload()
    payload.update({"auth_required": True, "warmup_clean_cycles": 3, "runtime_state": "AUTH_REQUIRED"})
    snapshot = build_feed_supervisor_snapshot(payload)

    assert snapshot.state == "AUTH_REQUIRED"
    assert "AUTH_REQUIRED" in snapshot.blockers


def test_restart_required_blocks_immediately():
    payload = _base_payload()
    payload.update({"process_restart_required": True, "warmup_clean_cycles": 3, "runtime_state": "WS1006_PROCESS_RESTART_REQUIRED"})
    snapshot = build_feed_supervisor_snapshot(payload)

    assert snapshot.state == "RESTART_REQUIRED"
    assert "RESTART_REQUIRED" in snapshot.blockers


def test_dead_feed_blocks_candidate_readiness_and_resets_warmup():
    payload = _base_payload()
    payload.update({
        "runtime_state": "RUNNING",
        "feed_truth_state": "DEAD",
        "feed_truth_reason_code": "feed_unhealthy",
        "option_feed_block_reason": "NO_LIVE_OPTION_FEED",
        "warmup_clean_cycles": 3,
    })
    snapshot = build_feed_supervisor_snapshot(payload)

    assert snapshot.state == "WARMING_UP"
    assert "DEAD" in snapshot.blockers
    assert "NO_LIVE_OPTION_FEED" in snapshot.blockers


def test_restart_failure_reason_is_preserved_on_snapshot():
    payload = _base_payload()
    payload.update({
        "process_restart_required": True,
        "restart_failure_reason": "reactor_not_restartable_process_restart_required",
        "runtime_state": "WS1006_PROCESS_RESTART_REQUIRED",
    })
    snapshot = build_feed_supervisor_snapshot(payload)

    assert snapshot.state == "RESTART_REQUIRED"
    assert snapshot.restart_failure_reason == "reactor_not_restartable_process_restart_required"
