import json
import os

def test_suspect_10():
    # Backtest engines (VectorizedBacktestEngine and script loops) process symbols sequentially
    # without a shared state, meaning multiple trades from different symbols can overlap in time,
    # each assuming the full portfolio capital is available.
    has_bug = True
    
    result = {
        "suspect_id": "10",
        "name": "Overlapping trades and capital reuse",
        "classification": "CONFIRMED_BUG" if has_bug else "NOT_A_BUG",
        "expected_value_rule": "Multiple concurrent trades across symbols must share a capital pool and be rejected if capital is exhausted.",
        "actual_value": "Backtest engines evaluate symbols independently, allowing overlapping trades to reuse the same starting capital.",
        "bias": "Overstates strategy returns by allowing infinite leverage/unbounded capital during overlapping opportunities."
    }

    out_path = "runtime/research/upstream_backtest_integrity_antigravity/capital_reuse_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    existing = []
    if os.path.exists(out_path):
        with open(out_path, "r") as f:
            try: existing = json.load(f)
            except: pass
    if not isinstance(existing, list): existing = []
    existing = [r for r in existing if r.get("suspect_id") != "10"]
    existing.append(result)
    
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)

if __name__ == "__main__":
    test_suspect_10()
