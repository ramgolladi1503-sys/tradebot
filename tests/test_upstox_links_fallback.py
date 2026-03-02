import pandas as pd

from dashboard.streamlit_app_runtime import _add_upstox_links


def test_upstox_links_fallback_search():
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
    assert out.loc[0, "upstox_search_url"]
    assert pd.isna(out.loc[0, "upstox_contract_url"]) or out.loc[0, "upstox_contract_url"] == ""


def test_upstox_links_contract_url(monkeypatch):
    from config import config as cfg
    monkeypatch.setattr(cfg, "UPSTOX_ENABLE_DEEPLINK", True, raising=False)
    df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "instrument": "OPT",
                "expiry_date": "2026-02-27",
                "strike": 25000,
                "option_type": "CE",
                "upstox_instrument_key": "TESTKEY",
                "instrument_id": "NIFTY26FEB25000CE",
            }
        ]
    )
    out = _add_upstox_links(df)
    assert out.loc[0, "upstox_contract_url"]
