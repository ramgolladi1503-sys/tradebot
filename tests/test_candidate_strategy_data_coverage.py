import json
from pathlib import Path

def test_candidate_strategy_data_coverage():
    report_path = Path("runtime/strategy_validation/OPTION_PRESSURE/phase_2_report.json")
    if report_path.exists():
        with open(report_path, "r") as f:
            data = json.load(f)
        if "Missing bid/ask and depth" in data.get("blockers", []):
            assert data.get("verdict") == "BLOCKED"
        assert not data.get("stress_replay_allowed")
