from pathlib import Path

from core.upstox_instruments import resolve_upstox_key


def test_resolve_upstox_key_match_csv(tmp_path: Path):
    csv_path = tmp_path / "upstox_instruments.csv"
    csv_path.write_text(
        "instrument_key,underlying,expiry_date,strike_price,option_type\n"
        "NFO|BANKNIFTY26FEB61200CE,BANKNIFTY,2026-02-26,61200,CE\n"
    )
    row = {
        "underlying": "BANKNIFTY",
        "expiry_date": "2026-02-26",
        "strike": 61200,
        "option_type": "CE",
    }
    key = resolve_upstox_key(row, instruments_path=csv_path)
    assert key == "NFO|BANKNIFTY26FEB61200CE"
