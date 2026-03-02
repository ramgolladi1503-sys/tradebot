from __future__ import annotations

from core.analytics.schema import GateDecision, TradeIntentEvent, TradeOutcome


def test_schema_dataclasses_roundtrip():
    decision = GateDecision(gate_name="spread_guard", passed=False, reason="spread_wide")
    event = TradeIntentEvent(
        trade_key="NIFTY|2026-03-05|22500|CE|BUY",
        event_id="evt_schema_1",
        intent="rejected",
        ts_epoch_ms=1740723900000,
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=22500.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        reject_reason="spread_wide",
        gate_decisions=(decision,),
        metrics_snapshot={"quote_age_sec": 1.2, "spread_pct": 0.02},
    )
    decoded_event = TradeIntentEvent.from_dict(event.to_dict())
    assert decoded_event.trade_key == event.trade_key
    assert decoded_event.event_id == event.event_id
    assert decoded_event.intent == "rejected"
    assert decoded_event.gate_decisions[0].gate_name == "spread_guard"

    outcome = TradeOutcome(
        trade_key=event.trade_key,
        event_id="out_schema_1",
        outcome="hit_sl",
        ts_epoch_ms=1740723960000,
        symbol="NIFTY",
        mfe_points=2.0,
        mae_points=-6.0,
        exec_feasible=True,
        exec_feasible_flags={"has_candle_data": True},
        source="unit_test",
        reject_reason="spread_wide",
    )
    decoded_outcome = TradeOutcome.from_dict(outcome.to_dict())
    assert decoded_outcome.trade_key == outcome.trade_key
    assert decoded_outcome.outcome == "hit_sl"
    assert decoded_outcome.exec_feasible_flags["has_candle_data"] is True

