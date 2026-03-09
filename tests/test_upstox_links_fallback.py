import pandas as pd

from dashboard.streamlit_app_runtime import _add_upstox_links


def test_upstox_links_are_disabled_in_runtime_ui():
    df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "instrument": "OPT",
                "expiry_date": "2026-02-27",
                "strike": 25000,
                "option_type": "CE",
            }
        ]
    )
    out = _add_upstox_links(df)
    assert list(out.columns) == list(df.columns)
    assert "upstox_contract_url" not in out.columns
    assert "upstox_search_url" not in out.columns
