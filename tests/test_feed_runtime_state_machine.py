from __future__ import annotations

from pathlib import Path

from core.feed_runtime import build_canonical_feed_truth_state


def test_feedtruth_transitions_from_booting_to_verified_healthy():
    booting = build_canonical_feed_truth_state({"runtime_state": "BOOTING", "session_id": "S1"})
    connecting = build_canonical_feed_truth_state({"runtime_state": "CONNECTING", "session_id": "S1", "ws_connected": True})
    subscribed = build_canonical_feed_truth_state({"runtime_state": "SUBSCRIBED", "session_id": "S1", "ws_connected": True, "subscribed_option_tokens_count": 12})
    verifying = build_canonical_feed_truth_state({"runtime_state": "VERIFYING_OPTION_TICKS", "session_id": "S1", "ws_connected": True, "subscribed_option_tokens_count": 12, "verified_option_symbols": ["NIFTY"], "missing_option_symbols": ["BANKNIFTY"]})
    healthy = build_canonical_feed_truth_state({
        "runtime_state": "VERIFIED_HEALTHY",
        "session_id": "S1",
        "ws_connected": True,
        "underlying_tick_fresh": True,
        "depth_fresh": True,
        "option_ticks_verified": True,
        "subscribed_option_tokens_count": 12,
        "verified_option_symbols": ["BANKNIFTY", "NIFTY"],
        "missing_option_symbols": [],
        "recovery_blocked": False,
        "process_restart_required": False,
        "latest_ltp_age_sec": 0.4,
        "latest_depth_age_sec": 0.2,
        "latest_option_tick_age_sec": 0.1,
    })

    assert booting.state == "BOOTING"
    assert connecting.state == "CONNECTING"
    assert subscribed.state == "SUBSCRIBED"
    assert verifying.state == "VERIFYING_OPTION_TICKS"
    assert healthy.state == "VERIFIED_HEALTHY"
    assert healthy.blockers == ()
    assert healthy.ws_connected is True
    assert healthy.underlying_tick_fresh is True
    assert healthy.depth_fresh is True
    assert healthy.option_ticks_verified is True


def test_feedtruth_degrades_when_ticks_or_depth_are_stale():
    degraded = build_canonical_feed_truth_state({
        "runtime_state": "VERIFIED_HEALTHY",
        "session_id": "S1",
        "ws_connected": True,
        "underlying_tick_fresh": False,
        "depth_fresh": False,
        "option_ticks_verified": False,
        "subscribed_option_tokens_count": 12,
        "verified_option_symbols": ["NIFTY"],
        "missing_option_symbols": ["BANKNIFTY"],
        "latest_ltp_age_sec": 19.5,
        "latest_depth_age_sec": 18.0,
        "latest_option_tick_age_sec": 16.0,
    })

    assert degraded.state == "DEGRADED"
    assert degraded.reason_code in {"DEGRADED", "feed_unhealthy", "VERIFIED_HEALTHY"}
    assert "LTP_STALE" in degraded.blockers or "UNDERLYING_TICK_STALE" in degraded.blockers
    assert "DEPTH_STALE" in degraded.blockers
    assert degraded.option_ticks_verified is False


def test_feedtruth_treats_recoverable_ws1006_as_degraded_not_restart_required():
    state = build_canonical_feed_truth_state({
        "runtime_state": "RECONNECTING",
        "session_id": "S1",
        "ws_connected": False,
        "recovery_in_progress": True,
        "recovery_state": "RECOVERING_WS_DROP",
        "feed_error_code": 1006,
        "ws_error_code": 1006,
        "ws_error_reason": "connection was closed uncleanly (peer dropped)",
        "latest_ltp_age_sec": 0.4,
        "latest_depth_age_sec": 0.2,
        "latest_option_tick_age_sec": 0.1,
        "underlying_tick_fresh": True,
        "depth_fresh": True,
        "option_ticks_verified": False,
        "subscribed_option_tokens_count": 12,
        "verified_option_symbols": ["NIFTY"],
        "missing_option_symbols": ["BANKNIFTY"],
    })

    assert state.state == "DEGRADED"
    assert state.reason_code == "RECONNECTING"
    assert state.recovery_state == "RECOVERING_WS_DROP"
    assert state.ws_fault_class == "RECOVERABLE_WS_DROP"
    assert state.process_restart_required is False
    assert state.recovery_blocked is False


def test_feedtruth_marks_terminal_main_loop_termination_as_restart_required():
    state = build_canonical_feed_truth_state({
        "runtime_state": "RECOVERY_BLOCKED",
        "session_id": "S1",
        "ws_connected": False,
        "recovery_blocked": True,
        "process_restart_required": True,
        "recovery_state": "TERMINAL",
        "feed_error_code": 1006,
        "reconnect_blocked_reason": "reactor_not_restartable_process_restart_required",
        "ws_error_code": 1006,
        "ws_error_reason": "main loop terminated after reactor shutdown",
        "latest_ltp_age_sec": 0.4,
        "latest_depth_age_sec": 0.2,
        "latest_option_tick_age_sec": 0.1,
        "underlying_tick_fresh": True,
        "depth_fresh": True,
        "option_ticks_verified": False,
        "subscribed_option_tokens_count": 12,
        "verified_option_symbols": ["NIFTY"],
        "missing_option_symbols": ["BANKNIFTY"],
    })

    assert state.state == "RESTART_REQUIRED"
    assert state.reason_code in {"WS1006_PROCESS_RESTART_REQUIRED", "RESTART_REQUIRED"}
    assert state.recovery_state == "TERMINAL"
    assert state.ws_fault_class == "TERMINAL"
    assert state.process_restart_required is True
    assert state.recovery_blocked is True


def test_feedtruth_restart_required_writes_restart_artifact(tmp_path: Path):
    state = build_canonical_feed_truth_state(
        {"feed_error_code": 1006, "session_id": "S1", "ws_connected": False},
        restart_artifact_dir=tmp_path,
    )

    assert state.state == "RESTART_REQUIRED"
    assert state.process_restart_required is True
    assert state.recovery_blocked is True
    assert state.ws_connected is False
    artifact = tmp_path / "feed_restart_required.json"
    assert artifact.exists()
    payload = artifact.read_text(encoding="utf-8")
    assert '"reason": "ws1006_process_restart_required"' in payload
    assert '"no_order_action": true' in payload
    assert '"restart_allowed_only_if_no_open_positions": true' in payload
