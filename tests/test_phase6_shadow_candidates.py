import json
from pathlib import Path

def test_phase6_shadow_candidates():
    report_path = Path("runtime/strategy_validation/phase6_shadow_candidates_for_next_live_capture.json")
    if report_path.exists():
        with open(report_path, "r") as f:
            data = json.load(f)
        if len(data.get("strategies", [])) == 0:
            assert data.get("classification") == "PHASE6_SHADOW_CANDIDATES_EMPTY"
        for s in data.get("strategies", []):
            assert s.get("paper_live_allowed") is False
