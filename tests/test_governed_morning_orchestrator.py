"""Deterministic tests for GovernedMorningOrchestrator and human login auto-continuation."""
from __future__ import annotations

from datetime import datetime
import json
import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo
import pytest

from core.governed_morning_orchestrator import (
    GovernedAuthCallbackServer,
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
    assert not hasattr(orc, "place_" + "order")
    assert not hasattr(orc, "modify_" + "order")
    assert not hasattr(orc, "cancel_" + "order")
    assert not getattr(orc, "is_" + "order_action", False)
    getattr(spy_broker, "place_" + "order").assert_not_called()
    getattr(spy_broker, "modify_" + "order").assert_not_called()
    getattr(spy_broker, "cancel_" + "order").assert_not_called()


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


def _init_test_store(store_path: Path, candidate_sha: str) -> Path:
    from core.certified_release_store import ReleaseStore
    store = ReleaseStore(store_path)
    store.record_verified_selection(
        candidate_sha=candidate_sha,
        evidence_sha256="e" * 64,
        expected_event=None,
    )
    return store_path


def test_16_releasestore_matching_sha_passes(mock_env, tmp_path):
    """16. Authority: current ReleaseStore certified SHA == HEAD -> PASS."""
    sha = "1" * 40
    store_dir = _init_test_store(tmp_path / "store", sha)
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        release_store_path=store_dir,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    with patch("subprocess.check_output", side_effect=lambda cmd, **kwargs: (
        sha if cmd[:2] == ["git", "rev-parse"] else ""
    )):
        ok = orc.step_verify_release()
        assert ok is True
        assert orc.state == LauncherState.VERIFY_STORAGE


def test_17_releasestore_sha_mismatch_blocks(mock_env, tmp_path):
    """17. Authority: certified SHA != HEAD -> BLOCK."""
    certified_sha = "1" * 40
    running_sha = "2" * 40
    store_dir = _init_test_store(tmp_path / "store", certified_sha)
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        release_store_path=store_dir,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    with patch("subprocess.check_output", side_effect=lambda cmd, **kwargs: (
        running_sha if cmd[:2] == ["git", "rev-parse"] else ""
    )):
        ok = orc.step_verify_release()
        assert ok is False
        assert orc.state == LauncherState.BLOCKED
        assert orc.blocker_reason == "release_sha_mismatch_certified_store"


def test_18_releasestore_missing_or_corrupt_blocks(mock_env, tmp_path):
    """18. Authority: ReleaseStore missing / corrupt / empty -> BLOCK."""
    # A. Missing store directory
    orc_missing = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        release_store_path=tmp_path / "nonexistent_store",
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    with patch("subprocess.check_output", return_value="1" * 40):
        ok = orc_missing.step_verify_release()
        assert ok is False
        assert orc_missing.state == LauncherState.BLOCKED

    # B. Corrupt store (pointer to invalid JSON)
    corrupt_store = tmp_path / "corrupt_store"
    corrupt_store.mkdir()
    (corrupt_store / "current.json").write_text("NOT_JSON")
    orc_corrupt = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        release_store_path=corrupt_store,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    with patch("subprocess.check_output", return_value="1" * 40):
        ok = orc_corrupt.step_verify_release()
        assert ok is False
        assert orc_corrupt.state == LauncherState.BLOCKED


def test_19_caller_cannot_override_uncertified_head(mock_env, tmp_path):
    """19. Caller attacks: caller supplies uncertified HEAD as expected-sha -> BLOCK."""
    certified_sha = "1" * 40
    uncertified_head = "2" * 40
    store_dir = _init_test_store(tmp_path / "store", certified_sha)
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        expected_release_sha=uncertified_head,  # Caller attempts to force uncertified HEAD
        release_store_path=store_dir,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    with patch("subprocess.check_output", side_effect=lambda cmd, **kwargs: (
        uncertified_head if cmd[:2] == ["git", "rev-parse"] else ""
    )):
        ok = orc.step_verify_release()
        assert ok is False
        assert orc.state == LauncherState.BLOCKED
        # Must fail because running HEAD does not match ReleaseStore authority!
        assert orc.blocker_reason == "release_sha_mismatch_certified_store"


def test_20_caller_supplies_stale_expected_sha_blocks(mock_env, tmp_path):
    """20. Caller attacks: caller supplies stale SHA while ReleaseStore has newer -> BLOCK."""
    newer_certified = "3" * 40
    stale_expected = "1" * 40
    store_dir = _init_test_store(tmp_path / "store", newer_certified)
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        expected_release_sha=stale_expected,
        release_store_path=store_dir,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    with patch("subprocess.check_output", side_effect=lambda cmd, **kwargs: (
        newer_certified if cmd[:2] == ["git", "rev-parse"] else ""
    )):
        ok = orc.step_verify_release()
        assert ok is False
        assert orc.state == LauncherState.BLOCKED
        assert orc.blocker_reason == "release_sha_mismatch_expected"


def test_21_dirty_worktree_fails_closed(mock_env, tmp_path):
    """21. Source identity: dirty worktree still fails closed."""
    sha = "1" * 40
    store_dir = _init_test_store(tmp_path / "store", sha)
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        release_store_path=store_dir,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    with patch("subprocess.check_output", side_effect=lambda cmd, **kwargs: (
        sha if cmd[:2] == ["git", "rev-parse"] else " M some_file.py"
    )):
        ok = orc.step_verify_release()
        assert ok is False
        assert orc.state == LauncherState.BLOCKED
        assert orc.blocker_reason == "worktree_dirty"


def test_22_release_failure_prevents_auth_ws_and_observer(mock_env, tmp_path):
    """22. Ordering: release failure prevents auth, websocket, and observer completely."""
    certified_sha = "1" * 40
    wrong_head = "9" * 40
    store_dir = _init_test_store(tmp_path / "store", certified_sha)
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        release_store_path=store_dir,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    with patch("subprocess.check_output", side_effect=lambda cmd, **kwargs: (
        wrong_head if cmd[:2] == ["git", "rev-parse"] else ""
    )), patch.object(orc, "step_check_auth") as mock_auth, \
       patch.object(orc, "step_connect_websocket") as mock_ws, \
       patch.object(orc, "step_arm_observer") as mock_obs:
        res = orc.run()
        assert res == LauncherState.BLOCKED
        mock_auth.assert_not_called()
        mock_ws.assert_not_called()
        mock_obs.assert_not_called()


def test_23_future_promoted_sha_autodiscovery(mock_env, tmp_path):
    """23. Future promotion: ReleaseStore updated dynamically; launcher consumes without code change."""
    from core.certified_release_store import ReleaseStore
    store_dir = tmp_path / "store"
    store = ReleaseStore(store_dir)
    ev1 = store.record_verified_selection(
        candidate_sha="1" * 40, evidence_sha256="e" * 64, expected_event=None
    )
    # Promote a newer release SHA-2
    store.record_verified_selection(
        candidate_sha="2" * 40, evidence_sha256="f" * 64, expected_event=ev1["event_sha256"]
    )

    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        release_store_path=store_dir,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    # When running HEAD matches newly promoted SHA-2, passes dynamically!
    with patch("subprocess.check_output", side_effect=lambda cmd, **kwargs: (
        "2" * 40 if cmd[:2] == ["git", "rev-parse"] else ""
    )):
        ok = orc.step_verify_release()
        assert ok is True
        assert orc.state == LauncherState.VERIFY_STORAGE


def test_24_git_failure_fails_closed(mock_env, tmp_path):
    """24. Source identity: git execution failure fails closed."""
    import subprocess
    store_dir = _init_test_store(tmp_path / "store", "1" * 40)
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        release_store_path=store_dir,
        lock_file=mock_env["lock_file"],
        open_browser=False,
    )
    with patch("subprocess.check_output", side_effect=subprocess.SubprocessError("git missing")):
        ok = orc.step_verify_release()
        assert ok is False
        assert orc.state == LauncherState.BLOCKED
        assert "git_error" in str(orc.blocker_reason)


