from __future__ import annotations

import pytest

from core.analytics.candidate_ml_v2.certification import _fold_metrics, _score_frame
from core.analytics.candidate_ml_v2.dataset import build_candidate_row


@pytest.mark.parametrize("status", ["UNASSESSED", "ASSESSED_INFEASIBLE"])
def test_candidate_ml_does_not_label_nonfeasible_observed_path_as_execution_result(status):
    row = build_candidate_row(
        {
            "event_id": "evt-1",
            "trade_key": "NIFTY|2026-10-29|25000|CE|BUY",
            "symbol": "NIFTY",
            "option_type": "CE",
            "ts_epoch_ms": 1791776700000,
            "strategy_id": "TEST",
            "metrics_snapshot": {},
        },
        {
            "event_ref_id": "evt-1",
            "resolution_ts_epoch_ms": 1791776820000,
            "trade_outcome": {
                "outcome": "hit_target",
                "exec_feasible": True,
                "exec_feasible_flags": {
                    "outcome_path_observed": True,
                    "execution_feasibility_status": status,
                },
            },
        },
    )

    assert row["execution_feasibility_status"] == status
    assert row["exec_feasible"] == 0
    assert row["target"] == 0
    assert row["stop_hit"] == 0
    assert row["future_net_r"] is None


def test_certification_quarantines_unassessed_rows_without_predicting_or_assigning_r():
    import pandas as pd

    class MustNotPredict:
        def predict(self, _payload):
            raise AssertionError("unassessed labels must be excluded before model scoring")

    frame = pd.DataFrame(
        [{
            "event_id": "evt-1",
            "session_date": "2026-10-12",
            "target": 0,
            "future_net_r": None,
            "execution_feasibility_status": "UNASSESSED",
        }]
    )
    scored = _score_frame(MustNotPredict(), frame)

    assert scored.loc[0, "ml_status"] == "LABEL_UNAVAILABLE"
    assert scored.loc[0, "selected"] is False or not bool(scored.loc[0, "selected"])
    assert pd.isna(scored.loc[0, "future_net_r"])
    metrics = _fold_metrics(scored)
    assert metrics["baseline_mean_future_net_r"] is None
    assert metrics["probability_rows"] == 0
