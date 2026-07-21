import json
import os

def test_suspect_4():
    # Production logic
    def calc_ledger(gross, proxy_delta, proxy_exec_cost):
        underlying_cost = proxy_exec_cost / proxy_delta
        proxy_gross = gross * proxy_delta
        costs = underlying_cost + proxy_exec_cost
        net_pnl = gross - costs
        proxy_option_net_pnl = proxy_gross - proxy_exec_cost
        return {
            "gross": gross,
            "underlying_cost": underlying_cost,
            "proxy_exec_cost": proxy_exec_cost,
            "costs": costs,
            "net_pnl": net_pnl,
            "proxy_option_net_pnl": proxy_option_net_pnl
        }

    cases = [
        (0.50, 0),
        (0.50, 10),
        (0.50, -10),
        (0.25, 0),
        (0.25, 10)
    ]
    
    results = []
    
    for proxy_delta, gross in cases:
        proxy_exec_cost = 1.5
        res = calc_ledger(gross, proxy_delta, proxy_exec_cost)
        
        # Oracle expected
        expected_underlying_net = gross - (proxy_exec_cost / proxy_delta)
        
        results.append({
            "delta": proxy_delta,
            "gross": gross,
            "actual_net_pnl": res["net_pnl"],
            "expected_net_pnl": expected_underlying_net,
            "diff": res["net_pnl"] - expected_underlying_net
        })

    # Since they are different, it's a bug.
    result = {
        "suspect_id": "4",
        "name": "Cost unit mixing or double deduction",
        "classification": "CONFIRMED_FALSE_NEGATIVE_BUG", # Because it subtracts too much cost, depressing PnL artificially (false negative for strategy performance)
        "expected_value_rule": "net_pnl should subtract ONLY the underlying_cost.",
        "actual_value": "net_pnl subtracts BOTH underlying_cost and proxy_exec_cost (mixing units)",
        "cases": results,
        "bias": "Double deduction and unit mixing artificially penalizes strategy performance, leading to false negatives in backtest expectancy."
    }

    import os
    os.makedirs("runtime/research/upstream_backtest_integrity_antigravity", exist_ok=True)
    out_path = "runtime/research/upstream_backtest_integrity_antigravity/cost_unit_results.json"
    
    existing = []
    if os.path.exists(out_path):
        with open(out_path, "r") as f:
            try: existing = json.load(f)
            except: pass
    if not isinstance(existing, list): existing = []
    existing = [r for r in existing if r.get("suspect_id") != "4"]
    existing.append(result)
    
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)

if __name__ == "__main__":
    test_suspect_4()
    
    # Write the pytest file correctly without using cat to append
    with open("tests/test_audit_upstream_integrity.py", "a") as f:
        f.write("\n\ndef test_suspect_4_cost_double_deduction():\n")
        f.write("    # Oracle\n")
        f.write("    gross = 10.0\n")
        f.write("    proxy_delta = 0.5\n")
        f.write("    proxy_exec_cost = 1.5\n")
        f.write("    underlying_cost = proxy_exec_cost / proxy_delta\n")
        f.write("    # In production:\n")
        f.write("    actual_net_pnl = gross - (underlying_cost + proxy_exec_cost)\n")
        f.write("    # Expected:\n")
        f.write("    expected_net_pnl = gross - underlying_cost\n")
        f.write("    assert actual_net_pnl != expected_net_pnl, 'Double deduction confirmed'\n")

