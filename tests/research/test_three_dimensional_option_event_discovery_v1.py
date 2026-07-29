from __future__ import annotations

import pandas as pd

from scripts import run_inventory_absorption_transition_v1 as common
from scripts import run_three_dimensional_option_event_discovery_v1 as discovery


def test_three_dimensional_features_use_cross_sectional_neighbourhood_only() -> None:
    timestamp = pd.Timestamp("2025-01-01T10:00:00Z")
    rows = []
    strikes = [100, 110, 120, 130, 140]
    ce_returns = [-4.0, -5.0, -2.0, -6.0, -5.0]
    pe_returns = [3.0, 4.0, 5.0, 4.0, 3.0]
    for option_type, returns in [("CE", ce_returns), ("PE", pe_returns)]:
        for strike, ret in zip(strikes, returns, strict=True):
            rows.append(
                {
                    "session_id": "2025-01-01",
                    "timestamp": timestamp,
                    "expiry_id": "2025-01-02",
                    "option_type": option_type,
                    "strike": strike,
                    "expired_instrument_key": f"{option_type}-{strike}",
                    "prior_5m_return_pct": ret,
                    "return_acceleration": ret + 6.0,
                    "prior_5m_volume_ratio": 2.0,
                    "mirror_return": 1.0,
                }
            )

    out = discovery.add_three_dimensional_features(pd.DataFrame(rows))
    target = out.loc[(out["option_type"].eq("CE")) & (out["strike"].eq(120))].iloc[0]

    assert target["strike_rank_pct"] == 0.5
    assert target["wing_edge_distance"] == 0.0
    assert target["local_median_return"] == -5.0
    assert target["local_breadth_positive"] == 0.0


def test_mechanism_masks_require_3d_local_and_mirror_context() -> None:
    frame = pd.DataFrame(
        [
            {
                "prior_5m_return_pct": -2.0,
                "previous_return": -8.0,
                "return_acceleration": 6.0,
                "prior_5m_volume_ratio": 3.0,
                "volume_acceleration": 2.0,
                "oi_change_ratio": 0.5,
                "mirror_return": 4.0,
                "option_asymmetry": -6.0,
                "local_median_return": -5.0,
                "local_median_acceleration": 6.0,
                "local_breadth_positive": 0.1,
                "local_return_dispersion": 0.2,
                "local_volume_ratio_mean": 3.0,
                "local_return_residual": 3.0,
                "local_median_repair": 2.0,
                "wing_edge_distance": 0.8,
                "surface_median_return": -4.0,
                "surface_median_acceleration": 4.0,
                "breadth_delta": 0.2,
                "directional_mass_shift": 2.0,
                "minute_of_day": 800,
                "days_to_expiry": 1,
            }
        ]
    )
    cut = {
        "ret10": -7.0,
        "ret20": -4.0,
        "ret30": -3.0,
        "ret70": 1.0,
        "prev10": -7.0,
        "acc65": 3.0,
        "acc75": 5.0,
        "vol65": 2.0,
        "vol75": 2.5,
        "vacc60": 1.0,
        "oi65": 0.2,
        "oi75": 0.4,
        "breadth_delta60": 0.1,
        "surface_acc60": 2.0,
        "local_ret25": -3.0,
        "local_ret35": -2.0,
        "local_acc65": 3.0,
        "local_acc75": 5.0,
        "local_breadth35": 0.3,
        "local_breadth60": 0.6,
        "local_disp35": 0.3,
        "local_vol70": 2.5,
        "local_repair65": 1.0,
        "resid30": -1.0,
        "resid70": 2.0,
        "mirror40": 0.0,
        "mirror70": 3.0,
        "asym25": -4.0,
        "asym70": 2.0,
        "edge35": 0.2,
        "edge70": 0.7,
        "mass_shift70": 1.0,
    }

    masks = discovery.mechanism_masks(frame, cut)

    assert bool(masks["local_cluster_washout_repair"].iloc[0])
    assert bool(masks["mirror_pin_reversal_3d"].iloc[0])
    assert bool(masks["late_session_3d_repair"].iloc[0])
    assert bool(masks["near_expiry_3d_repair"].iloc[0])


def test_oof_gate_rejects_top_winner_concentration() -> None:
    trades = pd.DataFrame(
        {
            "net_return_pct": [30.0] + [-0.2] * 120,
            "stress_return_pct": [29.0] + [-1.2] * 120,
            "session_id": [f"s{i:03d}" for i in range(121)],
            "timestamp": pd.date_range("2025-01-01", periods=121, freq="5min", tz="UTC"),
            "fold_id": [f"fold_{(i % 4) + 1}" for i in range(121)],
        }
    )

    metric = common.calculate_metrics(trades)

    assert metric.trades == 121
    assert not discovery.oof_gate(metric)
