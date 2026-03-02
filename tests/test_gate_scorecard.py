from __future__ import annotations

import json

from core.analytics.gate_scorecard import build_gate_scorecard
from core.analytics.schema import GateDecision, TradeIntentEvent, TradeOutcome


def _event(
    *,
    event_id: str,
    trade_key: str,
    ts_ms: int,
    intent: str,
    reject_reason: str | None,
    gate_name: str,
    gate_passed: bool,
) -> TradeIntentEvent:
    return TradeIntentEvent(
        trade_key=trade_key,
        event_id=event_id,
        intent=intent,
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=25000.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        reject_reason=reject_reason,
        gate_decisions=(
            GateDecision(gate_name=gate_name, passed=gate_passed, reason=reject_reason if not gate_passed else None),
        ),
        metrics_snapshot={},
    )


def _outcome(*, event_ref_id: str, trade_key: str, ts_ms: int, outcome: str) -> dict:
    row = TradeOutcome(
        trade_key=trade_key,
        event_id=f"out_{event_ref_id}",
        outcome=outcome,
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        mfe_points=10.0 if outcome == "hit_target" else 2.0,
        mae_points=-5.0 if outcome == "hit_sl" else -1.0,
        exec_feasible=True,
        exec_feasible_flags={"has_candle_data": True},
        source="unit_test",
        reject_reason=None,
    )
    return {"event_ref_id": event_ref_id, "trade_outcome": row.to_dict()}


def test_gate_scorecard_counts_and_net_edge(tmp_path):
    # 2026-02-28 in IST
    base_ts = 1_772_272_400_000
    events = [
        _event(
            event_id="rej_win",
            trade_key="tk_rej_win",
            ts_ms=base_ts,
            intent="rejected",
            reject_reason="spread_high",
            gate_name="spread_guard",
            gate_passed=False,
        ),
        _event(
            event_id="rej_lose",
            trade_key="tk_rej_lose",
            ts_ms=base_ts + 10_000,
            intent="rejected",
            reject_reason="spread_high",
            gate_name="spread_guard",
            gate_passed=False,
        ),
        _event(
            event_id="rej_neutral",
            trade_key="tk_rej_neutral",
            ts_ms=base_ts + 20_000,
            intent="rejected",
            reject_reason="quote_stale",
            gate_name="quote_guard",
            gate_passed=False,
        ),
        _event(
            event_id="acc_lose",
            trade_key="tk_acc_lose",
            ts_ms=base_ts + 30_000,
            intent="accepted",
            reject_reason=None,
            gate_name="spread_guard",
            gate_passed=True,
        ),
        _event(
            event_id="acc_win",
            trade_key="tk_acc_win",
            ts_ms=base_ts + 40_000,
            intent="accepted",
            reject_reason=None,
            gate_name="spread_guard",
            gate_passed=True,
        ),
    ]

    outcomes = [
        _outcome(event_ref_id="rej_win", trade_key="tk_rej_win", ts_ms=base_ts + 60_000, outcome="hit_target"),
        _outcome(event_ref_id="rej_lose", trade_key="tk_rej_lose", ts_ms=base_ts + 70_000, outcome="hit_sl"),
        _outcome(event_ref_id="rej_neutral", trade_key="tk_rej_neutral", ts_ms=base_ts + 80_000, outcome="no_hit"),
        _outcome(event_ref_id="acc_lose", trade_key="tk_acc_lose", ts_ms=base_ts + 90_000, outcome="hit_sl"),
        _outcome(event_ref_id="acc_win", trade_key="tk_acc_win", ts_ms=base_ts + 100_000, outcome="hit_target"),
    ]

    out_path = tmp_path / "runtime" / "analytics" / "reports" / "2026-02-28" / "gate_scorecard.json"
    payload = build_gate_scorecard(
        "2026-02-28",
        events=events,
        outcomes=outcomes,
        output_path=out_path,
    )

    by_key = {
        (row["gate_name"], row["reject_reason"]): row
        for row in payload["by_gate_reject_reason"]
    }
    spread = by_key[("spread_guard", "spread_high")]
    assert spread["blocked_count"] == 2
    assert spread["blocked_would_win"] == 1
    assert spread["blocked_would_lose"] == 1
    assert spread["blocked_neutral"] == 0
    assert spread["net_edge_score"] == 0.0

    quote = by_key[("quote_guard", "quote_stale")]
    assert quote["blocked_count"] == 1
    assert quote["blocked_would_win"] == 0
    assert quote["blocked_would_lose"] == 0
    assert quote["blocked_neutral"] == 1
    assert quote["net_edge_score"] == 0.0

    gate_metrics = {row["gate_name"]: row for row in payload["gate_precision_recall"]}
    spread_metrics = gate_metrics["spread_guard"]
    assert spread_metrics["blocked_count"] == 2
    assert spread_metrics["pass_count"] == 2
    assert spread_metrics["block_precision"] == 0.5
    assert spread_metrics["block_recall"] == 0.5
    assert spread_metrics["allow_precision"] == 0.5
    assert spread_metrics["allow_recall"] == 0.5

    quote_metrics = gate_metrics["quote_guard"]
    assert quote_metrics["blocked_count"] == 1
    assert quote_metrics["pass_count"] == 0
    assert quote_metrics["block_precision"] == 0.0
    assert quote_metrics["block_recall"] is None

    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["total_events"] == 5
    assert written["total_rejected_events"] == 3
