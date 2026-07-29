from __future__ import annotations

import pandas as pd

from scripts import run_high_occurrence_structural_edge_v1 as campaign


def _frame() -> pd.DataFrame:
    rows = []
    for minute in (600, 610, 635, 670):
        rows.append(
            {
                "session_id": "2026-01-01",
                "timestamp": pd.Timestamp("2026-01-01") + pd.Timedelta(minutes=minute),
                "entry_price_next_open": 100.0,
                "minute_of_day": minute,
                "days_to_expiry": 2,
                "surface_count": 5,
                "volume": 100.0,
                "previous_return": 0.1,
                "breadth_delta": 0.5,
                "return_acceleration": 0.4,
                "option_asymmetry": 0.3,
                "prior_5m_volume_ratio": 2.0,
            }
        )
    return pd.DataFrame(rows)


def test_select_independent_limits_two_and_enforces_cooldown() -> None:
    frame = _frame()
    selected = campaign.select_independent(frame, pd.Series(True, index=frame.index), "x", ["2026-01-01"])
    assert len(selected) == 2
    timestamps = sorted(pd.to_datetime(selected["timestamp"]).tolist())
    assert (timestamps[1] - timestamps[0]).total_seconds() >= 1800


def test_mechanism_count_is_predeclared_and_bounded() -> None:
    assert len(campaign.MECHANISMS) == 8
    assert len(set(campaign.MECHANISMS)) == 8


def test_holdout_gate_requires_twenty_trades() -> None:
    metric = campaign.research.Metrics(
        trades=19,
        profit_factor=9.0,
        mean_return_pct=2.0,
        median_return_pct=1.0,
        win_rate=0.8,
        net_return_pct_sum=20.0,
        remove_top_two_profit_factor=5.0,
        stress_profit_factor=3.0,
        bootstrap_mean_ci_low=0.1,
        bootstrap_mean_ci_high=3.0,
        positive_folds=4,
        total_folds=4,
        largest_winner_share=0.1,
    )
    trades = pd.DataFrame({"session_id": [f"s{i}" for i in range(19)]})
    assert campaign.holdout_gate(metric, trades) is False
