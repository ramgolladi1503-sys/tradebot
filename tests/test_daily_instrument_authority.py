import json
from pathlib import Path
import pytest
from core.daily_instrument_authority import independent_verify, produce_authority, validate_authority

def row(token=1, symbol="X", expiry="", lot=1):
    return {"exchange":"NSE","instrument_token":token,"tradingsymbol":symbol,"segment":"NSE","instrument_type":"EQ","expiry":expiry,"lot_size":lot,"tick_size":0.05,"strike":0}

def valid(): return [row(256265,"NIFTY 50"), row(2,"X")]

def test_independent_verifier_passes_required_tokens():
    assert independent_verify(valid(), [256265,2])["independent_verifier_status"] == "PASS"

@pytest.mark.parametrize("mutator", [lambda x:x[:-1], lambda x:x+[row(2,"Y")], lambda x:(x.__setitem__(0,{**x[0],"tradingsymbol":"BAD"}) or x), lambda x:(x.__setitem__(1,{**x[1],"lot_size":0}) or x)])
def test_invalid_or_material_master_fails(mutator):
    data=mutator(valid()); assert independent_verify(data,[256265,2])["independent_verifier_status"] == "FAIL"

def test_unknown_material_change_cannot_authorize(tmp_path):
    master=tmp_path/"m.json"; master.write_text(json.dumps(valid())); out=tmp_path/"a.json"
    result=produce_authority(master_path=master,output_path=out,session_date="2026-09-01",source_sha="a"*40,required_tokens=[256265,2])
    assert result["authority_verdict"] == "FAIL"

def test_reviewed_artifact_validates_and_tampering_fails(tmp_path):
    master=tmp_path/"m.json"; master.write_text(json.dumps(valid())); out=tmp_path/"a.json"; sha="a"*40
    result=produce_authority(master_path=master,output_path=out,session_date="2026-09-01",source_sha=sha,required_tokens=[256265,2],reviewed_pass=True)
    assert validate_authority(artifact_path=out,master_path=master,session_date="2026-09-01",source_sha=sha,required_tokens=[256265,2])["ok"]
    data=json.loads(out.read_text()); data["raw_master_sha256"]="0"*64; out.write_text(json.dumps(data)); assert not validate_authority(artifact_path=out,master_path=master,session_date="2026-09-01",source_sha=sha,required_tokens=[256265,2])["ok"]

def test_dated_artifact_cannot_overwrite(tmp_path):
    m=tmp_path/"m"; m.write_text(json.dumps(valid())); o=tmp_path/"a"
    produce_authority(master_path=m,output_path=o,session_date="2026-09-01",source_sha="a",required_tokens=[256265,2],reviewed_pass=True)
    with pytest.raises(FileExistsError): produce_authority(master_path=m,output_path=o,session_date="2026-09-01",source_sha="a",required_tokens=[256265,2],reviewed_pass=True)
