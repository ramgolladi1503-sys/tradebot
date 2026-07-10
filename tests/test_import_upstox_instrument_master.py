import json
import os
import pytest
from pathlib import Path

def test_import_blocks_missing_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from scripts import import_upstox_instrument_master
    
    # Run script with no file present
    import_upstox_instrument_master.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_master_import.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_INSTRUMENT_MASTER_IMPORT_BLOCKED_FILE_MISSING"
        assert not data["certification_eligible"]

def test_import_blocks_malformed_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from scripts import import_upstox_instrument_master
    
    Path("data/manual/upstox_instruments").mkdir(parents=True, exist_ok=True)
    p_in = Path("data/manual/upstox_instruments/complete.json")
    with open(p_in, "w") as f:
        f.write("not json")
        
    import_upstox_instrument_master.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_master_import.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_INSTRUMENT_MASTER_IMPORT_BLOCKED_MALFORMED"

def test_import_blocks_no_instrument_keys(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from scripts import import_upstox_instrument_master
    
    Path("data/manual/upstox_instruments").mkdir(parents=True, exist_ok=True)
    p_in = Path("data/manual/upstox_instruments/complete.json")
    with open(p_in, "w") as f:
        json.dump([{"some_other_key": "val"}], f)
        
    import_upstox_instrument_master.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_master_import.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_INSTRUMENT_MASTER_IMPORT_BLOCKED_NO_INSTRUMENT_KEYS"

def test_import_accepts_valid_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from scripts import import_upstox_instrument_master
    
    Path("data/manual/upstox_instruments").mkdir(parents=True, exist_ok=True)
    p_in = Path("data/manual/upstox_instruments/complete.json")
    with open(p_in, "w") as f:
        json.dump([{"instrument_key": "abc", "tradingsymbol": "NIFTY 50"}], f)
        
    import_upstox_instrument_master.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_master_import.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_INSTRUMENT_MASTER_IMPORTED"
        assert data["certification_eligible"] is True
        assert data["row_count"] == 1
        assert data["file_hash"] is not None
        
    p_out = Path("runtime/upstox_instruments/complete.json")
    assert p_out.exists()
