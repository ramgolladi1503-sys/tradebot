import json
from pathlib import Path

def test_candidate_strategy_wfa():
    report_path = Path("runtime/strategy_validation/VWAP_RECLAIM/phase_5_wfa_report.json")
    if report_path.exists():
        with open(report_path, "r") as f:
            data = json.load(f)
        blockers = data.get("blockers", [])
        if "INSUFFICIENT_HISTORICAL_DATA_FOR_WFA" in blockers:
            assert data.get("passed") is False
            assert data.get("phase6_shadow_candidate") is False
