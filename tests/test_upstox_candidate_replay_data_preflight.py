import os
import json
import pytest
from pathlib import Path
from scripts.preflight_upstox_candidate_replay_data import main

def test_token_preflight_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("UPSTOX_API_KEY", raising=False)
    monkeypatch.delenv("UPSTOX_API_SECRET", raising=False)
    
    main()
    
    report_file = Path("runtime/strategy_validation/upstox_candidate_replay_data_preflight.json")
    assert report_file.exists()
    
    with open(report_file) as f:
        data = json.load(f)
        
    assert data["token_present"] is False
    assert "UPSTOX_ACCESS_TOKEN_MISSING" in data["blockers"]
    assert data["classification"] == "UPSTOX_CANDIDATE_REPLAY_DATA_PREFLIGHT_BLOCKED"

def test_missing_date_range_blocks(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "fake_token")
    monkeypatch.delenv("UPSTOX_FETCH_START_DATE", raising=False)
    monkeypatch.delenv("UPSTOX_FETCH_END_DATE", raising=False)
    
    main()
    
    with open("runtime/strategy_validation/upstox_candidate_replay_data_preflight.json") as f:
        data = json.load(f)
        
    assert "UPSTOX_FETCH_DATE_RANGE_MISSING" in data["blockers"]
    assert data["classification"] == "UPSTOX_CANDIDATE_REPLAY_DATA_PREFLIGHT_BLOCKED"

def test_no_safety_flags_leaked(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main()
    with open("runtime/strategy_validation/upstox_candidate_replay_data_preflight.json") as f:
        data = json.load(f)
        
    assert data["paper_live_allowed"] is False
    assert data["live_allowed"] is False
    assert data["broker_order_allowed"] is False
    assert data["execution_allowed"] is False
    assert data["token_value_logged"] is False
