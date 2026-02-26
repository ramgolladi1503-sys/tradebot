import json
from pathlib import Path

from core.upstox_resolver import resolve_upstox_key


def test_resolve_upstox_key_match(tmp_path: Path):
    data = [
        {
            "instrument_key": "NFO|BANKNIFTY26FEB61200CE",
            "underlying": "BANKNIFTY",
            "expiry": "2026-02-26",
            "strike_price": 61200,
            "option_type": "CE",
        }
    ]
    path = tmp_path / "upstox_instruments.json"
    path.write_text(json.dumps(data))
    row = {
        "underlying": "BANKNIFTY",
        "expiry_date": "2026-02-26",
        "strike": 61200,
        "option_type": "CE",
    }
    key = resolve_upstox_key(row, instruments_path=path)
    assert key == "NFO|BANKNIFTY26FEB61200CE"
