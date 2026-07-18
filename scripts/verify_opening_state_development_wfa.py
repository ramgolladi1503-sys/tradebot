import sys
import json
from pathlib import Path

def load_json(path):
    with open(path, "r") as f:
        return json.load(f)

def save_json(path: Path, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def main():
    try:
        metrics = load_json("docs/agent_reviews/opening_state_momentum/development_wfa_metrics.json")
        controls = load_json("docs/agent_reviews/opening_state_momentum/development_wfa_negative_controls.json")
        temporal = load_json("docs/agent_reviews/opening_state_momentum/development_wfa_temporal_stability.json")
        
        # Determine classification
        # We use 5 bps as primary
        primary = metrics["OVERALL"]["ALL"]["5bps"]
        
        total_outcomes = primary["trade_count"]
        mean = primary["mean_return"]
        median = primary["median_return"]
        pf = primary["profit_factor"]
        
        if isinstance(pf, dict):
            pf = -1.0 # Failed pf
            
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
              inv_diff > 0 and 
              p_val <= 0.10):
            classification = "DEVELOPMENT_EDGE_CANDIDATE"
            
        out_dir = Path("docs/agent_reviews/opening_state_momentum")
        save_json(out_dir / "development_wfa_verification.json", {"classification": classification})
        
        print(f"CLASSIFICATION: {classification}")
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}")
        out_dir = Path("docs/agent_reviews/opening_state_momentum")
        save_json(out_dir / "development_wfa_verification.json", {"classification": "WFA_EVIDENCE_WITH_GAPS", "error": str(e)})
        print("CLASSIFICATION: WFA_EVIDENCE_WITH_GAPS")
        sys.exit(1)

if __name__ == "__main__":
    main()
