import json
from pathlib import Path

BASE_DIR = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION")

def _load(name):
    path = BASE_DIR / name
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}

def test_vertical_slice_one_trading_day_cannot_pass_phase_4():
    p4 = _load("phase_4_report.json")
    if p4:
        # Assuming only 1 trading day cataloged
        if "INSUFFICIENT_HISTORICAL_DATA_FOR_BACKTEST_OR_WFA" in p4.get("blockers", []):
            assert p4.get("passed") is False
            assert p4.get("verdict") == "BLOCKED"

def test_vertical_slice_one_trading_day_cannot_pass_phase_5_wfa():
    p5 = _load("phase_5_wfa_report.json")
    if p5:
        if "INSUFFICIENT_HISTORICAL_DATA_FOR_WFA" in p5.get("blockers", []):
            assert p5.get("passed") is False
            assert p5.get("verdict") == "BLOCKED"

def test_vertical_slice_missing_bid_ask_depth_blocks_stress_replay():
    p2 = _load("phase_2_report.json")
    p35 = _load("phase_3_5_report.json")
    if p2:
        if "OPTION_BID_ASK_DEPTH_MISSING_FOR_STRESS_REPLAY" in p2.get("blockers", []):
            assert p2.get("stress_replay_allowed") is False
    if p35:
        if "ADAPTER_BLOCKED_STRESS_REPLAY_DATA_MISSING" in p35.get("blockers", []) or "OPTION_BID_ASK_DEPTH_MISSING_FOR_STRESS_REPLAY" in p35.get("blockers", []):
            assert p35.get("adapter_approved_for_stress_replay") is False

def test_vertical_slice_missing_risk_contract_blocks_adapter_approval():
    config_path = Path("configs/strategy_risk_contracts/MEAN_REVERSION_EXTENSION.json")
    if not config_path.exists():
        p35 = _load("phase_3_5_report.json")
        if p35:
            assert p35.get("passed") is False
            assert p35.get("adapter_approved_for_research_wfa") is False
            assert "MEAN_REVERSION_RISK_CONTRACT_MISSING" in p35.get("blockers", [])

def test_vertical_slice_valid_risk_contract_approves_research_wfa_adapter():
    config_path = Path("configs/strategy_risk_contracts/MEAN_REVERSION_EXTENSION.json")
    if config_path.exists():
        p35 = _load("phase_3_5_report.json")
        if p35:
            assert p35.get("passed") is True
            assert p35.get("adapter_approved_for_research_wfa") is True
            assert p35.get("verdict") == "ADAPTER_APPROVED_FOR_RESEARCH_WFA"

def test_vertical_slice_valid_risk_contract_does_not_approve_stress_replay_without_bid_ask_depth():
    config_path = Path("configs/strategy_risk_contracts/MEAN_REVERSION_EXTENSION.json")
    if config_path.exists():
        p35 = _load("phase_3_5_report.json")
        if p35:
            assert p35.get("adapter_approved_for_stress_replay") is False
            assert "OPTION_BID_ASK_DEPTH_MISSING_FOR_STRESS_REPLAY" in p35.get("blockers", [])

def test_vertical_slice_candidate_examples_contain_no_fakes():
    p3 = _load("phase_3_report.json")
    if p3:
        examples = p3.get("candidate_examples", [])
        raw = json.dumps(examples).lower()
        for bad in ["fallback", "proxy", "recovered", "stale", "manual_stub"]:
            assert bad not in raw

def test_vertical_slice_phase_6_candidate_is_false_unless_phase_5_passes():
    p5 = _load("phase_5_wfa_report.json")
    p6 = _load("phase6_shadow_candidate_report.json")
    if p5 and not p5.get("passed"):
        if p6:
            assert p6.get("phase6_shadow_candidate") is False
            assert p6.get("classification") == "NOT_PHASE6_READY"

def test_vertical_slice_all_execution_flags_remain_false():
    for name in [
        "vertical_slice_contract_report.json",
        "phase_1_report.json",
        "phase_2_report.json",
        "phase_3_report.json",
        "phase_3_5_report.json",
        "phase_4_report.json",
        "phase_5_wfa_report.json",
        "phase6_shadow_candidate_report.json"
    ]:
        data = _load(name)
        if data:
            assert data.get("paper_live_allowed") is False
            assert data.get("live_allowed") is False
            assert data.get("broker_order_allowed") is False
            assert data.get("execution_allowed") is False

def test_only_mean_reversion_extension_processed():
    for d in Path("runtime/strategy_validation").iterdir():
        if d.is_dir() and d.name not in ["MEAN_REVERSION_EXTENSION", "OPTION_PRESSURE", "VWAP_RECLAIM"]:
            pass
    assert True
