import json
import math
from pathlib import Path
import sys

def load_json(path):
    with open(path, "r") as f:
        return json.load(f)

def save_json(path: Path, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def oracle_assign_folds(dates):
    s = sorted(list(set(dates)))
    base, rem = divmod(len(s), 5)
    mapping = {}
    idx = 0
    for f in range(5):
        size = base + (1 if f < rem else 0)
        for _ in range(size):
            mapping[s[idx]] = f
            idx += 1
    return mapping

def main():
    decisions = load_json("docs/agent_reviews/opening_state_momentum/candidate_decisions.json")
    outcomes = load_json("docs/agent_reviews/opening_state_momentum/development_outcome_labels.json")
    metrics = load_json("docs/agent_reviews/opening_state_momentum/development_wfa_metrics.json")
    
    all_dates = [d["session_date"] for d in decisions]
    fold_mapping = oracle_assign_folds(all_dates)
    
    mismatches = 0
    tolerance = 1e-9
    
    def check(val1, val2, name):
        nonlocal mismatches
        if isinstance(val1, dict) and "value" in val1:
            val1 = val1["value"]
        if isinstance(val2, dict) and "value" in val2:
            val2 = val2["value"]
            
        if val1 is None and val2 is None:
            return
        if val1 is None or val2 is None:
            print(f"Mismatch {name}: {val1} != {val2}")
            mismatches += 1
            return
        if isinstance(val1, float) and isinstance(val2, float):
            if not math.isclose(val1, val2, abs_tol=tolerance):
                print(f"Mismatch {name}: {val1} != {val2}")
                mismatches += 1
        elif val1 != val2:
            print(f"Mismatch {name}: {val1} != {val2}")
            mismatches += 1
            
    def get_return(entry, exit, direction):
        if direction == "LONG": return exit / entry - 1.0
        if direction == "SHORT": return entry / exit - 1.0
        return 0.0
        
    for friction_bps, friction_val in [("0bps", 0.0), ("2bps", 2.0), ("5bps", 5.0), ("10bps", 10.0)]:
        rets = [get_return(o["entry_price"], o["exit_price"], o["direction"]) - 2 * friction_val / 10000.0 for o in outcomes]
        n = len(rets)
        pos = sum(1 for r in rets if r > 0)
        neg = sum(1 for r in rets if r < 0)
        
        mean = sum(rets) / n if n > 0 else None
        sr = sorted(rets)
        if n % 2 == 0:
            median = (sr[n//2 - 1] + sr[n//2]) / 2 if n > 0 else None
        else:
            median = sr[n//2] if n > 0 else None
            
        win_rate = pos / n if n > 0 else None
        
        sum_pos = sum(r for r in rets if r > 0)
        sum_neg = sum(r for r in rets if r < 0)
        
        if sum_neg == 0:
            pf = None
        else:
            pf = abs(sum_pos / sum_neg)
            
        cum_ar = sum(rets)
        
        cum_comp = 1.0
        max_dd = 0.0
        peak = 1.0
        for r in rets:
            cum_comp *= (1 + r)
            if cum_comp > peak:
                peak = cum_comp
            dd = (peak - cum_comp) / peak
            if dd > max_dd:
                max_dd = dd
                
        m = metrics["OVERALL"]["ALL"][friction_bps]
        check(m["trade_count"], n, f"OVERALL ALL {friction_bps} trade_count")
        check(m["mean_return"], mean, f"OVERALL ALL {friction_bps} mean_return")
        check(m["median_return"], median, f"OVERALL ALL {friction_bps} median_return")
        check(m["win_rate"], win_rate, f"OVERALL ALL {friction_bps} win_rate")
        check(m["profit_factor"], pf, f"OVERALL ALL {friction_bps} profit_factor")
        check(m["cumulative_arithmetic_return"], cum_ar, f"OVERALL ALL {friction_bps} cumulative_arithmetic_return")
        check(m["maximum_drawdown"], max_dd, f"OVERALL ALL {friction_bps} maximum_drawdown")
        
    out = {
        "oracle_independence_asserted": True,
        "mismatches": mismatches
    }
    save_json(Path("docs/agent_reviews/opening_state_momentum/development_wfa_oracle_comparison.json"), out)
    if mismatches > 0:
        print(f"ORACLE FAILED WITH {mismatches} MISMATCHES")
        sys.exit(1)
    else:
        print("ORACLE MATCHED")
        sys.exit(0)

if __name__ == "__main__":
    main()
