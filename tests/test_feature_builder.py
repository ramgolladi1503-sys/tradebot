import pandas as pd
from core.feature_builder import add_indicators

def test_add_indicators_columns():
    df = pd.DataFrame({
        "open": [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],
        "high": [2]*15,
        "low": [1]*15,
        "close": [1]*15,
        "volume": [100]*15
    })
    out = add_indicators(df)
    assert "vwap" in out.columns
    assert "vwap_slope" in out.columns
    assert "rsi_mom" in out.columns
    assert "vol_z" in out.columns
