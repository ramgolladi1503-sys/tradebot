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
    
    audit_mod.audit_phase6()
    
    json_path = tmp_path / "runtime/strategy_validation/phase6_eligibility_report.json"
    assert json_path.exists()
    
    with open(json_path) as f:
        report = json.load(f)
        
    rep_map = {r["strategy_id"]: r for r in report}
    
    # SIMPLE_ORB
    assert rep_map["SIMPLE_ORB"]["phase6_eligible"] is True
    assert rep_map["SIMPLE_ORB"]["phase6_status"] == "PHASE_6_SCAFFOLD_READY"
    assert rep_map["SIMPLE_ORB"]["phase6_passed"] is False
    assert len(rep_map["SIMPLE_ORB"]["blockers"]) == 0
    assert rep_map["SIMPLE_ORB"]["execution_allowed"] is False
    
    # HTF_OPENING_DRIVE_CONT
    assert rep_map["HTF_OPENING_DRIVE_CONT"]["phase6_eligible"] is False
    assert rep_map["HTF_OPENING_DRIVE_CONT"]["phase6_status"] == "PHASE6_BLOCKED_QUARANTINED"
    assert "STRATEGY_QUARANTINED" in rep_map["HTF_OPENING_DRIVE_CONT"]["blockers"]
    
    # MEAN_REVERSION_EXTENSION (candidate generator)
    assert rep_map["MEAN_REVERSION_EXTENSION"]["phase6_eligible"] is False
    assert rep_map["MEAN_REVERSION_EXTENSION"]["phase6_status"] == "PHASE6_BLOCKED_CANDIDATE_GENERATOR_NOT_REPLAY_CERTIFIED"
    assert "CANDIDATE_GENERATOR_REQUIRES_REPLAY_CERTIFICATION_FIRST" in rep_map["MEAN_REVERSION_EXTENSION"]["blockers"]
    
    # PRO_STRATEGY_ENGINE (aggregate engine)
    assert rep_map["PRO_STRATEGY_ENGINE"]["phase6_eligible"] is False
    assert rep_map["PRO_STRATEGY_ENGINE"]["phase6_status"] == "PHASE6_BLOCKED_AGGREGATE_ENGINE_PENDING"
    assert "CHILD_CERTIFICATION_PENDING" in rep_map["PRO_STRATEGY_ENGINE"]["blockers"]
    
    # Check safety flags for all
    for r in report:
        assert r["paper_live_allowed"] is False
        assert r["live_allowed"] is False
        assert r["broker_order_allowed"] is False
        assert r["execution_allowed"] is False
        assert r["phase6_passed"] is False
        assert "5 clean live shadow sessions" in r["phase6_required_evidence"]
