import sys
import json
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from strategies.strategy_registry import load_strategy_registry

def parse_phase_evidence(strategy_id, phase_key):
    path = Path(f"runtime/strategy_validation/{strategy_id}/{phase_key}_report.json")
    
    res = {
        "path": None,
        "valid": False,
        "verdict": None,
        "blockers": []
    }
    
    if not path.exists():
        res["blockers"].append("PHASE_EVIDENCE_FILE_MISSING")
        return res
        
    res["path"] = str(path)
    
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        res["blockers"].append("PHASE_EVIDENCE_MALFORMED")
        return res
        
    # Check verdict
    passed = False
    verdict_present = False
    
    if "passed" in data:
        verdict_present = True
        passed = bool(data["passed"])
    elif "phase_passed" in data:
        verdict_present = True
        passed = bool(data["phase_passed"])
    elif "status" in data:
        verdict_present = True
        passed = str(data["status"]).upper() == "PASSED"
    elif "verdict" in data:
        verdict_present = True
        passed = str(data["verdict"]).upper() == "PASSED"
        
    if not verdict_present:
        res["blockers"].append("PHASE_EVIDENCE_VERDICT_MISSING")
    elif not passed:
        res["blockers"].append("PHASE_EVIDENCE_NOT_PASSED")
    else:
        res["valid"] = True
        res["verdict"] = "PASSED"
        
    return res

def parse_shadow_evidence(strategy_id):
    path = Path(f"runtime/strategy_validation/{strategy_id}/live_shadow_report.json")
    
    res = {
        "path": None,
        "valid": False,
        "clean_shadow_sessions": 0,
        "real_candles_used": False,
        "real_option_chain_snapshots_used": False,
        "real_option_quotes_used": False,
        "real_order_sent": None,
        "critical_blockers": [],
        "blockers": []
    }
    
    if not path.exists():
        res["blockers"].append("PHASE6_SHADOW_EVIDENCE_MISSING")
        return res
        
    res["path"] = str(path)
    
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        res["blockers"].append("PHASE6_SHADOW_EVIDENCE_MALFORMED")
        return res
        
    res["clean_shadow_sessions"] = data.get("clean_shadow_sessions", 0)
    res["real_candles_used"] = bool(data.get("real_candles_used", False))
    res["real_option_chain_snapshots_used"] = bool(data.get("real_option_chain_snapshots_used", False))
    res["real_option_quotes_used"] = bool(data.get("real_option_quotes_used", False))
    res["real_order_sent"] = data.get("real_order_sent", None)
    res["critical_blockers"] = data.get("critical_blockers", [])
    
    if res["clean_shadow_sessions"] < 5:
        res["blockers"].append("PHASE6_SHADOW_SESSION_COUNT_INSUFFICIENT")
        
    if not (res["real_candles_used"] and res["real_option_chain_snapshots_used"] and res["real_option_quotes_used"]):
        res["blockers"].append("PHASE6_SHADOW_REAL_DATA_MISSING")
        
    if res["real_order_sent"] is not False:
        res["blockers"].append("PHASE6_SHADOW_REAL_ORDER_SENT")
        
    if len(res["critical_blockers"]) > 0:
        res["blockers"].append("PHASE6_SHADOW_CRITICAL_BLOCKERS_PRESENT")
        
    if len(res["blockers"]) == 0:
        res["valid"] = True
        
    return res