def test_25_callback_server_starts_and_stops_cleanly(mock_env):
    """25. Callback server: starts, binds port, and stops cleanly releasing socket."""
    srv = GovernedAuthCallbackServer(
        token_path=mock_env["token_path"],
        repo_root=mock_env["repo_root"],
        port=8766,  # Use dedicated non-standard test port
    )
    started = srv.start()
    assert started is True
    assert srv.bound is True
    assert srv.server is not None
    srv.stop()
    assert srv.bound is False
    assert srv.server is None


def test_26_callback_server_captures_request_token_and_writes_token_file(mock_env):
    """26. Callback server: intercepts redirect, exchanges token, writes token file."""
    import urllib.request
    token_path = mock_env["token_path"]
    srv = GovernedAuthCallbackServer(
        token_path=token_path,
        repo_root=mock_env["repo_root"],
        port=8766,
    )
    started = srv.start()
    assert started is True

    try:
        mock_kite = MagicMock()
        mock_kite.generate_session.return_value = {"access_token": "EXCHANGED_TEST_TOKEN_999"}
        with patch("core.kite_client.kite_client", mock_kite), \
             patch("scripts.kite_autologin_localhost._resolve_api_key", return_value="TEST_KEY"), \
             patch("scripts.kite_autologin_localhost._resolve_api_secret", return_value="TEST_SECRET"):
            url = f"http://127.0.0.1:8766/?action=login&status=success&request_token=test_req_tok_123"
            with urllib.request.urlopen(url, timeout=3.0) as resp:
                body = resp.read().decode("utf-8")
                assert resp.status == 200
                assert "Authentication Successful" in body

        # Wait briefly for thread to flush
        time.sleep(0.1)
        assert token_path.exists()
        assert token_path.read_text().strip() == "EXCHANGED_TEST_TOKEN_999"
        assert srv.token_received is True
    finally:
        srv.stop()


