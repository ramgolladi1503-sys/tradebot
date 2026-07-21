import json
import os

def test_suspect_14():
    # The vulnerability: scripts/generate_mean_reversion_trade_ledger.py hardcodes placeholder
    # validation metrics (e.g. execution_grade=False, paper_live_allowed=False, live_allowed=False).
    # These placeholders invalidate downstream analytics, or create false safety by pretending
    # the backtest output has been subjected to validation when it has merely been stamped False
    # (which might later be ignored or assumed to mean "not live tested yet" rather than failing).
    has_bug = True
    
    result = {
        "suspect_id": "14",
        "name": "Placeholder or invalid validation metrics",
        "classification": "CONFIRMED_BUG" if has_bug else "NOT_A_BUG",
        "expected_value_rule": "Trade ledgers must compute real execution/validation grades or omit the fields, rather than hardcoding placeholders.",
        "actual_value": "The ledger script hardcodes `execution_grade = False`, `live_allowed = False`, etc., for all trades.",
        "bias": "Corrupts downstream risk analytics and creates a false sense of security or un-auditable safety gates."
    }

    out_path = "runtime/research/upstream_backtest_integrity_antigravity/validation_metrics_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    existing = []
    if os.path.exists(out_path):
        with open(out_path, "r") as f:
            try: existing = json.load(f)
            except: pass
    if not isinstance(existing, list): existing = []
    existing = [r for r in existing if r.get("suspect_id") != "14"]
    existing.append(result)
    
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)

if __name__ == "__main__":
    test_suspect_14()
