from __future__ import annotations

import json

from core.analytics.missed_opportunity import analyze_missed_opportunity
from core.analytics.schema import GateDecision, TradeIntentEvent, TradeOutcome


def _event(*, event_id: str, trade_key: str, ts_ms: int, reason: str, gate: str, target_points: float) -> TradeIntentEvent:
    return TradeIntentEvent(
        trade_key=trade_key,
        event_id=event_id,
        intent="rejected",
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=25000.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        reject_reason=reason,
        gate_decisions=(GateDecision(gate_name=gate, passed=False, reason=reason),),
        metrics_snapshot={"target_points": target_points},
    )


def _outcome(
    *,
    event_id: str,
    trade_key: str,
    ts_ms: int,
    outcome: str,
    mfe: float,
    mae: float,
    target_points: float = 10.0,
) -> dict:
    row = TradeOutcome(
        trade_key=trade_key,
        event_id=f"out_{event_id}",
        outcome=outcome,  # hit_target / hit_sl / no_hit
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        mfe_points=mfe,
        mae_points=mae,
        exec_feasible=True,
        exec_feasible_flags={"has_candle_data": True},
        source="unit_test",
        reject_reason="unit",
    )
    return {
        "event_ref_id": event_id,
        "target_points": float(target_points),
        "trade_outcome": row.to_dict(),
    }


def test_missed_opportunity_labels_and_aggregates(tmp_path):
    events = [
        _event(
            event_id="evt_clear",
            trade_key="tk_clear",
            ts_ms=1_772_272_400_000,  # 2026-03-03 IST day
            reason="spread_pct",
            gate="spread_guard",
            target_points=10.0,
        ),
        _event(
            event_id="evt_partial",
            trade_key="tk_partial",
            ts_ms=1_772_272_430_000,
            reason="quote_stale",
            gate="quote_guard",
            target_points=20.0,
        ),
        _event(
            event_id="evt_none",
            trade_key="tk_none",
            ts_ms=1_772_272_460_000,
            reason="quote_stale",
            gate="quote_guard",
            target_points=20.0,
        ),
    ]
    outcomes = [
        _outcome(
            event_id="evt_clear",
            trade_key="tk_clear",
            ts_ms=1_772_272_500_000,
            outcome="hit_target",
            mfe=12.0,
            mae=-2.0,
        ),
        _outcome(
            event_id="evt_partial",
            trade_key="tk_partial",
            ts_ms=1_772_272_560_000,
            outcome="no_hit",
            mfe=11.0,
            mae=-6.0,
            target_points=20.0,
        ),
        _outcome(
            event_id="evt_none",
            trade_key="tk_none",
            ts_ms=1_772_272_620_000,
            outcome="no_hit",
            mfe=5.0,
            mae=-8.0,
            target_points=20.0,
        ),
    ]

    out_path = tmp_path / "runtime" / "analytics" / "reports" / "2026-02-28" / "missed_opportunity.json"
    payload = analyze_missed_opportunity(
        "2026-02-28",
        rejected_events=events,
        outcomes=outcomes,
        output_path=out_path,
    )

    assert payload["total_rejected"] == 3
    assert payload["matched_outcomes"] == 3
    assert payload["labels"]["CLEAR_MISS"] == 1
    assert payload["labels"]["PARTIAL_EDGE"] == 1
    assert payload["labels"]["NO_EDGE"] == 1

    labels_by_event = {row["event_id"]: row["label"] for row in payload["rows"]}
    assert labels_by_event["evt_clear"] == "CLEAR_MISS"
    assert labels_by_event["evt_partial"] == "PARTIAL_EDGE"
    assert labels_by_event["evt_none"] == "NO_EDGE"

    agg = {
        (row["reject_reason"], row["gate_name"]): row
        for row in payload["aggregates"]
    }
    spread_bucket = agg[("spread_pct", "spread_guard")]
    assert spread_bucket["count"] == 1
    assert spread_bucket["clear_miss_rate"] == 1.0
    assert spread_bucket["avg_mfe"] == 12.0
    assert spread_bucket["avg_mae"] == -2.0

    quote_bucket = agg[("quote_stale", "quote_guard")]
    assert quote_bucket["count"] == 2
    assert quote_bucket["clear_miss_rate"] == 0.0
    assert quote_bucket["avg_mfe"] == 8.0
    assert quote_bucket["avg_mae"] == -7.0

    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["labels"] == payload["labels"]


def test_missed_opportunity_matches_by_trade_key_without_event_ref(tmp_path):
    event = _event(
        event_id="evt_trade_key_match",
        trade_key="tk_match",
        ts_ms=1_772_272_700_000,
        reason="premium_band",
        gate="premium_guard",
        target_points=10.0,
    )
    outcome = TradeOutcome(
        trade_key="tk_match",
        event_id="out_trade_key_match",
        outcome="hit_target",
        ts_epoch_ms=1_772_272_760_000,
        symbol="NIFTY",
        mfe_points=15.0,
        mae_points=-1.5,
        exec_feasible=True,
        exec_feasible_flags={"has_candle_data": True},
        source="unit_test",
        reject_reason="premium_band",
    )

    out_path = tmp_path / "runtime" / "analytics" / "reports" / "2026-02-28" / "missed_opportunity.json"
    payload = analyze_missed_opportunity(
        "2026-02-28",
        rejected_events=[event],
        outcomes=[{"trade_outcome": outcome.to_dict(), "target_points": 10.0}],
        output_path=out_path,
    )

    assert payload["matched_outcomes"] == 1
    assert payload["rows"][0]["label"] == "CLEAR_MISS"
    assert payload["rows"][0]["gate_name"] == "premium_guard"
