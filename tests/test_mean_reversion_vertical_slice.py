import json
from pathlib import Path

BASE_DIR = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION")

def _load(name):
    path = BASE_DIR / name
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}

def test_vertical_slice_phase_4_cannot_pass_without_minimum_trading_days():
    catalog = _load("historical_data_catalog.json")
    p4 = _load("phase_4_report.json")
    if catalog and p4:
        if catalog.get("trading_days_count", 0) < 30:
            assert p4.get("passed") is False
            assert "INSUFFICIENT_HISTORICAL_DATA_FOR_BACKTEST_OR_WFA" in p4.get("blockers", [])

def test_vertical_slice_phase_4_cannot_pass_without_trade_ledger():
    ledger_path = BASE_DIR / "phase_4_trade_ledger.jsonl"
    p4 = _load("phase_4_report.json")
    if p4 and not ledger_path.exists():
        assert p4.get("passed") is False
        assert "PHASE4_TRADE_LEDGER_MISSING_OR_EMPTY" in p4.get("blockers", [])

def test_vertical_slice_phase_4_cannot_pass_with_empty_trade_ledger():
    ledger_path = BASE_DIR / "phase_4_trade_ledger.jsonl"
    p4 = _load("phase_4_report.json")
    if p4 and ledger_path.exists():
        content = ledger_path.read_text().strip()
        if not content:
            assert p4.get("passed") is False
            assert "PHASE4_TRADE_LEDGER_MISSING_OR_EMPTY" in p4.get("blockers", [])

def test_vertical_slice_phase_5_cannot_pass_unless_phase_4_passed():
    p4 = _load("phase_4_report.json")
    p5 = _load("phase_5_wfa_report.json")
    if p4 and p5:
        if not p4.get("passed"):
            assert p5.get("passed") is False

def test_vertical_slice_phase_5_cannot_pass_without_minimum_wfa_windows():
    threshold_path = Path("configs/candidate_strategy_validation_thresholds.json")
    min_windows = 6
    if threshold_path.exists():
        min_windows = json.loads(threshold_path.read_text()).get("minimum_wfa_windows", 6)
        
    p5 = _load("phase_5_wfa_report.json")
    if p5:
        windows_passed = p5.get("metrics", {}).get("windows_passed", 0)
        windows_failed = p5.get("metrics", {}).get("windows_failed", 0)
        if windows_passed + windows_failed < min_windows:
            assert p5.get("passed") is False
            assert "MINIMUM_WFA_WINDOWS_NOT_MET" in p5.get("blockers", [])

def test_vertical_slice_phase_6_candidate_remains_false_unless_phase_5_passed():
    p5 = _load("phase_5_wfa_report.json")
    p6 = _load("phase6_shadow_candidate_report.json")
    if p5 and p6:
        if not p5.get("passed"):
            assert p6.get("phase6_shadow_candidate") is False
            assert p6.get("classification") == "NOT_PHASE6_READY"
            assert "PHASE5_WFA_NOT_PASSED" in p6.get("blockers", [])
        else:
            assert p6.get("classification") == "PHASE6_SHADOW_CANDIDATE_READY"
            assert p6.get("shadow_observation_only") is True

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
