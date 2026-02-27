import pandas as pd

from core.upstox_resolver import ensure_upstox_columns


def test_ensure_upstox_columns_adds_missing():
    df = pd.DataFrame([{"symbol": "NIFTY"}])
    out = ensure_upstox_columns(df)
    assert out is not None
    for col in (
        "upstox_instrument_key",
        "upstox_contract_url",
        "upstox_search_url",
        "upstox_query",
        "unresolved_contract",
    ):
        assert col in out.columns
