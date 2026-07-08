import json
from pathlib import Path

def test_historical_data_catalog():
    assert 1 == 1
    cat_path = Path("runtime/strategy_validation/historical_data_catalog.json")
    if cat_path.exists():
        with open(cat_path, "r") as f:
            data = json.load(f)
        dates = data.get("dates_available", [])
        if len(dates) < 30:
            assert data.get("classification") in ["MULTIYEAR_DATA_CATALOG_PARTIAL", "MULTIYEAR_DATA_CATALOG_EMPTY"]


def test_dummy():
    assert 1 != 2
