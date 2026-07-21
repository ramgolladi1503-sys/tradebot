import json
import os
import pandas as pd
from pathlib import Path
from core.option_backtest.engine import OptionBacktestEngine
from core.option_backtest.models import OptionBacktestConfig, ResearchMode

def test_suspect_5():
    config = OptionBacktestConfig(
        symbol="NIFTY",
        data_path=Path("."),
        quantity=50,
        research_mode=ResearchMode.PROXY_RESEARCH,
        fill_model_run_id="test"
    )
    engine = OptionBacktestEngine(config)
    
    signal_ask = 101.0
    candidate = {
        "side": "BUY",
        "symbol": "NIFTY",
        "execution_entry": signal_ask,
    }
    
    entry_ask = 106.0
    entry_row = pd.Series({
        "timestamp": pd.Timestamp("2024-01-01 09:16:00"),
        "bid": 105.0,
        "ask": entry_ask,
        "bid_qty": 100,
        "ask_qty": 100,
        "volume": 1000,
        "oi": 5000
    })
    
    captured_order = {}
    def mock_simulate(order, snapshot, run_id):
        captured_order.update(order)
        return {"status": "FILLED", "fill_price": order["limit_price"], "slippage_bp": 0.0}
        
    engine.fill_model.simulate = mock_simulate
    engine._simulate_entry(candidate, entry_row, 1)
    
    actual_limit_price_used = captured_order.get("limit_price")
    expected_limit_price = entry_ask
    
    diff = actual_limit_price_used - expected_limit_price
    
    result = {
        "suspect_id": "5",
        "name": "Signal-time limit reused at later entry bar",
        "classification": "CONFIRMED_FALSE_POSITIVE_BUG" if diff != 0 else "NOT_A_BUG",
        "expected_value_rule": "Entry limit price should be based on the entry bar's executable quote.",
        "actual_value": f"Entry limit price used {actual_limit_price_used} (from signal bar) instead of {expected_limit_price} (from entry bar)",
        "bias": "Using the signal-time quote as a resting limit introduces false positive fills if the market touches the old price, instead of hitting the true entry quote."
    }

    out_path = "runtime/research/upstream_backtest_integrity_antigravity/signal_limit_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    existing = []
    if os.path.exists(out_path):
        with open(out_path, "r") as f:
            try: existing = json.load(f)
            except: pass
    if not isinstance(existing, list): existing = []
    existing = [r for r in existing if r.get("suspect_id") != "5"]
    existing.append(result)
    
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)

if __name__ == "__main__":
    test_suspect_5()
