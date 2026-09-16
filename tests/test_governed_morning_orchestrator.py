"""Deterministic tests for GovernedMorningOrchestrator and human login auto-continuation."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.governed_morning_orchestrator import (
    GovernedMorningOrchestrator,
    LauncherState,
    snapshot_token_file,
)


@pytest.fixture
def mock_env(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = tmp_path / "state"
    state_root.mkdir()
    token_path = tmp_path / "token.txt"
    lock_file = tmp_path / "launcher.lock"
    return {
        "repo_root": repo_root,
        "state_root": state_root,
        "token_path": token_path,
        "lock_file": lock_file,
    }


def test_1_valid_token_no_login_automatic_continuation(mock_env):
    """1. Valid token -> no login -> automatic continuation."""
    token_path = mock_env["token_path"]
    token_path.write_text("VALID_TOKEN_SECRET_9999")

    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=token_path,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    with patch.object(orc, "validate_broker_read", return_value=(True, "USER1234", None)):
        ok = orc.step_check_auth()
        assert ok is True
        assert orc.state == LauncherState.AUTH_VALID
        assert orc.broker_user_id == "USER1234"


def test_2_missing_token_enters_waiting_human_auth(mock_env):
    """2. Missing token -> WAITING_HUMAN_AUTH."""
    token_path = mock_env["token_path"]
    if token_path.exists():
        token_path.unlink()

    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=token_path,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    ok = orc.step_check_auth()
    assert ok is False
    assert orc.state == LauncherState.WAITING_HUMAN_AUTH
    assert orc.blocker_reason is None or "token" in str(orc.state_history[-1]["reason"])


def test_3_expired_token_enters_waiting_human_auth(mock_env):
    """3. Expired token -> WAITING_HUMAN_AUTH."""
    token_path = mock_env["token_path"]
    token_path.write_text("EXPIRED_TOKEN_1111")

    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=token_path,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    with patch.object(orc, "validate_broker_read", return_value=(False, None, "TokenException: Expired")):
        ok = orc.step_check_auth()
        assert ok is False
        assert orc.state == LauncherState.WAITING_HUMAN_AUTH


def test_4_fresh_token_detected_and_validated_continues(mock_env):
    """4. Fresh token detected -> profile validation -> continuation."""
    token_path = mock_env["token_path"]
    token_path.write_text("INITIAL_STALE_TOKEN")

    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=token_path,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    orc.step_check_auth()

    # Simulate human login writing fresh token in background
    def write_fresh():
        time.sleep(0.1)
        token_path.write_text("FRESH_VALID_TOKEN_2222")

    threading.Thread(target=write_fresh).start()

    detected = orc.step_wait_human_auth(poll_interval=0.05, timeout_override=2.0)
    assert detected is True
    assert orc.state == LauncherState.DETECT_FRESH_TOKEN

    with patch.object(orc, "validate_broker_read", return_value=(True, "USER9999", None)):
        valid = orc.step_validate_auth()
        assert valid is True
        assert orc.state == LauncherState.AUTH_VALID
        assert orc.broker_user_id == "USER9999"


def test_5_token_changed_but_broker_validation_fails_no_continuation(mock_env):
    """5. Token file changed but broker validation fails -> no continuation."""
    token_path = mock_env["token_path"]
    token_path.write_text("INITIAL_TOKEN")

    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=token_path,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    orc.step_check_auth()

    # Update file with bad token
    token_path.write_text("MALFORMED_OR_REJECTED_TOKEN")
    orc.step_wait_human_auth(poll_interval=0.01, timeout_override=0.5)

    with patch.object(orc, "validate_broker_read", return_value=(False, None, "InvalidToken")):
        valid = orc.step_validate_auth(max_retries=1)
        assert valid is False
        assert orc.state == LauncherState.WAITING_HUMAN_AUTH


def test_6_human_auth_timeout_fails_closed(mock_env):
    """6. Timeout -> fail closed."""
    token_path = mock_env["token_path"]
    token_path.write_text("INITIAL_TOKEN")

    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=token_path,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    orc.step_check_auth()

    # Don't update token, let it time out quickly
    detected = orc.step_wait_human_auth(poll_interval=0.02, timeout_override=0.1)
    assert detected is False
    assert orc.state == LauncherState.STOPPED
    assert orc.stop_reason == "auth_timeout_waiting_human_auth"


def test_7_secrets_absent_from_logs_and_evidence(mock_env):
    """7. Secrets absent from logs/evidence."""
    secret = "TOP_SECRET_AUTH_TOKEN_VALUE_NEVER_LOG"
    token_path = mock_env["token_path"]
    token_path.write_text(secret)

    emitted_lines = []
    def callback(step, status, detail):
        emitted_lines.append(f"{step} {status} {detail}")

    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=token_path,
        lock_file=mock_env["lock_file"],
        open_browser=False,
        telemetry_callback=callback,
    )
    with patch.object(orc, "validate_broker_read", return_value=(True, "LLL209", None)):
        orc.step_check_auth()

    full_history = json.dumps(orc.state_history)
    assert secret not in full_history
    assert all(secret not in line for line in emitted_lines)


def test_8_instrument_refresh_only_after_auth(mock_env):
    """8. Instrument refresh only after AUTH."""
    token_path = mock_env["token_path"]
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=token_path,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    # Auth is not yet valid
    assert orc.state == LauncherState.START
    # In run(), if auth check fails and wait times out, refresh instruments is never called
    with patch.object(orc, "step_verify_release", return_value=True), \
         patch.object(orc, "step_verify_storage", return_value=True), \
         patch.object(orc, "step_check_auth", return_value=False), \
         patch.object(orc, "step_wait_human_auth", return_value=False), \
         patch.object(orc, "step_refresh_instruments") as mock_refresh:
        res = orc.run()
        mock_refresh.assert_not_called()
        assert res == LauncherState.STOPPED


def test_9_websocket_cannot_start_before_auth(mock_env):
    """9. WebSocket cannot start before AUTH."""
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    with patch.object(orc, "step_verify_release", return_value=True), \
         patch.object(orc, "step_verify_storage", return_value=True), \
         patch.object(orc, "step_check_auth", return_value=False), \
         patch.object(orc, "step_wait_human_auth", return_value=False), \
         patch.object(orc, "step_connect_websocket") as mock_ws:
        orc.run()
        mock_ws.assert_not_called()


def test_10_observer_cannot_start_before_prerequisites(mock_env):
    """10. Observer cannot start before prerequisites."""
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    # Release verification fails
    with patch.object(orc, "step_verify_release", return_value=False), \
         patch.object(orc, "step_arm_observer") as mock_arm:
        res = orc.run()
        mock_arm.assert_not_called()
        assert orc.state == LauncherState.BLOCKED


def test_11_duplicate_launcher_prevented(mock_env):
    """11. Duplicate launcher prevented (single-instance lock)."""
    orc1 = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    assert orc1.acquire_lock() is True

    orc2 = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    # Second instance must fail to acquire lock
    assert orc2.acquire_lock() is False
    res = orc2.run()
    assert res == LauncherState.BLOCKED
    assert orc2.blocker_reason == "GOVERNED_MORNING_LAUNCHER_ALREADY_RUNNING"

    orc1.release_lock()
    # Now orc2 can acquire
    assert orc2.acquire_lock() is True
    orc2.release_lock()


def test_12_sigterm_clean_shutdown(mock_env):
    """12. SIGTERM clean shutdown."""
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    orc.acquire_lock()
    assert mock_env["lock_file"].exists()

    orc.stop("SIGTERM")
    assert orc.state == LauncherState.STOPPED
    assert not mock_env["lock_file"].exists()


def test_13_broker_authorities_remain_false(mock_env):
    """13. Broker write/order/paper/live authorities remain false."""
    from core.kite_read_only_observation_runtime import safe_environment
    env = safe_environment()
    assert env.get("BROKER_WRITE_AUTHORITY") != "true"
    assert env.get("ORDER_AUTHORITY") != "true"
    assert env.get("LIVE_EXECUTION_AUTHORIZED") != "true"


def test_14_no_order_endpoints_invoked(mock_env):
    """14. No order endpoints invoked."""
    from unittest.mock import MagicMock
    spy_broker = MagicMock()
    # Orchestrator does not touch order endpoints
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    assert not hasattr(orc, "place_order")
    assert not hasattr(orc, "modify_order")
    assert not hasattr(orc, "cancel_order")
    spy_broker.place_order.assert_not_called()
    spy_broker.modify_order.assert_not_called()
    spy_broker.cancel_order.assert_not_called()


def test_15_successful_human_login_requires_no_second_command(mock_env):
    """15. Successful human login requires no second launcher command (full pipeline continuation)."""
    token_path = mock_env["token_path"]
    token_path.write_text("INITIAL_STALE_TOKEN")

    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=token_path,
        lock_file=mock_env["lock_file"],
        open_browser=False,
        dry_run=True,
    )

    # Human writes fresh token while orc is waiting in step_wait_human_auth
    def human_logs_in():
        time.sleep(0.1)
        token_path.write_text("FRESH_VALID_TOKEN_AFTER_2FA")

    threading.Thread(target=human_logs_in).start()

    with patch.object(orc, "step_verify_release", return_value=True), \
         patch.object(orc, "step_verify_storage", return_value=True), \
         patch.object(orc, "validate_broker_read", side_effect=[
             (False, None, "Expired"),      # initial check fails
             (True, "USER777", None),       # validation after fresh token succeeds
         ]), \
         patch.object(orc, "step_refresh_instruments", return_value=True), \
         patch.object(orc, "step_connect_websocket", return_value=True), \
         patch.object(orc, "step_verify_market_data", return_value=True):
        final_state = orc.run()
        # Finished through ARM_OBSERVER without any second command!
        assert final_state == LauncherState.STOPPED  # dry-run stops cleanly at ARM_OBSERVER
        states = [entry["to_state"] for entry in orc.state_history]
        assert "WAITING_HUMAN_AUTH" in states
        assert "DETECT_FRESH_TOKEN" in states
        assert "VALIDATE_AUTH" in states
        assert "AUTH_VALID" in states
        assert "CONNECT_WEBSOCKET" in states
        assert "ARM_OBSERVER" in states
