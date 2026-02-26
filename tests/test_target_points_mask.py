import pandas as pd

from dashboard.streamlit_app_runtime import _mask_unresolved_prices


def test_mask_unresolved_prices_clears_values_for_unresolved_contract():
    df = pd.DataFrame(
        [
            {
                "instrument": "OPT",
                "entry": 100.0,
                "stop": 90.0,
                "target": 120.0,
                "target_points": 20.0,
                "instrument_id": None,
                "tradingsymbol": None,
                "expiry_date": None,
                "tradable": False,
                "tradable_reasons_blocking": ["unresolved_contract"],
            }
        ]
    )
    out = _mask_unresolved_prices(df.copy())
    assert out.loc[0, "entry"] is None
    assert out.loc[0, "stop"] is None
    assert out.loc[0, "target"] is None
    assert out.loc[0, "target_points"] is None


def test_mask_unresolved_prices_keeps_values_for_resolved_contract():
    df = pd.DataFrame(
        [
            {
                "instrument": "OPT",
                "entry": 100.0,
                "stop": 90.0,
                "target": 120.0,
                "target_points": 20.0,
                "instrument_id": "NIFTY|2026-03-02|25000.0|CE",
                "tradingsymbol": "NIFTY2630225000CE",
                "expiry_date": "2026-03-02",
                "tradable": True,
            }
        ]
    )
    out = _mask_unresolved_prices(df.copy())
    assert out.loc[0, "entry"] == 100.0
    assert out.loc[0, "stop"] == 90.0
    assert out.loc[0, "target"] == 120.0
    assert out.loc[0, "target_points"] == 20.0
