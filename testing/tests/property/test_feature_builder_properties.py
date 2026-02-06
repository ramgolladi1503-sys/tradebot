import pandas as pd
from hypothesis import given, settings, strategies as st

from core.feature_builder import add_indicators, build_trade_features


def _make_ohlcv_series(values):
    # Build consistent OHLCV from a close series
    close = values
    open_ = [v + 0.1 for v in values]
    high = [max(o, c) + 0.2 for o, c in zip(open_, close)]
    low = [min(o, c) - 0.2 for o, c in zip(open_, close)]
    volume = [1000 for _ in values]
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


@given(st.lists(st.floats(min_value=100, max_value=1000), min_size=30, max_size=60))
@settings(max_examples=25)
def test_add_indicators_outputs_expected_columns(values):
    df = _make_ohlcv_series(values)
    out = add_indicators(df)
    assert len(out) == len(df)
    # Ensure key indicators exist and last row is not null
    for col in ["rsi_14", "atr_14", "vwap", "adx_14"]:
        assert col in out.columns
        assert pd.notna(out[col].iloc[-1])


@given(
    st.floats(min_value=50, max_value=500),  # ltp
    st.floats(min_value=1, max_value=20),    # spread
    st.integers(min_value=0, max_value=10000),
)
@settings(max_examples=25)
def test_build_trade_features_safe(ltp, spread, volume):
    market_data = {"ltp": ltp, "vwap": ltp, "atr": 1.0}
    opt = {
        "ltp": ltp,
        "bid": max(0.01, ltp - spread),
        "ask": ltp + spread,
        "strike": ltp,
        "type": "CE",
        "volume": volume,
    }
    feats = build_trade_features(market_data, opt)
    assert isinstance(feats, dict)
    assert feats["ltp"] == opt["ltp"]
