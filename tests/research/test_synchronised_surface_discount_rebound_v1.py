from __future__ import annotations

import pandas as pd

from scripts import run_inventory_absorption_transition_v1 as common
from scripts import run_synchronised_surface_discount_rebound_v1 as runner


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "expired_instrument_key": ["a", "a", "b"],
            "timestamp": pd.to_datetime(["2026-01-01 09:45Z", "2026-01-01 09:50Z", "2026-01-01 09:45Z"]),
            "session_id": ["s1", "s1", "s1"],
            "entry_price_next_open": [100.0, 105.0, 110.0],
            "days_to_expiry": [1, 1, 1],
            "surface_count": [5, 5, 5],
            "volume": [100, 100, 100],
            "prior_5m_return_pct": [-4.0, -3.0, -1.0],
            "previous_return": [-6.0, -4.0, -2.0],
            "return_acceleration": [2.0, 1.0, 0.5],
            "prior_5m_volume_ratio": [3.0, 2.5, 1.1],
            "volume_acceleration": [1.5, 0.5, 0.1],
            "oi_change_ratio": [0.3, 0.2, 0.0],
            "mirror_return": [1.0, 0.5, -2.0],
            "mirror_acceleration": [0.2, 0.1, -1.0],
            "breadth_positive": [0.1, 0.2, 0.8],
            "breadth_delta": [0.3, 0.2, -0.1],
            "breadth_acceleration": [0.6, 0.3, -0.1],
            "surface_median_return": [-3.0, -2.0, 1.0],
            "surface_median_acceleration": [1.0, 0.4, -0.1],
            "surface_return_dispersion": [0.3, 0.4, 2.0],
            "breadth_volume": [0.8, 0.6, 0.2],
            "prior_10m_range_pct": [0.5, 0.6, 2.0],
            "minute_of_day": [620, 625, 620],
            "option_type": ["CE", "CE", "PE"],
        }
    )


def test_masks_detect_synchronised_washout() -> None:
    frame = _frame()
    cut = {
        "ret15": -5.0,
        "ret25": -3.5,
        "ret35": -2.5,
        "acc60": 0.5,
        "acc70": 0.8,
        "acc80": 1.5,
        "vol60": 2.0,
        "vol70": 2.8,
        "vacc70": 1.0,
        "oi60": 0.1,
        "oi70": 0.25,
        "breadth25": 0.2,
        "breadth35": 0.3,
        "bdelta60": 0.1,
        "bdelta70": 0.25,
        "bacc60": 0.3,
        "surface25": -2.5,
        "surface35": -1.5,
        "sacc60": 0.5,
        "disp25": 0.35,
        "disp35": 0.5,
        "range25": 0.7,
        "mirror60": 0.0,
    }
    masks = runner.masks(frame, cut)
    assert masks["low_dispersion_surface_washout_rebound"].iloc[0]
    assert masks["volume_absorption_after_washout"].iloc[0]
    assert not masks["low_dispersion_surface_washout_rebound"].iloc[2]


def test_onset_only_keeps_first_true_per_instrument_run() -> None:
    frame = _frame()
    mask = pd.Series([True, True, True])
    onset = runner.onset(frame, mask)
    assert onset.tolist() == [True, False, True]


def test_oof_gate_rejects_negative_median_despite_many_trades() -> None:
    metric = common.Metrics(
        trades=120,
        sessions=90,
        profit_factor=1.50,
        mean_return_pct=0.40,
        median_return_pct=-0.01,
        win_rate=0.52,
        net_return_pct_sum=48.0,
        remove_top_five_profit_factor=1.20,
        remove_top_three_profit_factor=1.20,
        stress_profit_factor=1.10,
        bootstrap_mean_ci_low=0.10,
        bootstrap_mean_ci_high=0.80,
        positive_folds=4,
        total_folds=4,
        positive_halves=2,
        total_halves=2,
        largest_winner_share=0.05,
        largest_session_share=0.05,
    )
    assert not runner.oof_gate(metric)


def test_holdout_gate_requires_both_halves() -> None:
    metric = common.Metrics(
        trades=30,
        sessions=24,
        profit_factor=1.40,
        mean_return_pct=0.50,
        median_return_pct=0.10,
        win_rate=0.55,
        net_return_pct_sum=15.0,
        remove_top_five_profit_factor=1.10,
        remove_top_three_profit_factor=1.10,
        stress_profit_factor=1.05,
        bootstrap_mean_ci_low=0.05,
        bootstrap_mean_ci_high=0.90,
        positive_folds=4,
        total_folds=4,
        positive_halves=1,
        total_halves=2,
        largest_winner_share=0.10,
        largest_session_share=0.10,
    )
    assert not runner.holdout_gate(metric)
