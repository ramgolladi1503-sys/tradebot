import sys
import json
import os
from pathlib import Path

def discover_evidence():
    out_dir = Path("runtime/strategy_validation/SIMPLE_ORB")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    search_dirs = [
        "runtime/strategy_validation/",
        "reports/",
        "data/live_drift/",
        "configs/"
    ]
    
    phases = ["phase_1", "phase_2", "phase_3", "phase_3_5", "phase_4", "phase_5_wfa"]
    
    found_evidence = {p: None for p in phases}
    
    for d in search_dirs:
        p = Path(d)
        if not p.exists():
            continue
            
        for root, dirs, files in os.walk(p):
            for file in files:
                if not file.endswith(".json"):
                    continue
                if file.endswith("_report.json") or file.endswith("_inventory.json"):
                    continue
                    
                full_path = Path(root) / file
                lower_path = str(full_path).lower()
                
                try:
                    with open(full_path, "r") as f:
                        data = json.load(f)
                except Exception:
                    continue
                
                if not isinstance(data, dict):
                    continue
                
                # Detect strategy ID
                strat_id = data.get("strategy_id", None)
                if strat_id and strat_id != "SIMPLE_ORB":
                    continue # Explicitly another strategy
                    
                if strat_id != "SIMPLE_ORB" and "simple_orb" not in lower_path:
                    continue # Not clearly SIMPLE_ORB
                    
                # Detect phase
                phase_detected = None
                if data.get("phase") in phases:
                    phase_detected = data["phase"]
                elif data.get("phase_detected") in phases:
                    phase_detected = data["phase_detected"]
                else:
                    for ph in phases:
                        if ph in lower_path:
                            phase_detected = ph
                            break
                            
                if not phase_detected:
                    continue
                
                # Check pass verdict
                passed = False
                verdict = None
                if "passed" in data and bool(data["passed"]):
                    passed = True
                    verdict = "PASSED"
                elif "phase_passed" in data and bool(data["phase_passed"]):
                    passed = True
                    verdict = "PASSED"
                elif "status" in data and str(data["status"]).upper() == "PASSED":
                    passed = True
                    verdict = "PASSED"
                elif "verdict" in data and str(data["verdict"]).upper() == "PASSED":
                    passed = True
                    verdict = "PASSED"
                    
                if not passed:
                    continue
                    
                # Valid evidence found
                if found_evidence[phase_detected] is None:
                    found_evidence[phase_detected] = {
                        "path": str(full_path),
                        "exists": True,
                        "size": full_path.stat().st_size,
                        "mtime": full_path.stat().st_mtime,
                        "matched_terms": [phase_detected, "SIMPLE_ORB"],
                        "parsed_json": True,
                        "strategy_id_detected": "SIMPLE_ORB",
                        "phase_detected": phase_detected,
                        "verdict_detected": verdict,
                        "safe_to_use_as_phase_evidence": True,
                        "reasons": []
                    }

    missing_phases = [p for p in phases if found_evidence[p] is None]
    usable_count = len(phases) - len(missing_phases)
    all_present = len(missing_phases) == 0
    
    if all_present:
        classification = "SIMPLE_ORB_PHASE_EVIDENCE_COMPLETE"
    elif usable_count > 0:
        classification = "SIMPLE_ORB_PHASE_EVIDENCE_FOUND_PARTIAL"
    else:
        classification = "SIMPLE_ORB_PHASE_EVIDENCE_MISSING"
        
    inventory = {
        "strategy_id": "SIMPLE_ORB",
        "discovery_classification": classification,
        "phase_evidence": found_evidence,
        "missing_phases": missing_phases,
        "usable_phase_count": usable_count,
        "all_phase_1_to_5_evidence_present": all_present,
        "normalization_allowed": all_present,
        "paper_live_allowed": False,
        "live_allowed": False,
        "broker_order_allowed": False,
        "execution_allowed": False
    }
    
    with open(out_dir / "simple_orb_phase_evidence_inventory.json", "w") as f:
        json.dump(inventory, f, indent=2)
        
    md = [
        "# SIMPLE_ORB Phase Evidence Inventory\n",
        f"- Classification: {classification}",
        f"- Usable phases: {usable_count}/6",
        f"- Missing phases: {missing_phases}\n"
    ]
    for ph in phases:
        md.append(f"## {ph}")
        ev = found_evidence[ph]
        if ev:
            md.append(f"- Path: {ev['path']}")
            md.append(f"- Verdict: {ev['verdict_detected']}")
        else:
            md.append("- missing")
            
    with open(out_dir / "simple_orb_phase_evidence_inventory.md", "w") as f:
        f.write("\n".join(md) + "\n")
        
    # Normalization
    if all_present:
        for ph in phases:
            ev = found_evidence[ph]
            norm = {
              "strategy_id": "SIMPLE_ORB",
              "phase": ph,
              "passed": True,
              "verdict": "PASSED",
              "source_evidence_path": ev["path"],
              "source_evidence_mtime": ev["mtime"],
              "source_evidence_size": ev["size"],
              "normalization_type": "MIRROR_OF_EXISTING_EVIDENCE",
              "paper_live_allowed": False,
              "live_allowed": False,
              "broker_order_allowed": False,
              "execution_allowed": False
            }
            with open(out_dir / f"{ph}_report.json", "w") as f:
                json.dump(norm, f, indent=2)

if __name__ == "__main__":
    discover_evidence()
