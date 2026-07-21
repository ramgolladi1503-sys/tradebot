import json
import os
import pandas as pd
from core.option_backtest.adapter import build_candidate_from_candle
from core.option_backtest.models import OptionBacktestConfig, ResearchMode
from pathlib import Path

def test_suspect_8():
    config = OptionBacktestConfig(
        symbol="NIFTY",
        data_path=Path("."),
        research_mode=ResearchMode.PROXY_RESEARCH,
        max_quote_age_seconds=5.0
    )
    
    # We provide a CSV row where the quote is explicitly very old!
    # But because adapter.py ignores it and hardcodes ts_epoch, the age is 0!
    timestamp = pd.Timestamp("2024-01-01 09:15:00")
    
    row = {
        "timestamp": timestamp,
        "quote_ts": timestamp - pd.Timedelta(seconds=10), # Quote is 10 seconds old
        "bid": 100,
        "ask": 102,
        "has_bid_ask": True,
        "close": 101,
        "side": "BUY"
    }
    
    # Actually, the adapter doesn't even look at "quote_ts".
    # It just builds the snapshot using timestamp.
    
    candidate = build_candidate_from_candle(row, config)
    
    quote_age_sec = candidate.get("quote_age_ms", 0) / 1000.0
    
    has_bug = quote_age_sec == 0.0
    
    result = {
        "suspect_id": "8",
        "name": "Bar vs quote timestamp contract",
        "classification": "CONFIRMED_FALSE_POSITIVE_BUG" if has_bug else "NOT_A_BUG",
        "expected_value_rule": "Quote age should reflect real delay if CSV contains true quote timestamp, instead of hardcoding to 0.",
        "actual_value": f"quote_age_sec is always {quote_age_sec} because adapter passes ts_epoch for both evaluated_at and snapshot[ts]",
        "bias": "Hardcoding age to 0 accepts stale quotes that should have been rejected."
    }

    out_path = "runtime/research/upstream_backtest_integrity_antigravity/quote_age_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    existing = []
    if os.path.exists(out_path):
        with open(out_path, "r") as f:
            try: existing = json.load(f)
            except: pass
    if not isinstance(existing, list): existing = []
    existing = [r for r in existing if r.get("suspect_id") != "8"]
    existing.append(result)
    
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)

if __name__ == "__main__":
    test_suspect_8()
