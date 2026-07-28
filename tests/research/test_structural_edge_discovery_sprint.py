from __future__ import annotations

import pandas as pd

from research.structural_edge_discovery_sprint.sprint import apply_hypothesis, iter_hypotheses, metrics


def test_generates_causal_buy_only_hypotheses() -> None:
    frame = pd.DataFrame(
        {
            "event_type": ["vwap_reclaim"] * 20,
            "instrument": ["NIFTY"] * 20,
            "direction": ["UP"] * 20,
            "minute_index": range(20),
            "gap_pct": [0.0] * 20,
            "net_points": [1.0] * 20,
            "gross_points": [2.5] * 20,
            "mfe_points": [35.0] * 20,
            "mae_points": [5.0] * 20,
            "session_date": ["2024-06-01"] * 20,
            "entry_timestamp": ["2024-06-01T09:30:00+05:30"] * 20,
        }
    )
    hyps = iter_hypotheses(frame, 50)
    assert len(hyps) == 50
    assert all(h["action"] in {"BUY_CE", "BUY_PE"} for h in hyps)
    assert all(h["entry"] == "next_completed_bar_open" for h in hyps)
    assert all(h["allowed_for_live_execution"] is False for h in hyps)


def test_apply_hypothesis_filters_completed_feature_rule() -> None:
    frame = pd.DataFrame(
        {
            "event_type": ["vwap_reclaim", "vwap_reclaim"],
            "instrument": ["NIFTY", "NIFTY"],
            "direction": ["UP", "UP"],
            "minute_index": [10, 40],
            "net_points": [1.0, 2.0],
        }
    )
    hyp = {
        "event_type": "vwap_reclaim",
        "instrument": "NIFTY",
        "direction": "UP",
        "rules": [{"feature": "minute_index", "operator": ">=", "threshold": 20}],
    }
    out = apply_hypothesis(frame, hyp)
    assert len(out) == 1
    assert out.iloc[0]["minute_index"] == 40


def test_metrics_flags_concentration_inputs() -> None:
    frame = pd.DataFrame(
        {
            "net_points": [100.0, 1.0, 1.0, 1.0, 1.0],
            "gross_points": [101.5, 2.5, 2.5, 2.5, 2.5],
            "net_points_2x_cost": [98.5, -0.5, -0.5, -0.5, -0.5],
            "mfe_points": [40.0] * 5,
            "mae_points": [5.0] * 5,
            "month": ["2024-06"] * 5,
            "weekday": ["Monday"] * 5,
        }
    )
    result = metrics(frame)
    assert result["sample"] == 5
    assert result["top5_contribution"] == 1.0
