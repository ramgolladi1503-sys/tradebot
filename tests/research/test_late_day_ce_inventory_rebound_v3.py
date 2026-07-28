from __future__ import annotations

import pandas as pd

from scripts.run_extreme_option_pressure_discovery_v2 import Metrics
from scripts.run_late_day_ce_inventory_rebound_v3 import (
    _two_half_positive,
    candidate_mask,
    control_gate,
)


def test_candidate_mask_requires_ce_capitulation_and_pe_expansion() -> None:
    frame = pd.DataFrame(
        {
            "option_type": ["CE", "PE", "CE"],
            "minute_of_day": [800, 800, 760],
            "prior_5m_return_pct": [-12.0, -12.0, -12.0],
            "prior_5m_volume_ratio": [4.0, 4.0, 4.0],
            "return_acceleration": [-8.0, -8.0, -8.0],
            "mirror_return": [10.0, 10.0, 10.0],
            "option_asymmetry": [-22.0, -22.0, -22.0],
            "entry_price_next_open": [90.0, 90.0, 90.0],
            "days_to_expiry": [1, 1, 1],
            "surface_count": [4, 4, 4],
            "volume": [100, 100, 100],
        }
    )
    cut = {
        "ret_p10": -9.0,
        "volume_p90": 3.0,
        "accel_p10": -6.0,
        "ret_p80": 4.0,
        "asym_p10": -15.0,
    }
    assert candidate_mask(frame, cut).tolist() == [True, False, False]


def test_two_half_stability_requires_both_halves_positive() -> None:
    positive = pd.DataFrame(
        {
            "session_id": [f"s{index:02d}" for index in range(10)],
            "timestamp": pd.date_range("2026-01-01", periods=10, freq="D", tz="UTC"),
            "net_return_pct": [1.0] * 10,
        }
    )
    unstable = positive.copy()
    unstable.loc[:4, "net_return_pct"] = -2.0
    assert _two_half_positive(positive) is True
    assert _two_half_positive(unstable) is False


def test_control_gate_requires_directional_and_delay_survival() -> None:
    primary = Metrics(20, 1.8, 2.0, 1.0, 0.6, 40.0, 1.4, 1.3, 0.2, 3.8, 0, 0, 0.2)
    mirror = Metrics(18, 0.8, -0.5, -0.2, 0.4, -9.0, 0.6, 0.5, None, None, 0, 0, 0.3)
    delayed = Metrics(16, 1.2, 0.8, 0.3, 0.55, 12.8, 1.0, 1.0, None, None, 0, 0, 0.25)
    assert control_gate(primary, mirror, delayed) is True
    weak_delayed = Metrics(16, 0.7, -0.2, -0.1, 0.4, -3.2, 0.5, 0.4, None, None, 0, 0, 0.4)
    assert control_gate(primary, mirror, weak_delayed) is False
