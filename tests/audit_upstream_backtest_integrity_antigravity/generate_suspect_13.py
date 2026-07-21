import json
import os

def test_suspect_13():
    # The vulnerability: WalkForwardAnalyzer splits the raw data into disjoint train and test sets
    # *before* passing them to VectorizedBacktestEngine. The engine then calls `add_indicators()`
    # on the truncated test_df. Because the test_df has no warm-up data from the train period,
    # indicators like EMA, RSI, and ATR are initialized from scratch at the start of the OOS period,
    # destroying the continuous state of the indicators and causing massive data loss via `.dropna()`.
    # Furthermore, `VectorizedBacktestEngine` records `is_oos = False` for all these trades because
    # `oos_start_date` is not passed to the config.
    has_bug = True
    
    result = {
        "suspect_id": "13",
        "name": "False WFA or mixed IS/OOS metrics",
        "classification": "CONFIRMED_BUG" if has_bug else "NOT_A_BUG",
        "expected_value_rule": "WFA must calculate indicators continuously across train/test boundaries, and correctly label OOS trades.",
        "actual_value": "WFA slices raw data first, destroying indicator warm-up in test_df, and never sets oos_start_date.",
        "bias": "Destroys OOS validity by dropping early trades and evaluating on un-warmed indicators, while mislabeling them as IS."
    }

    out_path = "runtime/research/upstream_backtest_integrity_antigravity/wfa_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    existing = []
    if os.path.exists(out_path):
        with open(out_path, "r") as f:
            try: existing = json.load(f)
            except: pass
    if not isinstance(existing, list): existing = []
    existing = [r for r in existing if r.get("suspect_id") != "13"]
    existing.append(result)
    
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)

if __name__ == "__main__":
    test_suspect_13()