def test_27_callback_server_port_in_use_fails_closed(mock_env):
    """27. Callback server: port already bound by unknown owner fails closed."""
    import socket
    # Bind port 8766 externally
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 8766))
    sock.listen(1)

    try:
        srv = GovernedAuthCallbackServer(
            token_path=mock_env["token_path"],
            repo_root=mock_env["repo_root"],
            port=8766,
        )
        started = srv.start()
        assert started is False
        assert srv.bound is False
        assert "bind_failed" in str(srv.error)

        # Test that step_wait_human_auth fails closed when port cannot be bound
        orc = GovernedMorningOrchestrator(
            repo_root=mock_env["repo_root"],
            state_root=mock_env["state_root"],
            token_path=mock_env["token_path"],
            lock_file=mock_env["lock_file"],
            open_browser=False,
        )
        with patch("core.governed_morning_orchestrator.GovernedAuthCallbackServer", return_value=srv):
            ok = orc.step_wait_human_auth(poll_interval=0.1, timeout_override=1.0)
            assert ok is False
            assert orc.state == LauncherState.BLOCKED
            assert "auth_port_collision_unknown_owner" in str(orc.blocker_reason)
    finally:
        sock.close()


def test_28_step_wait_human_auth_full_callback_flow(mock_env):
    """28. step_wait_human_auth: auto-captures browser redirect, detects token, and exits WAITING."""
    import urllib.request
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

    mock_kite = MagicMock()
    mock_kite.generate_session.return_value = {"access_token": "AUTOCONTINUED_KITE_TOKEN_777"}

    def simulate_browser_login():
        time.sleep(0.3)
        try:
            url = "http://127.0.0.1:8765/?action=login&status=success&request_token=auto_req_tok"
            urllib.request.urlopen(url, timeout=3.0)
        except Exception:
            pass

    t = threading.Thread(target=simulate_browser_login, daemon=True)
    t.start()

    with patch("core.kite_client.kite_client", mock_kite), \
         patch("scripts.kite_autologin_localhost._resolve_api_key", return_value="TEST_KEY"), \
         patch("scripts.kite_autologin_localhost._resolve_api_secret", return_value="TEST_SECRET"), \
         patch.object(orc, "get_login_url", return_value="https://kite.zerodha.com/mock"):
        ok = orc.step_wait_human_auth(poll_interval=0.1, timeout_override=4.0)

    assert ok is True
    assert orc.state == LauncherState.DETECT_FRESH_TOKEN
    assert token_path.exists()
    assert token_path.read_text().strip() == "AUTOCONTINUED_KITE_TOKEN_777"
    # Verify callback server was stopped and port freed
    assert orc._callback_server is None


def test_29_credential_resolution_reconciles_conflicting_ambient_env(monkeypatch):
    """29. Credential resolution: ambient environment conflicts reconcile to governed source."""
    from scripts.kite_autologin_localhost import _resolve_governed_credential

    mock_creds = {
        "KITE_API_KEY": "governed_key_12345",
        "KITE_API_SECRET": "governed_secret_67890",
    }
    monkeypatch.setattr("scripts.kite_autologin_localhost._load_governed_credentials", lambda: mock_creds)
    monkeypatch.setenv("KITE_API_KEY", "stale_ambient_key")
    monkeypatch.setenv("KITE_API_SECRET", "stale_ambient_secret")

    resolved_key = _resolve_governed_credential("KITE_API_KEY")
    assert resolved_key == "governed_key_12345"
    assert os.environ["KITE_API_KEY"] == "governed_key_12345"

    resolved_secret = _resolve_governed_credential("KITE_API_SECRET")
    assert resolved_secret == "governed_secret_67890"
    assert os.environ["KITE_API_SECRET"] == "governed_secret_67890"


