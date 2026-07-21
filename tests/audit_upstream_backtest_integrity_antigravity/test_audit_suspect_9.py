import pytest
import pandas as pd
from core.vectorized_signals import build_vectorized_signals

@pytest.mark.xfail(strict=True, reason="bug confirmed")
def test_suspect_9_vector_index():
    idx = pd.date_range('2024-01-01 09:15:00', periods=50, freq='5min')
    str_idx = pd.Index([str(x) for x in idx])
    
    df = pd.DataFrame({
        'open': range(50), 
        'high': range(10, 60), 
        'low': range(-10, 40), 
        'close': range(50), 
        'volume': [1000] * 50
    }, index=str_idx)
    
    class MockConfig: pass
    
    signals = build_vectorized_signals(df, MockConfig())
    
    pos_indices = df.index.get_indexer(signals.index)
    
    has_bug = False
    if len(pos_indices) > 0:
        has_bug = any(p == -1 for p in pos_indices)
    else:
        has_bug = not df.index.equals(signals.index) and isinstance(signals.index, pd.DatetimeIndex) and not isinstance(df.index, pd.DatetimeIndex)

    # Intended contract: signals index should be same type as df index so get_indexer doesn't return -1
    assert not has_bug, "Intended contract: Signals index type must match original df index type"
