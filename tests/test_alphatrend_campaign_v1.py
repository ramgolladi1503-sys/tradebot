import pandas as pd

from research.alphatrend_mechanism_v1.campaign import (
    PREDECLARED_CONFIGS,
    run_development_campaign,
)


def _bars(session, rows=120):
    timestamp = pd.date_range(f"{session} 09:15", periods=rows, freq="min")
    values = []
    for i in range(rows):
        cycle = (0, 2, 5, 3, 1, 4)[i % 6]
        values.append(25000.0 + 0.8 * i + cycle)
    return pd.DataFrame(
        {
            "timestamp": timestamp,
            "open": values,
            "high": [value + 1.5 for value in values],
            "low": [value - 1.5 for value in values],
            "close": [value + 0.2 for value in values],
            "volume": [1000 + i for i in range(rows)],
        }
    )


def test_campaign_is_predeclared_and_cannot_promote_or_touch_holdout():
    bars = pd.concat(
        [_bars(f"2026-08-{day:02d}") for day in range(3, 8)],
        ignore_index=True,
    )
    result = run_development_campaign(bars)
    assert result["scope"] == "DEVELOPMENT_ONLY"
    assert result["holdout_evaluated"] is False
    assert result["validation_evaluated"] is False
    assert result["parameter_family_predeclared"] is True
    assert set(result["variants"]) == set(PREDECLARED_CONFIGS)
    for variant in result["variants"].values():
        assert variant["screen"]["fresh"]["promotion_authorized"] is False
        assert variant["screen"]["continuation"]["promotion_authorized"] is False
