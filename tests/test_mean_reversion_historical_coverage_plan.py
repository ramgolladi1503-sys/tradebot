import json
from pathlib import Path

def test_historical_coverage_plan_is_safe_and_chunked():
    path = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/historical_coverage_plan.json")
    if path.exists():
        with open(path, "r") as f:
            data = json.load(f)
            
        assert data.get("chunk_size_days") is not None
        assert data.get("chunk_size_days") <= 30
        assert data.get("resume_supported") is True
        assert data.get("fetched_market_data_committed") is False
        assert "token" not in str(data).lower()
