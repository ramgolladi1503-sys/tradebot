import pytest
import json
from pathlib import Path

def test_evidence_discovery(tmp_path, monkeypatch):
    import scripts.discover_simple_orb_phase_evidence as disc_mod
    monkeypatch.setattr(disc_mod, "Path", lambda p_str: tmp_path / p_str)
    
    # 1. No files found -> SIMPLE_ORB_PHASE_EVIDENCE_MISSING
    disc_mod.discover_evidence()
    
    inv_path = tmp_path / "runtime/strategy_validation/SIMPLE_ORB/simple_orb_phase_evidence_inventory.json"
    assert inv_path.exists()
    
    with open(inv_path) as f:
        inv = json.load(f)
        
    assert inv["discovery_classification"] == "SIMPLE_ORB_PHASE_EVIDENCE_MISSING"
    assert inv["usable_phase_count"] == 0
    assert inv["normalization_allowed"] is False
    
    # 2. Partial phase files -> SIMPLE_ORB_PHASE_EVIDENCE_FOUND_PARTIAL
    rep_dir = tmp_path / "reports/SIMPLE_ORB"
    rep_dir.mkdir(parents=True, exist_ok=True)
    
    with open(rep_dir / "phase_1_results.json", "w") as f:
        json.dump({"strategy_id": "SIMPLE_ORB", "phase": "phase_1", "passed": True}, f)
        
    disc_mod.discover_evidence()
    
    with open(inv_path) as f:
        inv = json.load(f)
        
    assert inv["discovery_classification"] == "SIMPLE_ORB_PHASE_EVIDENCE_FOUND_PARTIAL"
    assert inv["usable_phase_count"] == 1
    assert inv["normalization_allowed"] is False
    assert not (tmp_path / "runtime/strategy_validation/SIMPLE_ORB/phase_1_report.json").exists()
    
    # 3. Complete valid JSON evidence -> normalization allowed
    with open(rep_dir / "phase_2_results.json", "w") as f:
        json.dump({"strategy_id": "SIMPLE_ORB", "phase": "phase_2", "passed": True}, f)
    with open(rep_dir / "phase_3_results.json", "w") as f:
        json.dump({"strategy_id": "SIMPLE_ORB", "phase": "phase_3", "passed": True}, f)
    with open(rep_dir / "phase_3_5_results.json", "w") as f:
        json.dump({"strategy_id": "SIMPLE_ORB", "phase": "phase_3_5", "passed": True}, f)
    with open(rep_dir / "phase_4_results.json", "w") as f:
        json.dump({"strategy_id": "SIMPLE_ORB", "phase": "phase_4", "passed": True}, f)
    with open(rep_dir / "phase_5_wfa_results.json", "w") as f:
        json.dump({"strategy_id": "SIMPLE_ORB", "phase": "phase_5_wfa", "passed": True}, f)
        
    disc_mod.discover_evidence()
    
    with open(inv_path) as f:
        inv = json.load(f)
        
    assert inv["discovery_classification"] == "SIMPLE_ORB_PHASE_EVIDENCE_COMPLETE"
    assert inv["usable_phase_count"] == 6
    assert inv["normalization_allowed"] is True
    assert inv["paper_live_allowed"] is False
    
    # Check normalized reports
    for p in ["phase_1", "phase_2", "phase_3", "phase_3_5", "phase_4", "phase_5_wfa"]:
        norm_path = tmp_path / f"runtime/strategy_validation/SIMPLE_ORB/{p}_report.json"
        assert norm_path.exists()
        with open(norm_path) as f:
            norm = json.load(f)
        assert norm["normalization_type"] == "MIRROR_OF_EXISTING_EVIDENCE"
        assert norm["passed"] is True
        assert norm["paper_live_allowed"] is False
        assert norm["source_evidence_path"].endswith(f"{p}_results.json")
        assert norm["source_evidence_size"] > 0
        
    # Clear the generated normalized files so they don't count for the next assertions
    for p in ["phase_1", "phase_2", "phase_3", "phase_3_5", "phase_4", "phase_5_wfa"]:
        norm_path = tmp_path / f"runtime/strategy_validation/SIMPLE_ORB/{p}_report.json"
        if norm_path.exists():
            norm_path.unlink()
    
    # 4. Ambiguous strategy ID does not count
    with open(rep_dir / "phase_1_results.json", "w") as f:
        json.dump({"strategy_id": "OTHER_STRAT", "phase": "phase_1", "passed": True}, f)
    disc_mod.discover_evidence()
    with open(inv_path) as f:
        inv = json.load(f)
    assert inv["discovery_classification"] == "SIMPLE_ORB_PHASE_EVIDENCE_FOUND_PARTIAL"
    assert inv["usable_phase_count"] == 5
    
    # 5. Failed verdict does not count
    with open(rep_dir / "phase_1_results.json", "w") as f:
        json.dump({"strategy_id": "SIMPLE_ORB", "phase": "phase_1", "passed": False}, f)
    disc_mod.discover_evidence()
    with open(inv_path) as f:
        inv = json.load(f)
    assert inv["usable_phase_count"] == 5
