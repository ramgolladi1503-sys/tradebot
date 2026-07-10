import json
import pytest
from pathlib import Path

def test_upstox_underlying_ohlc_classification(tmp_path, monkeypatch):
    import scripts.report_candidate_replay_data_sources as report_mod
    monkeypatch.chdir(tmp_path)
    report_mod.generate_report()
    
    with open("runtime/strategy_validation/candidate_replay_data_source_decision_report.json") as f:
        data = json.load(f)
        
    for item in data:
        if item["source"] == "UPSTOX_UNDERLYING_OHLC":
            assert item["usable_for_setup_reconstruction"] is True
            assert item["usable_for_stress_replay"] is False
            assert item["certifiable_for_candidate_replay"] is False
            assert "DATA_BLOCKED_UNDERLYING_ONLY_NO_OPTION_TRUTH" in item["blockers"]

def test_upstox_option_ohlc_not_stress_certifiable(tmp_path, monkeypatch):
    import scripts.report_candidate_replay_data_sources as report_mod
    monkeypatch.chdir(tmp_path)
    report_mod.generate_report()
    
    with open("runtime/strategy_validation/candidate_replay_data_source_decision_report.json") as f:
        data = json.load(f)
        
    for item in data:
        if item["source"] == "UPSTOX_OPTION_OHLC":
            assert item["usable_for_stress_replay"] is False
            assert item["certifiable_for_candidate_replay"] is False
            assert "DATA_BLOCKED_OPTION_OHLC_NO_SPREAD_TRUTH" in item["blockers"]
            assert item["usable_for_option_candle_replay"] is True

def test_live_captured_depth_stress_capable(tmp_path, monkeypatch):
    import scripts.report_candidate_replay_data_sources as report_mod
    monkeypatch.chdir(tmp_path)
    report_mod.generate_report()
    
    with open("runtime/strategy_validation/candidate_replay_data_source_decision_report.json") as f:
        data = json.load(f)
        
    for item in data:
        if item["source"] == "LIVE_CAPTURED_OPTION_DEPTH":
            assert item["has_bid_ask_spread_truth"] is True
            assert item["has_depth_truth"] is True
            assert item["usable_for_stress_replay"] is True
            assert item["certifiable_for_candidate_replay"] is True

def test_synthetic_sources_always_non_certifiable(tmp_path, monkeypatch):
    import scripts.report_candidate_replay_data_sources as report_mod
    monkeypatch.chdir(tmp_path)
    report_mod.generate_report()
    
    with open("runtime/strategy_validation/candidate_replay_data_source_decision_report.json") as f:
        data = json.load(f)
        
    for item in data:
        if item["source"] in ["FIXTURE_DATA", "MOCK_DATA", "SYNTHETIC_DATA", "PROXY_DATA"]:
            assert item["usable_for_setup_reconstruction"] is False
            assert item["usable_for_stress_replay"] is False
            assert item["certifiable_for_candidate_replay"] is False
            assert "DATA_BLOCKED_STRESS_REPLAY_UNSUPPORTED_BY_DATA_CAPABILITY" in item["blockers"]

def test_report_stable_blocker_codes(tmp_path, monkeypatch):
    import scripts.report_candidate_replay_data_sources as report_mod
    monkeypatch.chdir(tmp_path)
    report_mod.generate_report()
    
    with open("runtime/strategy_validation/candidate_replay_data_source_decision_report.json") as f:
        data = json.load(f)
        
    for item in data:
        for blocker in item["blockers"]:
            assert blocker.startswith("DATA_BLOCKED_")

def test_no_token_requirement(tmp_path, monkeypatch):
    import scripts.report_candidate_replay_data_sources as report_mod
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    # Should run without error
    report_mod.generate_report()
    assert Path("runtime/strategy_validation/candidate_replay_data_source_decision_report.json").exists()

def test_no_execution_permissions_true(tmp_path, monkeypatch):
    import scripts.report_candidate_replay_data_sources as report_mod
    monkeypatch.chdir(tmp_path)
    report_mod.generate_report()
    
    with open("runtime/strategy_validation/candidate_replay_data_source_decision_report.json") as f:
        data = json.load(f)
        
    for item in data:
        assert item.get("live_allowed", False) is False
        assert item.get("paper_live_allowed", False) is False
        assert item.get("broker_order_allowed", False) is False
        assert item.get("execution_allowed", False) is False
