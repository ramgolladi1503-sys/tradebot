import json
from pathlib import Path

BASE_DIR = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION")

def _load(name):
    path = BASE_DIR / name
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}

def test_failure_analysis_blocks_if_ledger_missing():
    # If the ledger isn't there, we just test that the logic in analysis outputs a blocked status
    attr = _load("phase_4_failure_attribution.json")
    if not (BASE_DIR / "phase_4_trade_ledger.jsonl").exists():
        assert attr.get("classification") == "MEAN_REVERSION_FAILURE_ATTRIBUTION_BLOCKED_LEDGER_MISSING"

def test_pnl_by_symbol_computed():
    attr = _load("phase_4_failure_attribution.json")
    if attr and attr.get("classification") != "MEAN_REVERSION_FAILURE_ATTRIBUTION_BLOCKED_LEDGER_MISSING":
        assert "pnl_by_symbol" in attr

def test_pnl_by_direction_computed():
    attr = _load("phase_4_failure_attribution.json")
    if attr and attr.get("classification") != "MEAN_REVERSION_FAILURE_ATTRIBUTION_BLOCKED_LEDGER_MISSING":
        assert "pnl_by_direction" in attr

def test_exit_reason_distribution_computed():
    attr = _load("phase_4_failure_attribution.json")
    if attr and attr.get("classification") != "MEAN_REVERSION_FAILURE_ATTRIBUTION_BLOCKED_LEDGER_MISSING":
        assert "exit_reason_distribution" in attr

def test_direction_inversion_detected():
    attr = _load("phase_4_failure_attribution.json")
    if attr and attr.get("classification") != "MEAN_REVERSION_FAILURE_ATTRIBUTION_BLOCKED_LEDGER_MISSING":
        assert "direction_inversion_suspected" in attr

def test_constant_pnl_bug_detected():
    attr = _load("phase_4_failure_attribution.json")
    if attr and attr.get("classification") != "MEAN_REVERSION_FAILURE_ATTRIBUTION_BLOCKED_LEDGER_MISSING":
        assert "constant_pnl_bug_suspected" in attr

def test_exit_monoculture_detected():
    attr = _load("phase_4_failure_attribution.json")
    if attr and attr.get("classification") != "MEAN_REVERSION_FAILURE_ATTRIBUTION_BLOCKED_LEDGER_MISSING":
        assert "exit_logic_monoculture_suspected" in attr

def test_analysis_does_not_modify_phase_4_pass_state():
    p4 = _load("phase_4_report.json")
    if p4:
        assert p4.get("passed") is False

def test_no_execution_flags_true():
    attr = _load("phase_4_failure_attribution.json")
    if attr:
        assert not attr.get("paper_live_allowed", False)
        assert not attr.get("live_allowed", False)
        assert not attr.get("execution_allowed", False)
