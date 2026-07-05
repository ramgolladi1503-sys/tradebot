import pytest
import json
from pathlib import Path
from dataclasses import dataclass

@dataclass
class MockRegistryEntry:
    strategy_id: str
    strategy_kind: str

def test_phase6_eligibility_audit(tmp_path, monkeypatch):
    import scripts.audit_phase6_eligibility as audit_mod
    monkeypatch.setattr(audit_mod, "Path", lambda p_str: tmp_path / p_str if p_str.startswith("runtime/strategy_validation") else Path(p_str))
    
    def mock_load_registry():
        return {
            "SIMPLE_ORB": MockRegistryEntry("SIMPLE_ORB", "execution_signal_strategy"),
            "HTF_OPENING_DRIVE_CONT": MockRegistryEntry("HTF_OPENING_DRIVE_CONT", "execution_signal_strategy"),
            "MEAN_REVERSION_EXTENSION": MockRegistryEntry("MEAN_REVERSION_EXTENSION", "candidate_generator_strategy"),
            "PRO_STRATEGY_ENGINE": MockRegistryEntry("PRO_STRATEGY_ENGINE", "aggregate_engine")
        }
    monkeypatch.setattr(audit_mod, "load_strategy_registry", mock_load_registry)
    
    # Run once without any mock evidence files
    audit_mod.audit_phase6()
    
    json_path = tmp_path / "runtime/strategy_validation/phase6_eligibility_report.json"
    with open(json_path) as f:
        report = json.load(f)
        
    rep_map = {r["strategy_id"]: r for r in report}
    
    # SIMPLE_ORB should fail due to missing evidence
    assert rep_map["SIMPLE_ORB"]["phase6_eligible"] is False
    assert rep_map["SIMPLE_ORB"]["phase6_status"] == "PHASE6_BLOCKED_PHASE_EVIDENCE_MISSING"
    assert rep_map["SIMPLE_ORB"]["phase_1_passed"] is False
    assert "PHASE_EVIDENCE_MISSING" in rep_map["SIMPLE_ORB"]["blockers"]
    
    # HTF_OPENING_DRIVE_CONT is quarantined
    assert rep_map["HTF_OPENING_DRIVE_CONT"]["phase6_eligible"] is False
    assert rep_map["HTF_OPENING_DRIVE_CONT"]["phase6_status"] == "PHASE6_BLOCKED_QUARANTINED"
    assert "STRATEGY_QUARANTINED" in rep_map["HTF_OPENING_DRIVE_CONT"]["blockers"]
    
    # MEAN_REVERSION_EXTENSION is a generator
    assert rep_map["MEAN_REVERSION_EXTENSION"]["phase6_eligible"] is False
    assert rep_map["MEAN_REVERSION_EXTENSION"]["phase6_status"] == "PHASE6_BLOCKED_CANDIDATE_GENERATOR_NOT_REPLAY_CERTIFIED"
    
    # Now create mock evidence files for SIMPLE_ORB
    orb_dir = tmp_path / "runtime/strategy_validation/SIMPLE_ORB"
    orb_dir.mkdir(parents=True, exist_ok=True)
    (orb_dir / "phase_1_report.json").touch()
    (orb_dir / "phase_2_report.json").touch()
    (orb_dir / "phase_3_report.json").touch()
    (orb_dir / "phase_3_5_report.json").touch()
    (orb_dir / "phase_4_report.json").touch()
    (orb_dir / "phase_5_wfa_report.json").touch()
    
    # Run again with evidence
    audit_mod.audit_phase6()
    
    with open(json_path) as f:
        report = json.load(f)
        
    rep_map = {r["strategy_id"]: r for r in report}
    
    assert rep_map["SIMPLE_ORB"]["phase6_eligible"] is True
    assert rep_map["SIMPLE_ORB"]["phase6_status"] == "PHASE_6_SCAFFOLD_READY"
    assert rep_map["SIMPLE_ORB"]["phase_1_passed"] is True
    assert rep_map["SIMPLE_ORB"]["phase6_passed"] is False
    assert "PHASE_EVIDENCE_MISSING" not in rep_map["SIMPLE_ORB"]["blockers"]
    
    # Finally, add shadow evidence
    (orb_dir / "live_shadow_report.json").touch()
    
    audit_mod.audit_phase6()
    
    with open(json_path) as f:
        report = json.load(f)
        
    rep_map = {r["strategy_id"]: r for r in report}
    assert rep_map["SIMPLE_ORB"]["phase6_passed"] is True
    assert rep_map["SIMPLE_ORB"]["phase_evidence_sources"]["phase_6_shadow"] is not None

