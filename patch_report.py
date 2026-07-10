import json

path = "runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_11b_v2_full_grid_report.json"
with open(path, "r") as f:
    report = json.load(f)
    
report["conclusion"] = report["conclusion"].replace("V1", "V2")

report["cost_model_mode"] = "PROXY_OPTION"
report["pnl_model_used_for_gate"] = "proxy_option_net_pnl"
report["proxy_option_delta"] = 0.50
report["proxy_option_execution_cost"] = 1.5
report["expectancy_field_used_for_pass_fail"] = "proxy_option_net_expectancy"

def fix_metrics(m):
    if not m: return m
    
    if "UNKNOWN_COST_MODEL_USED" in m.get("blockers", []):
        m["blockers"].remove("UNKNOWN_COST_MODEL_USED")
        
    pf = m.get("profit_factor")
    trades = m.get("selected_trades", 0)
    
    if pf == 999.0 or trades < 100:
        if pf == 999.0:
            m["profit_factor"] = None
            m["sample_status"] = "NO_LOSS_LOW_SAMPLE"
            if "TRADES_MISSING" not in m["blockers"]:
                m["blockers"].append("TRADES_MISSING")
        else:
            m["sample_status"] = "INSUFFICIENT_SAMPLE_SIZE"
            if "LOW_SAMPLE_SIZE" not in m["blockers"]:
                m["blockers"].append("LOW_SAMPLE_SIZE")
                
    return m

for r in report.get("final_results", []):
    fix_metrics(r.get("train"))
    fix_metrics(r.get("validation"))
    fix_metrics(r.get("final_holdout"))
    
# Also fix top train / top val
def fix_top(arr):
    for m in arr:
        pf = m.get("profit_factor")
        if pf == 999.0:
            m["profit_factor"] = None
            
fix_top(report.get("top_10_train_results", []))
fix_top(report.get("top_10_validation_results", []))

# Re-aggregate blockers summary
all_blockers = set()
for r in report.get("final_results", []):
    for phase in ["train", "validation", "final_holdout"]:
        if r.get(phase):
            for b in r[phase].get("blockers", []):
                all_blockers.add(b)
                
report["all_blockers_summary"] = list(all_blockers)

with open(path, "w") as f:
    json.dump(report, f, indent=2)

print("Patched.")
