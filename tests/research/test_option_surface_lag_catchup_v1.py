from __future__ import annotations

import pandas as pd

from scripts import run_inventory_absorption_transition_v1 as common
from scripts import run_option_surface_lag_catchup_v1 as campaign


def test_surface_residual_is_contract_minus_surface() -> None:
    frame = pd.DataFrame(
        {
            "prior_5m_return_pct": [1.0, 3.0],
            "surface_median_return": [2.0, 2.0],
        }
    )
    residual = frame["prior_5m_return_pct"] - frame["surface_median_return"]
    assert residual.tolist() == [-1.0, 1.0]


def test_onset_emits_only_state_transition() -> None:
    frame = pd.DataFrame({"expired_instrument_key": ["A"] * 4})
    mask = pd.Series([False, True, True, False])
    assert campaign.onset(frame, mask).tolist() == [False, True, False, False]


def test_oof_gate_rejects_low_occurrence() -> None:
    metric = common.Metrics(
        99, 80, 1.5, 1.0, 0.4, 0.6, 99.0, 1.3, 1.3, 1.2,
        0.1, 2.0, 4, 4, 2, 2, 0.1, 0.1,
    )
    assert campaign.oof_gate(metric) is False


def test_control_gate_requires_lag_specificity() -> None:
    primary = common.Metrics(40, 30, 1.6, 1.2, 0.4, 0.6, 48.0, 1.4, 1.4, 1.3, 0.1, 2.0, 0, 0, 2, 2, 0.1, 0.1)
    mirror = common.Metrics(30, 25, 0.8, -0.5, -0.4, 0.4, -15.0, 0.7, 0.7, 0.6, -1.0, 0.1, 0, 0, 0, 0, 0.1, 0.1)
    delayed = common.Metrics(35, 28, 1.2, 0.5, 0.1, 0.5, 17.5, 1.0, 1.0, 0.9, -0.2, 1.0, 0, 0, 0, 0, 0.1, 0.1)
    leader = common.Metrics(38, 29, 1.1, 0.2, 0.0, 0.5, 7.6, 0.9, 0.9, 0.8, -0.3, 0.8, 0, 0, 0, 0, 0.1, 0.1)
    assert campaign.control_gate(primary, mirror, delayed, leader) is True
