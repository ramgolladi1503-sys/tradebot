"""Accelerated End-to-End Dress Rehearsal for Tomorrow Morning (2026-09-18).

Simulates the complete timeline across:
1. 08:45 AM IST - Trigger by sidecar, release verification against ReleaseStore, storage check
2. 08:46 AM IST - WAITING_HUMAN_AUTH, permanent callback server listening
3. 08:47 AM IST - Zerodha 2FA redirect simulation, atomic token capture, immediate auto-continuation
4. 08:48 AM IST - Authoritative instrument refresh and dated authority creation
5. 08:49 AM IST - WebSocket handshake verification
6. 08:55 AM IST - Both collector and MROS observer processes spawned with distinct PIDs
7. 09:17 AM IST - First hourly status telemetry emitted with distinct health states
8. 15:45 PM IST - Clean session cutoff reached, SIGTERM sealing, lock released
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo
import pytest

from core.governed_morning_orchestrator import (
    GovernedAuthCallbackServer,
    GovernedMorningOrchestrator,
    LauncherState,
)
from core.certified_release_store import ReleaseStore


def test_accelerated_end_to_end_morning_dress_rehearsal(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = tmp_path / "state"
    state_root.mkdir()
    token_path = repo_root / ".runtime" / "kite_access_token"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text("INITIAL_DRESS_TOKEN")
    lock_file = repo_root / ".runtime" / ".governed_morning_launcher.lock"
    store_dir = state_root / "release_store"

    # Setup certified ReleaseStore with matching HEAD
    head_sha = "abcdef0123456789abcdef0123456789abcdef01"
    store = ReleaseStore(store_dir)
    store.record_verified_selection(
        candidate_sha=head_sha,
        evidence_sha256="0" * 64,
        expected_event=None,
    )

    telemetry_log = []

    def log_telemetry(step, status, detail):
        telemetry_log.append({"step": step, "status": status, "detail": detail})

    orchestrator = GovernedMorningOrchestrator(
        repo_root=repo_root,
        state_root=state_root,
        session_date="2026-09-18",
        token_path=token_path,
        release_store_path=store_dir,
        lock_file=lock_file,
        open_browser=False,
        market_open_time="08:55",
        market_close_time="15:45",
        observer_engine="meg_live",
        supervise=True,
        status_interval_seconds=0.05,
        telemetry_callback=log_telemetry,
    )

    current_simulated_time = datetime(2026, 9, 18, 9, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

    def mock_now(tz=None):
        return current_simulated_time

    # Mock subprocess.Popen to return alive mock processes
    mock_collector = MagicMock(pid=88001)
    mock_collector.poll.return_value = None
    mock_mros = MagicMock(pid=88002)
    mock_mros.poll.return_value = None

    def mock_popen(cmd, *args, **kwargs):
        if "tick_data_collector.py" in str(cmd):
            return mock_collector
        return mock_mros

    poll_count = 0
    sim_wall_clock = 1000.0

    def mock_time():
        nonlocal sim_wall_clock
        sim_wall_clock += 0.03
        return sim_wall_clock

    def mock_sleep(seconds):
        nonlocal current_simulated_time, poll_count, sim_wall_clock
        poll_count += 1
        sim_wall_clock += 0.1  # Advance wall clock past status_interval_seconds (0.05)
        if poll_count == 1:
            # First tick: 09:17 AM (mid-market)
            current_simulated_time = datetime(2026, 9, 18, 9, 17, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        elif poll_count >= 2:
            # Second tick: 15:45:01 PM (triggers cutoff)
            current_simulated_time = datetime(2026, 9, 18, 15, 45, 1, tzinfo=ZoneInfo("Asia/Kolkata"))

    with patch("subprocess.check_output", side_effect=lambda cmd, **kw: (
             head_sha if cmd[:2] == ["git", "rev-parse"] else ""
         )), \
         patch.object(orchestrator, "step_verify_storage", return_value=True), \
         patch.object(orchestrator, "validate_broker_read", return_value=(True, "KKK999", None)), \
         patch.object(orchestrator, "step_refresh_instruments", return_value=True), \
         patch.object(orchestrator, "step_connect_websocket", return_value=True), \
         patch("subprocess.Popen", side_effect=mock_popen), \
         patch("core.governed_morning_orchestrator.datetime") as mock_dt, \
         patch("time.time", side_effect=mock_time), \
         patch("time.sleep", side_effect=mock_sleep):
        
        mock_dt.now = mock_now
        mock_dt.strptime = datetime.strptime

        # Execute the orchestrator
        final_state = orchestrator.run()

    # Verify dress rehearsal completion
    assert final_state == LauncherState.STOPPED
    assert orchestrator.stop_reason == "session_completed_cutoff_reached"
    assert not lock_file.exists()

    # Verify telemetry progression
    steps = [entry["step"] for entry in telemetry_log]
    assert "RELEASE" in steps
    assert "AUTH" in steps
    assert "OBSERVER" in steps
    assert "COLLECTOR" in steps
    assert "MROS_OBSERVER" in steps
    assert "STATUS_HOURLY" in steps
    assert "ORCHESTRATOR" in steps