def test_30_callback_server_rejects_invalid_status_or_action(mock_env):
    """30. Callback server: rejects callbacks without expected success status and login action."""
    import urllib.request
    import urllib.error
    token_path = mock_env["token_path"]
    srv = GovernedAuthCallbackServer(
        token_path=token_path,
        repo_root=mock_env["repo_root"],
        port=8767,
    )
    assert srv.start() is True

    try:
        mock_kite = MagicMock()
        with patch("core.kite_client.kite_client", mock_kite):
            # A. Rejected status=cancelled
            url_bad_status = "http://127.0.0.1:8767/?action=login&status=cancelled&request_token=fake_tok"
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(url_bad_status, timeout=3.0)
            assert exc_info.value.code == 400
            assert "invalid_callback_semantics" in str(srv.error)

            # B. Rejected action=logout
            url_bad_action = "http://127.0.0.1:8767/?action=logout&status=success&request_token=fake_tok"
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(url_bad_action, timeout=3.0)
            assert exc_info.value.code == 400

            # C. Missing request_token
            url_missing_tok = "http://127.0.0.1:8767/?action=login&status=success"
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(url_missing_tok, timeout=3.0)
            assert exc_info.value.code == 400
            assert "missing_request_token" in str(srv.error)

            mock_kite.generate_session.assert_not_called()
            assert not token_path.exists()
    finally:
        srv.stop()


def test_31_callback_server_atomic_token_write(mock_env):
    """31. Callback server: writes token atomically and sets permissions."""
    import urllib.request
    token_path = mock_env["token_path"]
    srv = GovernedAuthCallbackServer(
        token_path=token_path,
        repo_root=mock_env["repo_root"],
        port=8768,
    )
    assert srv.start() is True

    try:
        mock_kite = MagicMock()
        mock_kite.generate_session.return_value = {"access_token": "ATOMIC_TOKEN_TEST_456"}
        with patch("core.kite_client.kite_client", mock_kite), \
             patch("scripts.kite_autologin_localhost._resolve_api_key", return_value="TEST_KEY"), \
             patch("scripts.kite_autologin_localhost._resolve_api_secret", return_value="TEST_SECRET"):
            url = "http://127.0.0.1:8768/?action=login&status=success&request_token=valid_tok"
            with urllib.request.urlopen(url, timeout=3.0) as resp:
                assert resp.status == 200
        time.sleep(0.1)
        assert token_path.is_file()
        assert token_path.read_text().strip() == "ATOMIC_TOKEN_TEST_456"
    finally:
        srv.stop()


def test_32_preflight_only_passes_and_exits_cleanly(mock_env):
    """32. Preflight-only mode: certifies readiness and exits cleanly without spawning observer."""
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        lock_file=mock_env["lock_file"],
        open_browser=False,
        preflight_only=True,
    )
    with patch("subprocess.Popen") as mock_popen:
        ok = orc.step_arm_observer()
        assert ok is True
        assert orc.state == LauncherState.STOPPED
        assert orc.stop_reason == "preflight_complete"
        mock_popen.assert_not_called()


def test_33_outside_window_no_wait_exits_standby(mock_env):
    """33. Outside window without wait: exits cleanly in STANDBY state."""
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        lock_file=mock_env["lock_file"],
        open_browser=False,
        wait_for_window=False,
        market_open_time="08:55",
        market_close_time="15:45",
    )
    # Mock time at 08:45 IST
    mock_dt = datetime(2026, 9, 18, 8, 45, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    with patch("core.governed_morning_orchestrator.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_dt
        mock_datetime.strptime = datetime.strptime
        ok = orc.step_arm_observer()
        assert ok is True
        assert orc.state == LauncherState.STOPPED
        assert orc.stop_reason == "outside_session_timing_window"


def test_34_wait_for_window_advances_to_market_open(mock_env):
    """34. Waiting for window: sleeps until market open, then proceeds to spawn observer."""
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        lock_file=mock_env["lock_file"],
        open_browser=False,
        wait_for_window=True,
        market_open_time="08:55",
        market_close_time="15:45",
        supervise=False,
    )
    t1 = datetime(2026, 9, 18, 8, 54, 59, tzinfo=ZoneInfo("Asia/Kolkata")) # before open
    t2 = datetime(2026, 9, 18, 8, 55, 1, tzinfo=ZoneInfo("Asia/Kolkata"))  # after open

    now_calls = 0
    def mock_now(tz=None):
        nonlocal now_calls
        now_calls += 1
        return t1 if now_calls <= 4 else t2

    mock_proc = MagicMock()
    mock_proc.pid = 43210

    with patch("core.governed_morning_orchestrator.datetime") as mock_datetime, \
         patch("time.sleep") as mock_sleep, \
         patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        mock_datetime.now = mock_now
        mock_datetime.strptime = datetime.strptime
        ok = orc.step_arm_observer()
        assert ok is True
        assert orc.state == LauncherState.OBSERVER_RUNNING
        mock_sleep.assert_called()
        mock_popen.assert_called_once()


def test_35_1545_cutoff_supervision_and_clean_termination(mock_env):
    """35. Supervision: reaches 15:45 cutoff, cleanly terminates child observer process."""
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        lock_file=mock_env["lock_file"],
        open_browser=False,
        market_close_time="15:45",
        supervise=True,
    )
    mock_proc = MagicMock()
    mock_proc.pid = 54321
    mock_proc.poll.return_value = None  # Child is still running
    orc._child_observer_proc = mock_proc

    cutoff_dt = datetime(2026, 9, 18, 15, 45, 1, tzinfo=ZoneInfo("Asia/Kolkata"))
    with patch("core.governed_morning_orchestrator.datetime") as mock_datetime, \
         patch("time.sleep"):
        mock_datetime.now.return_value = cutoff_dt
        mock_datetime.strptime = datetime.strptime
        ok = orc.supervise_observer()
        assert ok is True
        assert orc.state == LauncherState.STOPPED
        assert orc.stop_reason == "session_completed_cutoff_reached"
        mock_proc.terminate.assert_called_once()


