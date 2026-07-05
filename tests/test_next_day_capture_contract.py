import pytest
import json
from pathlib import Path

def test_validate_next_day_capture_contract(tmp_path, monkeypatch):
    import scripts.validate_next_day_capture_contract as val_mod
    monkeypatch.setattr(val_mod, "Path", lambda p_str: tmp_path / p_str if p_str in ["runtime/strategy_validation", "runtime/live_capture", "runtime", ".runtime", "data", "configs", "reports", "."] else Path(p_str))
    
    # 1. No capture dir
    val_mod.check_readiness()
    
    json_path = tmp_path / "runtime/strategy_validation/next_day_capture_contract_readiness.json"
    assert json_path.exists()
    
    with open(json_path) as f:
        data = json.load(f)
        
    assert data["classification"] == "NEXT_DAY_CAPTURE_CONTRACT_READY_BUT_DATA_MISSING"
    assert data["capture_ready"] is True
    assert data["data_available"] is False
    assert data["certification_replay_allowed"] is False
    assert "NEXT_DAY_CAPTURE_DATA_NOT_AVAILABLE_YET" in data["blockers"]
    
    assert data["execution_allowed"] is False
    assert data["paper_live_allowed"] is False
    assert data["live_allowed"] is False
    assert data["broker_order_allowed"] is False
    
    # 2. Add valid dir
    d = tmp_path / "runtime/live_capture/20260703"
    d.mkdir(parents=True)
    (d / "instrument_master").mkdir()
    (d / "ticks").mkdir()
    (d / "manifests").mkdir()
    
    (d / "instrument_master/kite_instruments_20260703.json").touch()
    (d / "ticks/option_ticks_20260703.parquet").touch()
    (d / "manifests/capture_manifest_20260703.json").touch()
    
    val_mod.check_readiness()
    
    with open(json_path) as f:
        data = json.load(f)
        
    assert data["classification"] == "NEXT_DAY_CAPTURE_CONTRACT_VALID"
    assert data["data_available"] is True
    assert data["certification_replay_allowed"] is True
    assert len(data["blockers"]) == 0
    assert data["execution_allowed"] is False
