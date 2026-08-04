import pytest
import subprocess
import sys
import json
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.upstox_capture.run_upstox_replay_capture_v1 import main as run_main

def test_executable_preconnect_cleanup(tmp_path):
    root = tmp_path / "test_root"
    camp = "camp-01"
    
    # 1. Create a valid temporary premarket manifest
    cmd = [
        sys.executable,
        "scripts/upstox_capture/prepare_premarket_data.py",
        "--session-date", "20260805",
        "--nifty-spot", "24774.3",
        "--output-root", str(root),
        "--campaign-id", camp,
        "--dry-run"
    ]
    subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parents[2], check=True)
    
    expected_root = root / camp
    
    # 2 & 3. Patch auth and connect
    with patch("scripts.upstox_capture.run_upstox_replay_capture_v1.preflight_auth", return_value=True) as mock_auth, \
         patch("scripts.upstox_capture.run_upstox_replay_capture_v1.ReplayQualityStreamer.connect") as mock_connect, \
         patch.dict("os.environ", {"UPSTOX_ACCESS_TOKEN": "mock_token"}), \
         patch("sys.argv", [
             "run.py", 
             "--session-date", "20260805", 
             "--campaign-id", camp, 
             "--output-root", str(root),
             "--preconnect-only"
         ]):
        
        # 4. Call main and expect exit 0
        with pytest.raises(SystemExit) as exc_info:
            run_main()
            
        assert exc_info.value.code == 0
        mock_connect.assert_not_called()
        
        # 5. Assert Lifecycle and Writer states
        lifecycle_file = expected_root / "lifecycle" / "session_lifecycle.jsonl"
        assert lifecycle_file.exists()
        
        events = []
        with open(lifecycle_file, "r") as f:
            for line in f:
                events.append(json.loads(line))
                
        event_types = [e["event_type"] for e in events]
        assert "PRECONNECT_PASS" in event_types
        assert "SESSION_REJECTED" not in event_types
        assert "NEVER_OBSERVED" not in event_types
        
        # Check Reconciliation 
        preconnect_event = [e for e in events if e["event_type"] == "PRECONNECT_PASS"][0]
        reconciliation = preconnect_event["reconciliation"]
        assert reconciliation["reconciled"] is True
        
        # We know there are 50 constituents, NIFTY 50, NIFTY FUT, plus options.
        # But wait, prepare script ran with dry-run? No, dry-run means it doesn't do something else, but it creates files. 
        # Actually it creates the plan. Let's verify counts directly from the plan.
        plan_path = expected_root / "subscription" / "universe_plan.json"
        with open(plan_path, "r") as f:
            plan = json.load(f)
            
        assert len(plan["full"]) == 126
        assert len(plan.get("ltpc", [])) == 0
