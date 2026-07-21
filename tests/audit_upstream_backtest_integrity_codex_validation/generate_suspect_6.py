import json
import os
from core.fill_model import FillModel

def test_suspect_6():
    fm = FillModel()
    
    order = {"side": "BUY", "symbol": "TEST", "qty": 10000, "limit_price": 100.0}
    market = {
        "bid": 90.0,
        "ask": 100.0,
        "bid_qty": 10,
        "ask_qty": 10,
        "volume": 10,
        "oi": 10,
        "allow_fallback_liquidity": True
    }
    
    res = fm.simulate(order, market, "test_run")
    
    fill_price = res["fill_price"]
    slippage_bp = res["slippage_bp"]
    
    expected_slippage_points = 100.0 * (slippage_bp / 10000.0)
    actual_slippage_applied = fill_price - 100.0
    
    bug_confirmed = actual_slippage_applied == 0 and expected_slippage_points > 0
    
    result = {
        "suspect_id": "6",
        "name": "Slippage reported but not applied",
        "classification": "CONFIRMED_FALSE_POSITIVE_BUG" if bug_confirmed else "NOT_A_BUG",
        "expected_value_rule": "fill_price should be worse than the quote by slippage_bp.",
        "actual_value": f"fill_price was {fill_price}, meaning 0 slippage applied, despite slippage_bp={slippage_bp} being calculated.",
        "bias": "Dropping the modeled slippage makes executions unrealistically favorable, causing false positives in strategy expectancy."
    }

    out_path = "runtime/research/upstream_backtest_integrity_antigravity/slippage_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    existing = []
    if os.path.exists(out_path):
        with open(out_path, "r") as f:
            try: existing = json.load(f)
            except: pass
    if not isinstance(existing, list): existing = []
    existing = [r for r in existing if r.get("suspect_id") != "6"]
    existing.append(result)
    
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)

if __name__ == "__main__":
    test_suspect_6()
