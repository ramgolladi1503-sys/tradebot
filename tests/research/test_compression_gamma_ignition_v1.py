from __future__ import annotations

import pandas as pd

from scripts import run_compression_gamma_ignition_v1 as subject


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "expired_instrument_key": ["a", "a", "b", "b"],
            "timestamp": pd.to_datetime([
                "2026-01-01T04:00:00Z",
                "2026-01-01T04:05:00Z",
                "2026-01-01T04:00:00Z",
                "2026-01-01T04:05:00Z",
            ], utc=True),
            "session_id": ["2026-01-01"] * 4,
            "expiry_id": ["2026-01-02"] * 4,
            "option_type": ["CE", "CE", "PE", "PE"],
            "strike": [24000, 24000, 24000, 24000],
            "entry_price_next_open": [80.0, 82.0, 78.0, 77.0],
            "days_to_expiry": [1, 1, 1, 1],
            "surface_count": [4, 4, 4, 4],
            "volume": [10, 30, 10, 30],
            "prior_10m_range_pct": [0.2, 0.1, 0.2, 0.1],
            "prior_5m_return_pct": [0.0, 0.005, 0.0, 0.004],
            "previous_return": [-0.1, 0.0, -0.1, 0.0],
            "return_acceleration": [0.1, 0.6, 0.1, 0.5],
            "prior_5m_volume_ratio": [0.9, 3.0, 0.9, 2.8],
            "volume_acceleration": [0.0, 2.1, 0.0, 1.9],
            "oi_change_ratio": [0.0, 0.2, 0.0, 0.2],
            "mirror_return": [0.0, -0.3, 0.0, -0.2],
            "mirror_acceleration": [0.0, -0.1, 0.0, -0.1],
            "option_asymmetry": [0.0, 0.9, 0.0, 0.7],
            "breadth_positive": [0.25, 0.75, 0.25, 0.75],
            "breadth_delta": [0.0, 0.5, 0.0, 0.5],
            "breadth_volume": [0.25, 0.75, 0.25, 0.75],
            "surface_return_dispersion": [0.2, 0.1, 0.2, 0.1],
            "surface_median_return": [0.0, 0.5, 0.0, 0.5],
            "surface_median_acceleration": [0.0, 0.4, 0.0, 0.4],
            "directional_mass_shift": [0.0, 20.0, 0.0, 20.0],
            "minute_of_day": [600, 605, 600, 605],
            "bar_acceptance": [False, True, False, True],
        }
    )


def test_thresholds_and_masks_are_deterministic() -> None:
    frame = _frame()
    cuts = subject.thresholds(frame)
    masks = subject.masks(frame, cuts)
    assert set(masks) == set(subject.MECHANISMS)
    assert masks["quiet_contract_volume_ignition"].dtype == bool
    assert bool(masks["low_premium_gamma_kick"].iloc[1]) is True


def test_onset_keeps_first_true_only_per_instrument_run() -> None:
    frame = _frame()
    mask = pd.Series([False, True, True, False], index=frame.index)
    onset = subject.onset(frame, mask)
    assert onset.tolist() == [False, True, True, False]


def test_select_respects_session_cap_and_cooldown() -> None:
    frame = pd.concat([_frame(), _frame().assign(timestamp=lambda x: x["timestamp"] + pd.Timedelta(minutes=25))], ignore_index=True)
    mask = pd.Series([True] * len(frame), index=frame.index)
    selected = subject.select(frame, mask, "quiet_contract_volume_ignition", ["2026-01-01"])
    assert len(selected) <= subject.MAX_SIGNALS_PER_SESSION
    assert selected["mechanism"].eq("quiet_contract_volume_ignition").all()


def test_contract_constants_are_research_only() -> None:
    assert subject.NORMAL_COST_PCT == 0.10
    assert subject.STRESS_COST_PCT == 1.00
    assert subject.MAX_SIGNALS_PER_SESSION == 2