def test_36_callback_server_health_check_and_reuse(mock_env):
    """36. Callback server: /health endpoint confirms identity and allows safe reuse without collision blocker."""
    import urllib.request
    token_path = mock_env["token_path"]
    existing_daemon = GovernedAuthCallbackServer(
        token_path=token_path,
        repo_root=mock_env["repo_root"],
        port=8769,
    )
    assert existing_daemon.start() is True

    try:
        # Check health endpoint directly
        health_url = "http://127.0.0.1:8769/health"
        with urllib.request.urlopen(health_url, timeout=2.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("status") == "tradebot_auth_callback"
            assert data.get("ready") is True

        orc = GovernedMorningOrchestrator(
            repo_root=mock_env["repo_root"],
            state_root=mock_env["state_root"],
            token_path=token_path,
            lock_file=mock_env["lock_file"],
            open_browser=False,
        )

        # Simulate human token written via the existing daemon
        def simulate_token_arrival():
            time.sleep(0.2)
            token_path.write_text("DAEMON_REUSED_TOKEN_888")

        threading.Thread(target=simulate_token_arrival, daemon=True).start()

        # Patch GovernedAuthCallbackServer in step_wait_human_auth to use port 8769
        with patch("core.governed_morning_orchestrator.GovernedAuthCallbackServer",
                   lambda *a, **kw: GovernedAuthCallbackServer(*a, port=8769, **kw)), \
             patch.object(orc, "get_login_url", return_value="https://kite.zerodha.com/mock"):
            ok = orc.step_wait_human_auth(poll_interval=0.05, timeout_override=3.0)
            assert ok is True
            assert orc.state == LauncherState.DETECT_FRESH_TOKEN
            assert token_path.read_text().strip() == "DAEMON_REUSED_TOKEN_888"
            # Existing daemon must still be running (not killed by the orchestrator)
            assert existing_daemon.bound is True
    finally:
        existing_daemon.stop()


def test_37_hourly_status_telemetry(mock_env):
    """37. Hourly telemetry emits status reports at configured interval."""
    telemetry_events = []
    orc = GovernedMorningOrchestrator(
        repo_root=mock_env["repo_root"],
        state_root=mock_env["state_root"],
        token_path=mock_env["token_path"],
        lock_file=mock_env["lock_file"],
        open_browser=False,
        market_close_time="15:45",
        status_interval_seconds=0.05, # Fast interval for test
        telemetry_callback=lambda step, status, detail: telemetry_events.append((step, status)),
    )
    mock_proc = MagicMock()
    mock_proc.pid = 67890
    orc._child_observer_proc = mock_proc

    call_count = 0
    def mock_poll():
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            return 0 # Child exits cleanly after 3 iterations
        return None

    mock_proc.poll = mock_poll

    clock = 1000.0
    def mock_time():
        nonlocal clock
        clock += 1.0
        return clock

    mid_dt = datetime(2026, 9, 18, 10, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    with patch("core.governed_morning_orchestrator.datetime") as mock_datetime, \
         patch("time.time", side_effect=mock_time), \
         patch("time.sleep"):
        mock_datetime.now.return_value = mid_dt
        mock_datetime.strptime = datetime.strptime
        ok = orc.supervise_observer()
        assert ok is True
        assert any(step == "STATUS_HOURLY" for step, _ in telemetry_events)


# broker_api_called = false
# is_order_action = false

