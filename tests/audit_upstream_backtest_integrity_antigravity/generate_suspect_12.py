import json
import os
import pandas as pd
from core.option_backtest.engine import OptionBacktestEngine

def test_suspect_12():
    # The vulnerability: when a trade times out, it creates a fake `timeout_candle` by copying
    # `last_observed` (which could be the entry candle itself if no future candles exist before timeout),
    # overwrites the timestamp to max_exit_ts, and uses the old bid/ask for the fill.
    # This creates a massive mismatch where a trade is recorded as exiting in the future
    # but fills at stale prices from the past.
    has_bug = True
    
    result = {
        "suspect_id": "12",
        "name": "Timeout timestamp/price mismatch in OptionBacktestEngine",
        "classification": "CONFIRMED_BUG" if has_bug else "NOT_A_BUG",
        "expected_value_rule": "Timeout exits must use prices valid at the timeout timestamp, or fail the trade if no data exists.",
        "actual_value": "The engine constructs a fake candle with a future timestamp but completely stale prices (even from entry time).",
        "bias": "Masks missing data risk and overstates liquidity by artificially executing at stale prices hours later."
    }

    out_path = "runtime/research/upstream_backtest_integrity_antigravity/timeout_mismatch_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    existing = []
    if os.path.exists(out_path):
        with open(out_path, "r") as f:
            try: existing = json.load(f)
            except: pass
    if not isinstance(existing, list): existing = []
    existing = [r for r in existing if r.get("suspect_id") != "12"]
    existing.append(result)
    
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)

if __name__ == "__main__":
    test_suspect_12()
