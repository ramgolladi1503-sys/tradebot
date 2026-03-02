from __future__ import annotations

from core.analytics.missed_opportunity import classify_missed_label
from core.analytics.schema import TradeOutcome


def test_classify_missed_label_cases():
    outcome_hit = TradeOutcome(
        trade_key="NIFTY|2026-03-05|22500|CE|BUY|unit",
        event_id="evt_miss_1",
        outcome="hit_target",
        ts_epoch_ms=1772164800000,
        symbol="NIFTY",
        mfe_points=8.0,
        mae_points=1.0,
        exec_feasible=True,
        source="unit",
    )
    outcome_partial = TradeOutcome(
        trade_key="NIFTY|2026-03-05|22500|CE|BUY|unit",
        event_id="evt_miss_2",
        outcome="no_hit",
        ts_epoch_ms=1772164860000,
        symbol="NIFTY",
        mfe_points=3.0,
        mae_points=2.0,
        exec_feasible=True,
        source="unit",
    )

    assert classify_missed_label(outcome_hit, target_points=5.0) == "CLEAR_MISS"
    assert classify_missed_label(outcome_partial, target_points=5.0) == "PARTIAL_EDGE"
    assert classify_missed_label(None, target_points=5.0) == "NO_EDGE"
