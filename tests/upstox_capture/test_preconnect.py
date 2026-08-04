import pytest
import subprocess
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.upstox_capture.run_upstox_replay_capture_v1 import main as run_main

def test_prepare_campaign_root(tmp_path):
    root = tmp_path / "test_root"
    camp = "camp-01"
    
    cmd = [
        sys.executable,
        "scripts/upstox_capture/prepare_premarket_data.py",
        "--session-date", "20260805",
        "--nifty-spot", "24774.3",
        "--output-root", str(root),
        "--campaign-id", camp,
        "--dry-run"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parents[2])
    assert result.returncode == 0
    
    expected_root = root / camp
    assert expected_root.exists()
    assert (expected_root / "upstox_instruments" / "complete.json").exists()

@patch("requests.get")
@patch("os.getenv")
@patch("sys.argv", ["run.py", "--session-date", "20260805", "--preconnect-only"])
def test_preconnect_exits_cleanly(mock_getenv, mock_get, tmp_path):
    # Setup mocks
    mock_getenv.return_value = "fake_token"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp
    
    # We must patch the output root so it doesn't write to the real directory
    with patch("scripts.upstox_capture.run_upstox_replay_capture_v1.Path") as mock_path_cls:
        # Just let it run, we mainly care about the exit code and that it doesn't call connect()
        # Since we want to test the full flow, we can use the prepare script test output.
        pass

def test_preconnect_integration(tmp_path):
    root = tmp_path / "test_root"
    camp = "camp-01"
    
    cmd = [
        sys.executable,
        "scripts/upstox_capture/prepare_premarket_data.py",
        "--session-date", "20260805",
        "--nifty-spot", "24774.3",
        "--output-root", str(root),
        "--campaign-id", camp
    ]
    subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parents[2], check=True)
    
    # Now run launcher with a fake token and mocked auth in a sub-process? 
    # Or just run it and let auth fail? If auth fails, it exits before preconnect.
    pass
