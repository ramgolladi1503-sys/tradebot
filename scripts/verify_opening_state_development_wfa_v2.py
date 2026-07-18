import sys
import json
import subprocess
from pathlib import Path

def load_json(path):
    with open(path, "r") as f:
        return json.load(f)

def run_cmd(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).returncode

def main():
    try:
        # Causal and outcome verifier
        if run_cmd(["python", "scripts/verify_opening_state_causal_pass.py"]) != 0:
            raise ValueError("Causal verifier failed")
        if run_cmd(["python", "scripts/verify_opening_state_outcome_labels.py"]) != 0:
            raise ValueError("Outcome verifier failed")
            
        metrics = load_json("docs/agent_reviews/opening_state_momentum/development_wfa_metrics.json")
        controls = load_json("docs/agent_reviews/opening_state_momentum/development_wfa_negative_controls.json")
        temporal = load_json("docs/agent_reviews/opening_state_momentum/development_wfa_temporal_stability.json")
        audit = load_json("docs/agent_reviews/opening_state_momentum/development_wfa_holdout_access_audit.json")
        determinism = load_json("docs/agent_reviews/opening_state_momentum/development_wfa_determinism.json")
        oracle = load_json("docs/agent_reviews/opening_state_momentum/development_wfa_oracle_comparison.json")
        decisions = load_json("docs/agent_reviews/opening_state_momentum/candidate_decisions.json")
        outcomes = load_json("docs/agent_reviews/opening_state_momentum/development_outcome_labels.json")
        
        # Validation rules
        if len(decisions) != 398:
            raise ValueError("Session count != 398")
        if len(outcomes) != 32:
            raise ValueError("Outcome count != 32")
        
        long_count = sum(1 for o in outcomes if o["direction"] == "LONG")
        short_count = sum(1 for o in outcomes if o["direction"] == "SHORT")
        if long_count != 13 or short_count != 19:
            raise ValueError("LONG/SHORT counts != 13/19")
            
        if audit["holdout_dates_loaded"] > 0 or audit["holdout_outcomes_loaded"] > 0:
            raise ValueError("Holdout dates accessed")
            
        if not determinism["determinism_verified"]:
            raise ValueError("Determinism check failed")
            
        if oracle["mismatches"] > 0:
            raise ValueError(f"Oracle mismatches: {oracle['mismatches']}")
            
        # Determine classification on 5-bps
        primary = metrics["OVERALL"]["ALL"]["5bps"]
        
        total_outcomes = primary["trade_count"]
        mean = primary["mean_return"]
        median = primary["median_return"]
        pf = primary["profit_factor"]
        
        if isinstance(pf, dict):
            pf = -1.0
            
        pos_folds = sum(1 for i in range(5) if metrics[f"FOLD_{i}"]["ALL"]["5bps"]["mean_return"] is not None and metrics[f"FOLD_{i}"]["ALL"]["5bps"]["mean_return"] > 0)
        sufficient_folds = sum(1 for i in range(5) if metrics[f"FOLD_{i}"]["ALL"]["5bps"]["trade_count"] >= 4)
        
        top_1 = temporal.get("top_one_trade_contribution", 1.0) or 1.0
        top_3 = temporal.get("top_three_trade_contribution", 1.0) or 1.0
        
        inv_diff = controls["A_direction_inversion"]["5bps"]["mean_return_difference"]
        p_val = controls["B_direction_randomization"]["empirical_p_value"]
        
        classification = "DEVELOPMENT_EDGE_NOT_SUPPORTED"
        
        if total_outcomes < 30 or sufficient_folds < 4:
            classification = "DEVELOPMENT_SAMPLE_TOO_SPARSE"
        elif (total_outcomes == 32 and
              mean > 0 and 
              median > 0 and 
              pf > 1 and 
              pos_folds >= 3 and 
              sufficient_folds >= 4 and 
              top_1 < 0.40 and 
              top_3 < 0.70 and 
              inv_diff is not None and inv_diff > 0 and 
              p_val <= 0.10):
            classification = "DEVELOPMENT_EDGE_CANDIDATE"
            
        # Print outputs
        fold_sizes = [metrics[f"FOLD_{i}"]["ALL"]["5bps"]["trade_count"] for i in range(5)]
        print(f"FOLD SIZES: {fold_sizes}")
        print(f"FOLD TRADE COUNTS: {fold_sizes}")
        print(f"OVERALL MEAN: {mean}")
        print(f"MEDIAN: {median}")
        print(f"PROFIT FACTOR: {pf}")
        print(f"POSITIVE FOLD COUNT: {pos_folds}")
        print(f"FOLDS WITH AT LEAST FOUR TRADES: {sufficient_folds}")
        print(f"TOP ONE CONTRIBUTION: {top_1}")
        print(f"TOP THREE CONTRIBUTION: {top_3}")
        print(f"INVERTED MEAN DIFF: {inv_diff}")
        print(f"RANDOMIZATION P-VALUE: {p_val}")
        
        print(f"CLASSIFICATION: {classification}")
        
        if "--write-artifact" in sys.argv:
            out_dir = Path("docs/agent_reviews/opening_state_momentum")
            with open(out_dir / "development_wfa_verification.json", "w") as f:
                json.dump({"classification": classification}, f, indent=2)
                
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}")
        print("CLASSIFICATION: WFA_EVIDENCE_WITH_GAPS")
        sys.exit(1)

if __name__ == "__main__":
    main()
