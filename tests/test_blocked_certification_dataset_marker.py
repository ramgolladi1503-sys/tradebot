import pytest
import json
from pathlib import Path

def test_mark_blocked_certification_dataset(tmp_path, monkeypatch):
    import scripts.mark_blocked_certification_dataset as mark_mod
    monkeypatch.setattr(mark_mod, "Path", lambda p_str: tmp_path / p_str if p_str in ["runtime/strategy_validation", "runtime", ".runtime", "data", "configs", "reports", "."] else Path(p_str))
    
    mark_mod.mark_blocked()
    
    json_path = tmp_path / "runtime/strategy_validation/blocked_datasets.json"
    assert json_path.exists()
    
    with open(json_path) as f:
        data = json.load(f)[0]
        
    assert data["certification_allowed"] is False
    assert data["candidate_replay_allowed"] is False
    assert data["allowed_use"] == "RESEARCH_DEBUG_ONLY"
    assert data["execution_allowed"] is False
    assert data["paper_live_allowed"] is False
    assert data["live_allowed"] is False
    assert data["broker_order_allowed"] is False
    
    assert "FILTERED_DATASET_INSTRUMENT_MASTER_DATE_UNKNOWN" in data["blockers"]
    assert "FILTERED_DATASET_SPREAD_OUTLIER_RATE_TOO_HIGH" in data["blockers"]
    
