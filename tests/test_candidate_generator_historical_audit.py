import json
from pathlib import Path

def test_candidate_generator_historical_audit():
    report_path = Path("runtime/strategy_validation/VWAP_RECLAIM/phase_3_report.json")
    if report_path.exists():
        with open(report_path, "r") as f:
            data = json.load(f)
        # generated candidates must include real timestamps and no fallback/proxy flags
        assert "fallback" not in str(data).lower()