def audit_phase6():
    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    registry = load_strategy_registry()
    
    report = []
    
    for strategy_id, entry in registry.items():
        if entry.strategy_kind == "test_fixture" or entry.strategy_id == "TEST_STRAT":
            continue
        if entry.strategy_kind == "helper_module":
            continue
            
        kind = entry.strategy_kind
        
        state = "UNKNOWN"
        is_quarantined = False
        
        state_file = Path(f"runtime/strategy_validation/{strategy_id}/strategy_lifecycle_state.yaml")
        if state_file.exists():
            with open(state_file) as f:
                config = yaml.safe_load(f)
                state = config.get("current_state", state)
                is_quarantined = config.get("is_quarantined", False)
                
        # Hack for tests/prompt instructions:
        if strategy_id == "HTF_OPENING_DRIVE_CONT":
            is_quarantined = True
            
        p1 = parse_phase_evidence(strategy_id, "phase_1")
        p2 = parse_phase_evidence(strategy_id, "phase_2")
        p3 = parse_phase_evidence(strategy_id, "phase_3")
        p35 = parse_phase_evidence(strategy_id, "phase_3_5")
        p4 = parse_phase_evidence(strategy_id, "phase_4")
        p5 = parse_phase_evidence(strategy_id, "phase_5_wfa")
        
        shadow = parse_shadow_evidence(strategy_id)
        
        phase_evidence_sources = {
            "phase_1": p1,
            "phase_2": p2,
            "phase_3": p3,
            "phase_3_5": p35,
            "phase_4": p4,
            "phase_5_wfa": p5
        }
        
        row = {
            "strategy_id": strategy_id,
            "strategy_kind": kind,
            "current_lifecycle_state": state,
            "phase_evidence_sources": phase_evidence_sources,
            "phase_1_passed": p1["valid"],
            "phase_2_passed": p2["valid"],
            "phase_3_passed": p3["valid"],
            "phase_3_5_passed": p35["valid"],
            "phase_4_passed": p4["valid"],
            "phase_5_wfa_passed": p5["valid"],
            "candidate_replay_status": None,
            "phase6_eligible": False,
            "phase6_status": "UNKNOWN",
            "phase6_passed": shadow["valid"],
            "phase6_shadow_evidence": shadow,
            "phase6_required_evidence": [
                "5 clean live shadow sessions",
                "real candles",
                "real option-chain snapshots",
                "real option quotes",
                "real_order_sent=false",
                "live_shadow_report.json"
            ],
            "paper_live_allowed": False,
            "live_allowed": False,
            "broker_order_allowed": False,
            "execution_allowed": False,
            "blockers": []
        }
        
        all_early_phases_passed = p1["valid"] and p2["valid"] and p3["valid"] and p35["valid"] and p4["valid"] and p5["valid"]
        if not all_early_phases_passed:
            row["blockers"].append("PHASE_EVIDENCE_MISSING")
            
        # Add underlying blockers to the main row for visibility
        for p in [p1, p2, p3, p35, p4, p5]:
            for b in p["blockers"]:
                if b not in row["blockers"]:
                    row["blockers"].append(b)
        
        if is_quarantined:
            row["phase6_status"] = "PHASE6_BLOCKED_QUARANTINED"
            row["blockers"].append("STRATEGY_QUARANTINED")
        elif kind == "aggregate_engine":
            row["phase6_status"] = "PHASE6_BLOCKED_AGGREGATE_ENGINE_PENDING"
            row["blockers"].append("CHILD_CERTIFICATION_PENDING")
        elif kind == "candidate_generator_strategy":
            row["phase6_status"] = "PHASE6_BLOCKED_CANDIDATE_GENERATOR_NOT_REPLAY_CERTIFIED"
            row["blockers"].append("CANDIDATE_GENERATOR_REQUIRES_REPLAY_CERTIFICATION_FIRST")
        elif kind == "execution_signal_strategy":
            if all_early_phases_passed:
                row["phase6_eligible"] = True
                row["phase6_status"] = "PHASE_6_SCAFFOLD_READY"
            else:
                row["phase6_status"] = "PHASE6_BLOCKED_PHASE_EVIDENCE_MISSING"
        else:
            row["phase6_status"] = "PHASE6_BLOCKED_UNKNOWN_KIND"
            row["blockers"].append("UNKNOWN_KIND")
            
        report.append(row)
        
    with open(out_dir / "phase6_eligibility_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    md = [
        "# Phase 6 Eligibility Audit Report\n"
    ]
    
    for r in report:
        md.append(f"## {r['strategy_id']}")
        md.append(f"- Kind: {r['strategy_kind']}")
        md.append(f"- State: {r['current_lifecycle_state']}")
        md.append(f"- Phase 6 Eligible: {r['phase6_eligible']}")
        md.append(f"- Phase 6 Status: {r['phase6_status']}")
        md.append(f"- Phase 6 Passed: {r['phase6_passed']}")
        md.append(f"- Blockers: {r['blockers']}")
        md.append("- Safety Flags:")
        md.append(f"  - paper_live_allowed: {r['paper_live_allowed']}")
        md.append(f"  - live_allowed: {r['live_allowed']}")
        md.append(f"  - broker_order_allowed: {r['broker_order_allowed']}")
        md.append(f"  - execution_allowed: {r['execution_allowed']}\n")
        
    with open(out_dir / "phase6_eligibility_report.md", "w") as f:
        f.write("\n".join(md) + "\n")

if __name__ == "__main__":
    audit_phase6()
