import json
from pathlib import Path

def test_historical_data_capability():
    cap_path = Path("runtime/strategy_validation/historical_data_capability.json")
    if cap_path.exists():
        with open(cap_path, "r") as f:
            data = json.load(f)
        if data.get("is_candle_only"):
            assert not data.get("execution_grade_stress_replay_possible")
        assert "token_value" not in str(data)
