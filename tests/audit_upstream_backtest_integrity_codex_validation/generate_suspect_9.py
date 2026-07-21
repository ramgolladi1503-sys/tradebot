import json
import os
import pandas as pd
from core.vectorized_signals import build_vectorized_signals
from core.backtest_elite import VectorizedBacktestEngine

def test_suspect_9():
    # To trigger the bug, self.data must not have a "timestamp" column,
    # and its index must be strings (not DatetimeIndex).
    # Then backtest_elite won't convert self.data.index to DatetimeIndex,
    # but build_vectorized_signals will convert its COPY's index to DatetimeIndex.
    # get_indexer will then compare DatetimeIndex against String Index, returning -1.
    
    idx = pd.date_range("2024-01-01 09:15:00", periods=50, freq="5min")
    # Make index strings
    str_idx = pd.Index([str(x) for x in idx])
    
    # We must provide enough data for valid_vol and trend so that it generates a signal.
    # VWAP slope, ATR, RSI, ADX...
    # It's easier to just mock build_vectorized_signals, but the bug is in the interaction
    # between backtest_elite and build_vectorized_signals.
    # Let's write the test at the unit test level.
    
    class MockConfig:
        pass
        
    cfg = MockConfig()
    
    df = pd.DataFrame({
        "open": range(50),
        "high": range(10, 60),
        "low": range(-10, 40),
        "close": range(50),
        "volume": [1000] * 50
    }, index=str_idx)
    
    has_bug = False
    
    # In backtest_elite.py:
    # 268: if "timestamp" in self.data.columns:
    # 269:     ts = pd.to_datetime(self.data["timestamp"], errors="coerce")
    # 272:     self.data.index = ts
    
    # Simulate backtest_elite.py logic:
    # No "timestamp" column, so self.data.index remains strings
    
    signals = build_vectorized_signals(df, cfg)
    
    # build_vectorized_signals returns a DatetimeIndex, even if df had a string index!
    # pos_indices = self.data.index.get_indexer(signals_df.index)
    pos_indices = df.index.get_indexer(signals.index)
    
    if len(pos_indices) > 0:
        has_bug = any(p == -1 for p in pos_indices)
    else:
        # If no signals generated, we can still verify the types:
        has_bug = not df.index.equals(signals.index) and isinstance(signals.index, pd.DatetimeIndex) and not isinstance(df.index, pd.DatetimeIndex)

    result = {
        "suspect_id": "9",
        "name": "Vector index mapping",
        "classification": "CONFIRMED_BUG" if has_bug else "NOT_A_BUG",
        "expected_value_rule": "Signals index should perfectly align with the original DataFrame index types, or get_indexer should validate -1.",
        "actual_value": f"pos_indices returned -1 due to type mismatch (DatetimeIndex vs String), has_bug={has_bug}",
        "bias": "Index misalignment causes execution on wrong bars (last bar) or crashes."
    }

    out_path = "runtime/research/upstream_backtest_integrity_antigravity/vector_index_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    existing = []
    if os.path.exists(out_path):
        with open(out_path, "r") as f:
            try: existing = json.load(f)
            except: pass
    if not isinstance(existing, list): existing = []
    existing = [r for r in existing if r.get("suspect_id") != "9"]
    existing.append(result)
    
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)

if __name__ == "__main__":
    test_suspect_9()
