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
    
    # 1. Empty phase report does not pass
    orb_dir = tmp_path / "runtime/strategy_validation/SIMPLE_ORB"
    orb_dir.mkdir(parents=True, exist_ok=True)
    (orb_dir / "phase_1_report.json").write_text("")
    
    audit_mod.audit_phase6()
    json_path = tmp_path / "runtime/strategy_validation/phase6_eligibility_report.json"
    with open(json_path) as f:
        report = json.load(f)
    rep_map = {r["strategy_id"]: r for r in report}
    
    assert rep_map["SIMPLE_ORB"]["phase6_eligible"] is False
    assert "PHASE_EVIDENCE_MALFORMED" in rep_map["SIMPLE_ORB"]["blockers"]
    
    # 2. Malformed phase report
    (orb_dir / "phase_1_report.json").write_text("{badjson}")
    audit_mod.audit_phase6()
    with open(json_path) as f:
        report = json.load(f)
    rep_map = {r["strategy_id"]: r for r in report}
    assert "PHASE_EVIDENCE_MALFORMED" in rep_map["SIMPLE_ORB"]["blockers"]
    
    # 3. No verdict
    (orb_dir / "phase_1_report.json").write_text('{"foo": "bar"}')
    audit_mod.audit_phase6()
    with open(json_path) as f:
        report = json.load(f)
    rep_map = {r["strategy_id"]: r for r in report}
    assert "PHASE_EVIDENCE_VERDICT_MISSING" in rep_map["SIMPLE_ORB"]["blockers"]
    
    # 4. passed=false
    (orb_dir / "phase_1_report.json").write_text('{"passed": false}')
    audit_mod.audit_phase6()
    with open(json_path) as f:
        report = json.load(f)
    rep_map = {r["strategy_id"]: r for r in report}
    assert "PHASE_EVIDENCE_NOT_PASSED" in rep_map["SIMPLE_ORB"]["blockers"]
    
    # 5. passed=true
    (orb_dir / "phase_1_report.json").write_text('{"passed": true}')
    (orb_dir / "phase_2_report.json").write_text('{"status": "PASSED"}')
    (orb_dir / "phase_3_report.json").write_text('{"verdict": "PASSED"}')
    (orb_dir / "phase_3_5_report.json").write_text('{"phase_passed": true}')
    (orb_dir / "phase_4_report.json").write_text('{"passed": true}')
    (orb_dir / "phase_5_wfa_report.json").write_text('{"passed": true}')
    
    audit_mod.audit_phase6()
    with open(json_path) as f:
        report = json.load(f)
    rep_map = {r["strategy_id"]: r for r in report}
    
    assert rep_map["SIMPLE_ORB"]["phase6_eligible"] is True
    assert rep_map["SIMPLE_ORB"]["phase6_status"] == "PHASE_6_SCAFFOLD_READY"
    assert rep_map["SIMPLE_ORB"]["phase_1_passed"] is True
    assert rep_map["SIMPLE_ORB"]["phase_evidence_sources"]["phase_2"]["verdict"] == "PASSED"
    
    # 8. Empty shadow report does not pass
    (orb_dir / "live_shadow_report.json").write_text("")
    audit_mod.audit_phase6()
    with open(json_path) as f:
        report = json.load(f)
    rep_map = {r["strategy_id"]: r for r in report}
    assert rep_map["SIMPLE_ORB"]["phase6_passed"] is False
    assert "PHASE6_SHADOW_EVIDENCE_MALFORMED" in rep_map["SIMPLE_ORB"]["phase6_shadow_evidence"]["blockers"]
    
    # 10. Shadow report fewer than 5 sessions
    (orb_dir / "live_shadow_report.json").write_text('{"clean_shadow_sessions": 3}')
    audit_mod.audit_phase6()
    with open(json_path) as f:
        report = json.load(f)
    rep_map = {r["strategy_id"]: r for r in report}
    assert rep_map["SIMPLE_ORB"]["phase6_passed"] is False
    assert "PHASE6_SHADOW_SESSION_COUNT_INSUFFICIENT" in rep_map["SIMPLE_ORB"]["phase6_shadow_evidence"]["blockers"]
    
    # 11. real_order_sent=true
    (orb_dir / "live_shadow_report.json").write_text('{"clean_shadow_sessions": 5, "real_order_sent": true}')
    audit_mod.audit_phase6()
    with open(json_path) as f:
        report = json.load(f)
    rep_map = {r["strategy_id"]: r for r in report}
    assert "PHASE6_SHADOW_REAL_ORDER_SENT" in rep_map["SIMPLE_ORB"]["phase6_shadow_evidence"]["blockers"]
    
    # 12. missing real data fields
    (orb_dir / "live_shadow_report.json").write_text('{"clean_shadow_sessions": 5, "real_order_sent": false, "real_candles_used": true}')
    audit_mod.audit_phase6()
    with open(json_path) as f:
        report = json.load(f)
    rep_map = {r["strategy_id"]: r for r in report}
    assert "PHASE6_SHADOW_REAL_DATA_MISSING" in rep_map["SIMPLE_ORB"]["phase6_shadow_evidence"]["blockers"]
    
    # 13. All required fields
    (orb_dir / "live_shadow_report.json").write_text('{"clean_shadow_sessions": 5, "real_order_sent": false, "real_candles_used": true, "real_option_chain_snapshots_used": true, "real_option_quotes_used": true}')
    audit_mod.audit_phase6()
    with open(json_path) as f:
        report = json.load(f)
    rep_map = {r["strategy_id"]: r for r in report}
    assert rep_map["SIMPLE_ORB"]["phase6_passed"] is True
    assert rep_map["SIMPLE_ORB"]["phase6_shadow_evidence"]["valid"] is True
    
    # 14. candidate generators remain blocked
    assert rep_map["MEAN_REVERSION_EXTENSION"]["phase6_eligible"] is False
    assert rep_map["MEAN_REVERSION_EXTENSION"]["phase6_status"] == "PHASE6_BLOCKED_CANDIDATE_GENERATOR_NOT_REPLAY_CERTIFIED"
    
    # 15. HTF remains quarantined
    assert rep_map["HTF_OPENING_DRIVE_CONT"]["phase6_eligible"] is False
    assert rep_map["HTF_OPENING_DRIVE_CONT"]["phase6_status"] == "PHASE6_BLOCKED_QUARANTINED"
    
    # 16. Paper/live flags remain false
    for r in report:
        assert r["paper_live_allowed"] is False
        assert r["live_allowed"] is False
        assert r["broker_order_allowed"] is False
        assert r["execution_allowed"] is False

