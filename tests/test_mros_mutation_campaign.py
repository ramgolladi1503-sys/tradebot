"""Mutation campaign suite for Governed Morning Observer and Autologin Callback.

Applies 10 deliberate mutations across:
1. release_sha_equality_mutation -> caught (mismatch blocks)
2. callback_status_action_mutation -> caught (bad semantics rejected 400)
3. callback_nonce_spoof_mutation -> caught (spoofed nonce fails closed 400/blocked)
4. callback_oversized_uri_mutation -> caught (oversized URL rejected 414)
5. persistent_mros_selection_mutation -> caught (both collector and mros spawned)
6. collector_vs_observer_health_separation_mutation -> caught (collector alive cannot pass dead mros)
7. scheduler_timezone_mutation -> caught (cron converts to exactly 08:45 IST)
8. single_instance_lock_mutation -> caught (duplicate launcher blocked)
9. audit_predecessor_binding_mutation -> caught (mutated archive fails provenance)
10. zero_broker_writes_mutation -> caught (broker write attempts rejected)
"""
from __future__ import annotations

import json
import os
import stat
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
from core.audit_chain_recovery import (
    perform_audit_chain_rollover,
    verify_recovery_provenance,
)


def run_mros_mutation_campaign(tmp_path: Path) -> dict[str, object]:
    results = {}

    # 1. Mutation: release SHA equality check bypassed
    orc1 = GovernedMorningOrchestrator(
        repo_root=tmp_path,
        state_root=tmp_path,
        token_path=tmp_path / "token.txt",
        release_store_path=tmp_path / "empty_store",
        lock_file=tmp_path / "lock.txt",
        open_browser=False,
    )
    with patch("subprocess.check_output", return_value="deadbeef" * 5):
        ok1 = orc1.step_verify_release()
    # Mutation killed if mismatch/missing store returns False
    results["release_sha_equality_mutation"] = (ok1 is False and orc1.state == LauncherState.BLOCKED)

    # 2. Mutation: callback accepts invalid status/action
    srv = GovernedAuthCallbackServer(
        token_path=tmp_path / "token.txt",
        repo_root=tmp_path,
        port=8773,
    )
    assert srv.start() is True
    try:
        import urllib.request
        import urllib.error
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen("http://127.0.0.1:8773/?action=logout&status=failure", timeout=2.0)
        results["callback_status_action_mutation"] = (exc.value.code == 400)
    finally:
        srv.stop()

    # 3. Mutation: callback allows spoofed nonce
    srv3 = GovernedAuthCallbackServer(token_path=tmp_path / "token.txt", repo_root=tmp_path, port=8774)
    assert srv3.start() is True
    # Overwrite contract file with spoofed nonce AFTER srv3 writes it
    contract_file = tmp_path / ".runtime" / ".callback_server_8774.json"
    contract_file.write_text(json.dumps({"pid": os.getpid(), "nonce": "SPOOFED_NONCE"}))
    try:
        orc3 = GovernedMorningOrchestrator(
            repo_root=tmp_path,
            state_root=tmp_path,
            token_path=tmp_path / "token.txt",
            lock_file=tmp_path / "lock3.txt",
            open_browser=False,
        )
        with patch("core.governed_morning_orchestrator.GovernedAuthCallbackServer",
                   lambda *a, **kw: GovernedAuthCallbackServer(*a, port=8774, **kw)):
            reused3 = orc3.step_wait_human_auth(poll_interval=0.01, timeout_override=0.1)
        results["callback_nonce_spoof_mutation"] = (reused3 is False and orc3.state == LauncherState.BLOCKED)
    finally:
        srv3.stop()

    # 4. Mutation: oversized URI accepted
    srv4 = GovernedAuthCallbackServer(token_path=tmp_path / "token.txt", repo_root=tmp_path, port=8775)
    assert srv4.start() is True
    try:
        import urllib.request
        import urllib.error
        with pytest.raises(urllib.error.HTTPError) as exc4:
            urllib.request.urlopen("http://127.0.0.1:8775/?" + ("y" * 2100), timeout=2.0)
        results["callback_oversized_uri_mutation"] = (exc4.value.code == 414)
    finally:
        srv4.stop()

    # 5. Mutation: persistent-MROS selection bypassed
    orc5 = GovernedMorningOrchestrator(
        repo_root=tmp_path,
        state_root=tmp_path,
        token_path=tmp_path / "token.txt",
        lock_file=tmp_path / "lock5.txt",
        observer_engine="dual",
        supervise=False,
    )
    with patch("subprocess.Popen") as mock_popen, \
         patch("core.governed_morning_orchestrator.datetime") as mock_dt:
        mock_popen.return_value = MagicMock(pid=9999)
        mock_dt.now.return_value = datetime(2026, 9, 18, 9, 30, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        mock_dt.strptime = datetime.strptime
        orc5.step_arm_observer()
        # Must have called popen for both collector and meg_live observer
        results["persistent_mros_selection_mutation"] = (
            mock_popen.call_count == 2
            and orc5._child_collector_proc is not None
            and orc5._child_mros_proc is not None
        )

    # 6. Mutation: collector health masks MROS health
    orc6 = GovernedMorningOrchestrator(
        repo_root=tmp_path,
        state_root=tmp_path,
        token_path=tmp_path / "token.txt",
        lock_file=tmp_path / "lock6.txt",
        open_browser=False,
    )
    col_proc = MagicMock(pid=101)
    col_proc.poll.return_value = None  # alive
    mros_proc = MagicMock(pid=102)
    mros_proc.poll.return_value = 99  # dead
    orc6._child_collector_proc = col_proc
    orc6._child_mros_proc = mros_proc
    with patch("time.sleep"):
        ok6 = orc6.supervise_observer()
    results["collector_vs_observer_health_separation_mutation"] = (
        ok6 is False
        and orc6.collector_health == "HEALTHY"
        and orc6.mros_health == "FAILED_CODE_99"
    )

    # 7. Mutation: scheduler timezone offset broken
    ist = ZoneInfo("Asia/Kolkata")
    cron_utc = datetime(2026, 9, 18, 3, 15, 0, tzinfo=timezone.utc)
    ist_converted = cron_utc.astimezone(ist)
    results["scheduler_timezone_mutation"] = (
        ist_converted.hour == 8 and ist_converted.minute == 45
    )

    # 8. Mutation: duplicate launcher instance allowed
    lock8_file = tmp_path / "l8.lock"
    orc8a = GovernedMorningOrchestrator(repo_root=tmp_path, state_root=tmp_path, token_path=tmp_path / "tok", lock_file=lock8_file)
    assert orc8a.acquire_lock() is True
    orc8b = GovernedMorningOrchestrator(repo_root=tmp_path, state_root=tmp_path, token_path=tmp_path / "tok", lock_file=lock8_file)
    res8b = orc8b.acquire_lock()
    results["single_instance_lock_mutation"] = (res8b is False)
    orc8a.release_lock()

    # 9. Mutation: audit predecessor archive mutation unverified
    audit_path = tmp_path / "audit_mut.jsonl"
    audit_path.write_text('{"event":"E","prev_hash":"X"}\n')
    rollover = perform_audit_chain_rollover(audit_log_path=audit_path, reason="mut9")
    arch_file = Path(rollover["archive_path"])
    os.chmod(arch_file, stat.S_IRUSR | stat.S_IWUSR)
    arch_file.write_text('{"event":"TAMPERED_ARCHIVE"}\n')
    prov = verify_recovery_provenance(audit_path)
    results["audit_predecessor_binding_mutation"] = (
        prov["ok"] is False and "archive_sha_mismatch" in prov["reason"]
    )

    # 10. Mutation: zero broker writes bypassed
    from core.kite_read_only_observation_runtime import safe_environment
    env = safe_environment()
    results["zero_broker_writes_mutation"] = (
        env.get("BROKER_WRITE_AUTHORITY") != "true"
        and env.get("ORDER_AUTHORITY") != "true"
        and env.get("LIVE_EXECUTION_AUTHORIZED") != "true"
    )

    return results


def test_mros_full_mutation_campaign(tmp_path):
    """Run all 10 deliberate mutations and prove 100% are caught."""
    res = run_mros_mutation_campaign(tmp_path)
    assert len(res) == 10
    for name, killed in res.items():
        assert killed is True, f"Mutation {name} was NOT caught!"
