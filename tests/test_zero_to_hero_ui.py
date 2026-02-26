from __future__ import annotations

import pandas as pd

from dashboard.streamlit_app_runtime import _zero_to_hero_display_columns


def test_zero_to_hero_table_columns_minimal():
    df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "expiry_date": "2026-03-06",
                "strike": 25000,
                "option_type": "CE",
                "entry": 10.0,
                "stop": 6.0,
                "target": 18.0,
                "premium": 10.0,
                "confidence": 0.72,
                "status": "PLANNING",
                "pnl_1lot": None,
                "note": "PAPER only, non-executable",
                "strategy": "ZERO_TO_HERO",
                "regime": "TREND",
                "tier": "EXPLORATION",
                "category": "lotto",
            }
        ]
    )
    cols = _zero_to_hero_display_columns(df)
    assert "strategy" not in cols
    assert "regime" not in cols
    assert "tier" not in cols
    assert "category" not in cols
    assert cols == [
        "symbol",
        "expiry_date",
        "strike",
        "option_type",
        "entry",
        "stop",
        "target",
        "premium",
        "confidence",
        "status",
        "pnl_1lot",
        "note",
    ]
