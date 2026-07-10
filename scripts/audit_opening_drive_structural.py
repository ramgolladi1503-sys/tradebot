import json
import sys
from pathlib import Path

import argparse

def run_audit(strat_id="OPENING_DRIVE", is_smoke_test=False):
    ledger_path = Path(f"runtime/strategy_validation/{strat_id}/phase_4_candidates.jsonl")
    out_path = Path(f"runtime/strategy_validation/{strat_id}/phase_4_opening_drive_structural_audit.json")
    
    if not ledger_path.exists():
        with open(out_path, "w") as f:
            json.dump({"classification": "STRUCTURAL_AUDIT_FAILED", "blockers": ["MISSING_CANDIDATES_FILE"]}, f)
        return False
        
    blockers = set()
    rows = 0
    
    with open(ledger_path, "r") as f:
        for line in f:
            if not line.strip(): continue
            cand = json.loads(line)
            rows += 1
            
            base_reqs = ["signal_time", "symbol", "setup_type", "reject_reason", "opening_drive_window_minutes", "open_move_points", "vwap_distance", "signal_close"]
            for req in base_reqs:
                if req not in cand:
                    blockers.add(f"MISSING_BASE_FIELD_{req.upper()}")
            
            rr = cand.get("reject_reason")
            
            if rr in ["SELECTED", "NEXT_OPEN_COST_HURDLE_FAILED", "NEXT_OPEN_GAP_INVALID"]:
                exec_reqs = ["entry_open", "stop_loss", "target", "planned_target_distance", "proxy_option_expected_move", "cost_hurdle_margin"]
                for req in exec_reqs:
                    if req not in cand:
                        blockers.add(f"MISSING_EXEC_FIELD_{req.upper()}")

    if rows == 0:
        blockers.add("OPENING_DRIVE_EMPTY_LEDGER_PASSED")
        
    has_selected = False
    has_buy_call = False
    has_buy_put = False
    
    with open(ledger_path, "r") as f:
        for line in f:
            if not line.strip(): continue
            cand = json.loads(line)
            if cand.get("reject_reason") == "SELECTED":
                has_selected = True
            
            # Record direction diversity from all candidates (or specifically from selected ones if preferred. The user said: "Before the grid, prove this: candidate_reject_reason_distribution... BUY_CALL_count, BUY_PUT_count" and "Add OPENING_DRIVE_DIRECTION_DIVERSITY_NOT_PROVEN blocker if all trades are one direction". I'll check all candidates for direction diversity.
            if cand.get("setup_type") == "BUY_CALL": has_buy_call = True
            if cand.get("setup_type") == "BUY_PUT": has_buy_put = True
                
    if not has_selected:
        blockers.add("OPENING_DRIVE_SELECTED_PATH_NOT_PROVEN")
        
    if not (has_buy_call and has_buy_put):
        if is_smoke_test:
            print("WARNING: OPENING_DRIVE_DIRECTION_DIVERSITY_NOT_PROVEN (suppressed due to smoke test)")
        else:
            blockers.add("OPENING_DRIVE_DIRECTION_DIVERSITY_NOT_PROVEN")
        
    res = {
        "classification": "OPENING_DRIVE_STRUCTURAL_AUDIT_PASSED" if not blockers else "OPENING_DRIVE_STRUCTURAL_AUDIT_FAILED",
        "blockers": list(blockers)
    }
    with open(out_path, "w") as f:
        json.dump(res, f, indent=2)
        
    return not blockers

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, default="OPENING_DRIVE")
    parser.add_argument("--is-smoke-test", action="store_true")
    args = parser.parse_args()
    run_audit(strat_id=args.strategy, is_smoke_test=args.is_smoke_test)
