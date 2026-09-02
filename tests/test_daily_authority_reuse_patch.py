import json
from core.daily_instrument_authority import produce_authority

def _row(token, symbol):
    return {"exchange":"NSE","instrument_token":token,"tradingsymbol":symbol,"segment":"NSE","instrument_type":"EQ","expiry":"","lot_size":1,"tick_size":0.05,"strike":0}

def test_same_day_unchanged_reviewed_master_is_expected_on_restart(tmp_path):
    master=tmp_path/"m.json"; master.write_text(json.dumps([_row(256265,"NIFTY 50"), _row(2,"X")]))
    first=tmp_path/"a1.json"; second=tmp_path/"a2.json"; sha="a"*40
    prior=produce_authority(master_path=master, output_path=first, session_date="2026-09-01", source_sha=sha, required_tokens=[256265,2], reviewed_pass=True)
    resumed=produce_authority(master_path=master, output_path=second, session_date="2026-09-01", source_sha=sha, required_tokens=[256265,2], previous=prior)
    assert resumed["material_change_status"] == "EXPECTED"
    assert resumed["authority_verdict"] == "PASS"
