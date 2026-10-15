"""
Continuous OS Subprocess Integration and Live WAL Mutation Acceptance Harness.

Proves:
1. Observer runs as a distinct OS subprocess against isolated WAL fixtures.
2. WAL is mutated while observer is running (appending active proposal payload, then completed exit).
3. Evaluator transitions from IN_FLIGHT_OPEN (PROSPECTIVE_OBSERVED) to COMPLETED_EVALUABLE across cycles.
4. Clean shutdown via SIGINT/SIGTERM flushes snapshot cleanly.
5. Process restarts and recovers identical state without duplicate proposals or duplicate exits.
"""

import os
import sys
import time
import json
import signal
import subprocess
import pytest
from datetime import datetime

# Repository-relative path resolution
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
RUNNER_SCRIPT = os.path.join(REPO_ROOT, "scripts", "run_prospective_shadow_observer.py")

def test_live_os_subprocess_wal_mutation_and_restart_recovery(tmp_path):
    test_nifty_wal = str(tmp_path / "test_dynamic_nifty_wal.json")
    test_sensex_wal = str(tmp_path / "test_dynamic_sensex_wal.json")
    test_state_path = str(tmp_path / "test_dynamic_observer_state.json")
    
    # Initialize base empty WAL fixtures in isolated tmp_path
    initial_wal = {
        "state": "IDLE",
        "payload": None,
        "last_completed_trade": None,
        "trade_history": []
    }
    with open(test_nifty_wal, "w") as f:
        json.dump(initial_wal, f)
    with open(test_sensex_wal, "w") as f:
        json.dump(initial_wal, f)

    env = os.environ.copy()
    env["SHADOW_NIFTY_WAL_PATH"] = test_nifty_wal
    env["SHADOW_SENSEX_WAL_PATH"] = test_sensex_wal
    env["SHADOW_STATE_PATH"] = test_state_path
    env["SHADOW_ALLOW_FRESH_INIT"] = "true"
    env["SHADOW_POLL_INTERVAL_SEC"] = "0.2"
    # Unset iteration cap to ensure true continuous daemon mode
    env.pop("SHADOW_MAX_POLL_ITERATIONS", None)
    env.pop("SHADOW_POLL_ITERATIONS", None)
    
    # 1. Spawn Observer as a separate OS subprocess
    proc = subprocess.Popen(
        [sys.executable, RUNNER_SCRIPT],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    try:
        # Allow process to start and complete initial backfill pass
        time.sleep(0.6)
        assert proc.poll() is None, "Observer process exited prematurely!"
        
        # 2. Mutate WAL while process is running: Append active open position in payload
        # Ensure timestamp is within clock skew window (now)
        now_iso = datetime.now().isoformat()
        open_trade = {
            "position_id": "TRADE_LIVE_100",
            "direction": "CE",
            "strike_contract": "NIFTY 23000 CE",
            "entry_time": now_iso,
            "entry_price": 23050.0
        }
        wal_with_open = {
            "state": "ARMED",
            "payload": open_trade,
            "last_completed_trade": None,
            "trade_history": []
        }
        with open(test_nifty_wal, "w") as f:
            json.dump(wal_with_open, f)
            
        # Give observer time to poll and ingest open trade
        time.sleep(0.8)
        assert os.path.exists(test_state_path), "Observer failed to persist state snapshot!"
        
        with open(test_state_path, "r") as f:
            st1 = json.load(f)
            
        session_date = now_iso[:10]
        scoped_key = f"NIFTY::{session_date}::TRADE_LIVE_100"
        assert scoped_key in st1.get("in_flight_positions", {}), "Open trade not captured in in_flight_positions!"
        prop_rec = st1["proposal_registry"][scoped_key]
        assert prop_rec["provenance_mode"] == "PROSPECTIVE_OBSERVED", "Open trade must be PROSPECTIVE_OBSERVED!"
        assert prop_rec["lifecycle_state"] == "IN_FLIGHT_OPEN"
        assert len(st1.get("shadow_ledger", [])) == 0, "No exits should be in ledger yet!"
        
        # 3. Mutate WAL while process is running: Complete the trade and move to trade_history
        completed_trade = {
            "position_id": "TRADE_LIVE_100",
            "direction": "CE",
            "strike_contract": "NIFTY 23000 CE",
            "entry_time": now_iso,
            "exit_time": datetime.now().isoformat(),
            "exit_reason": "TARGET_HIT",
            "pnl_pts": 15.0,
            "opt_pnl_pts": 8.5,
            "opt_bid": 120.0,
            "opt_ask": 120.5
        }
        wal_completed = {
            "state": "LIQUIDATED",
            "payload": None,
            "last_completed_trade": completed_trade,
            "trade_history": [completed_trade]
        }
        with open(test_nifty_wal, "w") as f:
            json.dump(wal_completed, f)
            
        # Allow observer to poll and ingest exit
        time.sleep(0.8)
        
        with open(test_state_path, "r") as f:
            st2 = json.load(f)
            
        assert scoped_key not in st2.get("in_flight_positions", {}), "Completed trade must be removed from in_flight!"
        assert len(st2.get("shadow_ledger", [])) == 1, "Exit must be recorded in shadow_ledger!"
        exit_rec = st2["shadow_ledger"][0]
        assert exit_rec["position_id"] == "TRADE_LIVE_100"
        assert exit_rec["provenance_mode"] == "PROSPECTIVE_OBSERVED", "Exit must be PROSPECTIVE_OBSERVED since proposal was seen prior!"
        assert exit_rec["lifecycle_state"] == "COMPLETED_EVALUABLE"
        
        # 4. Graceful termination via SIGINT
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=3)
        assert proc.returncode == 0, f"Process did not exit cleanly on SIGINT: returncode={proc.returncode}"
        
        # 5. Restart process to verify crash/restart idempotency and no duplicate accounting
        proc2 = subprocess.Popen(
            [sys.executable, RUNNER_SCRIPT],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        time.sleep(0.8)
        proc2.send_signal(signal.SIGINT)
        proc2.wait(timeout=3)
        assert proc2.returncode == 0
        
        with open(test_state_path, "r") as f:
            st3 = json.load(f)
            
        assert len(st3.get("shadow_ledger", [])) == 1, "Ledger count must remain exactly 1 across restart!"
        assert len(st3.get("proposal_registry", {})) == 1, "Proposal count must remain exactly 1 across restart!"
        
    finally:
        if proc.poll() is None:
            proc.kill()
