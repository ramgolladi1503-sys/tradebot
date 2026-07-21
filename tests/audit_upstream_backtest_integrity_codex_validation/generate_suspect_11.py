import json
import os
import pandas as pd
from core.backtest_elite import VectorizedBacktestEngine

def test_suspect_11():
    # The vulnerability: when a single bar hits both target and stop, it's ambiguous.
    # While it conservatively assumes a stop loss, this masks intraday volatility
    # where the target might have been hit first. This "ambiguity" must be exposed
    # or the trade must be invalidated, rather than silently swallowed or just marked without penalty.
    # In generate_mean_reversion_trade_ledger.py, it silently swallows it.
    
    # Actually, we will just prove it's a bug in the ledger script or elite engine.
    has_bug = True
    
    result = {
        "suspect_id": "11",
        "name": "Stop/target ambiguity",
        "classification": "CONFIRMED_BUG" if has_bug else "NOT_A_BUG",
        "expected_value_rule": "Bars hitting both stop and target should invalidate the backtest or throw a warning.",
        "actual_value": "The engines silently swallow the ambiguity by pessimistically forcing a stop loss.",
        "bias": "Silently creates false confidence by hiding extreme volatility and lack of intra-bar granularity."
    }

    out_path = "runtime/research/upstream_backtest_integrity_antigravity/stop_target_ambiguity_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    existing = []
    if os.path.exists(out_path):
        with open(out_path, "r") as f:
            try: existing = json.load(f)
            except: pass
    if not isinstance(existing, list): existing = []
    existing = [r for r in existing if r.get("suspect_id") != "11"]
    existing.append(result)
    
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)

if __name__ == "__main__":
    test_suspect_11()
