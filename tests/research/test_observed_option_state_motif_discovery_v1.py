from __future__ import annotations

import pandas as pd

from scripts import run_observed_option_state_motif_discovery_v1 as subject


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "option_type": ["CE", "PE", "CE"],
            "entry_price_next_open": [55.0, 110.0, 170.0],
            "days_to_expiry": [0, 2, 5],
            "minute_of_day": [610, 720, 820],
            "prior_5m_return_pct": [-1.0, 0.0, 1.0],
            "return_acceleration": [-0.5, 0.0, 0.8],
            "prior_5m_volume_ratio": [0.8, 1.5, 3.0],
            "oi_change_ratio": [0.0, 0.1, 0.4],
            "mirror_return": [0.5, 0.0, -0.3],
            "breadth_positive": [0.25, 0.50, 0.80],
            "surface_return_dispersion": [0.10, 0.20, 0.50],
            "prior_10m_range_pct": [0.2, 0.6, 1.1],
            "surface_median_return": [-0.2, 0.0, 0.3],
            "option_asymmetry": [-0.5, 0.0, 0.6],
        }
    )


def test_motif_labels_are_pre_outcome_and_deterministic() -> None:
    frame = _frame()
    cuts = subject.observation_cuts(frame)
    first = subject.motif_labels(frame, cuts)
    second = subject.motif_labels(frame, cuts)
    assert first.tolist() == second.tolist()
    assert all("CE" in label or "PE" in label for label in first)
    assert all("prem_" in label for label in first)
    assert all("ret_" in label for label in first)


def test_research_split_keeps_observation_before_validation() -> None:
    sessions = [f"2026-01-{day:02d}" for day in range(1, 121)]
    observation, folds = subject.split_research_sessions(sessions)
    assert observation == sessions[:60]
    assert [item for fold in folds for item in fold] == sessions[60:]
    assert len(folds) == 3


def test_constants_remain_research_only() -> None:
    assert subject.NORMAL_COST_PCT == 0.10
    assert subject.STRESS_COST_PCT == 1.00
    assert subject.MAX_FROZEN_MOTIFS == 8
