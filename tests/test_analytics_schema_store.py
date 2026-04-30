from __future__ import annotations

import json
from pathlib import Path

from core.analytics.schema import (
    GateDecision,
    TradeIntentEvent,
    TradeOutcome,
    from_json,
    to_json,
    validate_trade_intent_event_payload,
    validate_trade_outcome_payload,
)
from core.analytics.store import (
    load_decision_telemetry_events,
    load_executable_review_queue_events,
    load_review_queue_events,
)


def test_schema_roundtrip_serialize_deserialize():
    gate = GateDecision(
        gate_name="spread_guard",
        passed=False,
        reason="spread_pct_high",
        metrics_snapshot={"spread_pct": 0.041},
    )
    event = TradeIntentEvent(
        trade_key="tk_1",
        event_id="evt_1",
        intent="rejected",
        ts_epoch_ms=1_700_000_000_000,
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=25000.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        reject_reason="spread_pct",
        gate_decisions=(gate,),
        metrics_snapshot={"quote_age_sec": 3.2},
    )
    payload = event.to_dict()
    ok, errors = validate_trade_intent_event_payload(payload)
    assert ok is True, errors
    encoded = to_json(payload)
    decoded = from_json(encoded)
    restored = TradeIntentEvent.from_dict(decoded)
    assert restored == event

    outcome = TradeOutcome(
        trade_key="tk_1",
        event_id="evt_out_1",
        outcome="hit_target",
        ts_epoch_ms=1_700_000_001_000,
        symbol="NIFTY",
        mfe_points=12.5,
        mae_points=-3.0,
        exec_feasible=True,
        exec_feasible_flags={"has_candle_data": True, "ambiguous_intrabar": False},
        source="unit_test",
        reject_reason="spread_pct",
        reject_reasons=("spread_pct",),
        primary_reject_reason="spread_pct",
    )
    out_payload = outcome.to_dict()
    ok2, errors2 = validate_trade_outcome_payload(out_payload)
    assert ok2 is True, errors2
    out_restored = TradeOutcome.from_dict(from_json(to_json(out_payload)))
    assert out_restored == outcome


def test_load_decision_telemetry_skips_malformed_jsonl(tmp_path):
    telemetry_path = tmp_path / "decision_telemetry.jsonl"
    lines = [
        '{"symbol":"NIFTY","ts_epoch":1700000000,"side":"BUY","strike":25000,"option_type":"CE","reason_code":"spread_pct"}',
        '{"symbol":"NIFTY","ts_epoch":1700000005,"side":"BUY",bad_json_here}',
        '{"symbol":"BANKNIFTY","ts_epoch":1700000010,"side":"SELL","strike":52000,"option_type":"PE","execution_allowed":1}',
    ]
    telemetry_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    events = load_decision_telemetry_events(paths=[telemetry_path])
    assert len(events) == 2
    assert events[0].symbol == "NIFTY"
    assert events[0].intent == "rejected"
    assert events[1].symbol == "BANKNIFTY"
    assert events[1].intent in {"accepted", "advisory"}


def test_load_review_queue_skips_malformed_json_file(tmp_path):
    queue_path = tmp_path / "review_queue.json"
    queue_path.write_text('[{"symbol":"NIFTY","timestamp_epoch_ms":1700000000000}\n', encoding="utf-8")

    rows = load_review_queue_events(paths=[queue_path])
    assert rows == []

    valid_path = tmp_path / "review_queue_valid.json"
    valid_payload = [
        {
            "symbol": "NIFTY",
            "timestamp_epoch_ms": 1_700_000_000_000,
            "side": "BUY",
            "strike": 25000,
            "option_type": "CE",
            "status": "PLANNING",
            "permission": "ADVISORY_ONLY",
            "reject_reason": "stale_quote",
            "expiry_date": "2026-03-05",
            "trade_key": "tk_review_1",
        },
        "bad_row_type",
    ]
    valid_path.write_text(json.dumps(valid_payload), encoding="utf-8")
    rows2 = load_review_queue_events(paths=[valid_path])
    assert len(rows2) == 1
    assert rows2[0].intent == "rejected"
    assert rows2[0].reject_reason == "stale_quote"


def test_load_review_queue_preserves_predicted_confidence_metrics(tmp_path):
    queue_path = tmp_path / "review_queue_confidence.json"
    payload = [
        {
            "symbol": "NIFTY",
            "timestamp_epoch_ms": 1_700_000_000_000,
            "side": "BUY",
            "strike": 25000,
            "option_type": "CE",
            "status": "PLANNING",
            "permission": "ADVISORY_ONLY",
            "expiry_date": "2026-03-05",
            "trade_key": "tk_review_conf_1",
            "confidence_raw_canonical": 0.63,
            "confidence_after_soft_veto": 0.58,
            "gating_final_confidence": 0.56,
        }
    ]
    queue_path.write_text(json.dumps(payload), encoding="utf-8")

    rows = load_review_queue_events(paths=[queue_path])

    assert len(rows) == 1
    metrics = rows[0].metrics_snapshot
    assert metrics["predicted_confidence"] == 0.63
    assert metrics["predicted_confidence_source"] == "confidence_raw_canonical"
    assert metrics["predicted_confidence_final"] == 0.58
    assert metrics["predicted_confidence_final_source"] == "confidence_after_soft_veto"


def test_load_executable_review_queue_events_marks_executable_rows_accepted(tmp_path):
    queue_path = tmp_path / "review_queue.json"
    payload = [
        {
            "trade_key": "SENSEX|2026-04-23|77700|PE|BUY|ENSEMBLE_OPT",
            "symbol": "SENSEX",
            "timestamp_epoch_ms": 1_771_056_600_000,
            "candidate_class": "EXECUTABLE",
            "final_action": "EXECUTE",
            "execution_allowed": False,
            "status": "BLOCKED_APPROVAL",
            "permission": "EXECUTE",
            "candidate_status": "advisory_only",
            "entry_price": 100.0,
            "target_price": 104.0,
            "stop_price": 97.0,
            "side": "BUY",
            "option_type": "PE",
            "expiry_date": "2026-04-23",
            "strike": 77700.0,
            "quote_validation_status": "STALE_OPTION_LTP",
            "primary_blocker": "missing_execution_entry",
            "selection_reason": "not_execution_eligible",
            "current_ltp": 100.0,
        },
        {
            "trade_key": "SENSEX|2026-04-23|77800|PE|BUY|ENSEMBLE_OPT",
            "symbol": "SENSEX",
            "timestamp_epoch_ms": 1_771_056_600_000,
            "candidate_class": "ADVISORY_ONLY",
            "final_action": "QUEUE_ONLY",
            "execution_allowed": False,
            "status": "BLOCKED_APPROVAL",
            "permission": "QUEUE_ONLY",
            "candidate_status": "queue_only",
            "entry_price": 90.0,
            "target_price": 94.0,
            "stop_price": 87.0,
            "side": "BUY",
            "option_type": "PE",
            "expiry_date": "2026-04-23",
            "strike": 77800.0,
        },
    ]
    queue_path.write_text(json.dumps(payload), encoding="utf-8")

    events = load_executable_review_queue_events(paths=[queue_path])
    assert len(events) == 1
    assert events[0].intent == "accepted"
    assert events[0].symbol == "SENSEX"
    assert events[0].metrics_snapshot["candidate_class"] == "EXECUTABLE"
    assert events[0].metrics_snapshot["execution_allowed"] is False
