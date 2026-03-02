from __future__ import annotations

import json

from core.analytics.feed_context import build_feed_context
from core.analytics.schema import (
    TradeIntentEvent,
    validate_trade_intent_event_payload,
)
from core.analytics.store import load_decision_telemetry_events
from core.feed.runtime import build_default_feed_health, classify_group


def test_enrichment_adds_feed_fields_for_known_group():
    now_ref = {"now": 1000.0}

    def _now():
        return float(now_ref["now"])

    machine, metrics_map = build_default_feed_health(now_fn=_now)
    group = classify_group("NIFTY")
    metrics = metrics_map[group]
    metrics.observe_ws(ts=now_ref["now"])
    metrics.observe_tick(token=101, ts=now_ref["now"])
    metrics.observe_quote(
        token=101,
        bid=100.0,
        ask=100.2,
        ltp=100.1,
        ts=now_ref["now"],
        depth_ok=True,
    )
    machine.update_group(group, metrics.snapshot())

    ctx = build_feed_context("NIFTY", machine=machine, metrics_map=metrics_map)
    assert ctx["feed_group"] == group
    assert ctx["feed_state"] in {"OK", "DEGRADED", "DOWN", "UNKNOWN"}
    metrics_payload = dict(ctx["feed_metrics"] or {})
    for key in (
        "tick_age_p50",
        "tick_age_p95",
        "ws_age",
        "spread_p95",
        "depth_missing_pct",
        "tokens_recent_pct",
        "flap_locked",
    ):
        assert key in metrics_payload


def test_enrichment_unknown_symbol():
    machine, metrics_map = build_default_feed_health(now_fn=lambda: 1000.0)
    ctx = build_feed_context("WEIRD_SYMBOL_123", machine=machine, metrics_map=metrics_map)
    assert ctx["feed_state"] == "UNKNOWN"
    assert "UNKNOWN" in str(ctx["feed_group"])
    metrics_payload = dict(ctx["feed_metrics"] or {})
    assert metrics_payload.get("tick_age_p50") is None
    assert metrics_payload.get("ws_age") is None


def test_schema_validation_accepts_feed_fields():
    payload = {
        "trade_key": "NIFTY|2026-03-05|22500|CE|BUY",
        "event_id": "evt_feed_ctx_1",
        "intent": "rejected",
        "ts_epoch_ms": 1740723900000,
        "symbol": "NIFTY",
        "source": "unit_test",
        "reject_reason": "feed_state_DOWN",
        "gate_decisions": [{"gate_name": "exec_guard", "passed": False, "reason": "feed_state_DOWN"}],
        "metrics_snapshot": {},
        "feed_group": "INDEX:NIFTY",
        "feed_state": "DOWN",
        "feed_metrics": {
            "tick_age_p50": 4.2,
            "tick_age_p95": 4.2,
            "ws_age": 4.2,
            "spread_p95": 0.02,
            "depth_missing_pct": 1.0,
            "tokens_recent_pct": 0.0,
            "flap_locked": None,
        },
    }
    event = TradeIntentEvent.from_dict(payload)
    ok, errors = validate_trade_intent_event_payload(event.to_dict())
    assert ok is True, errors
    assert event.feed_state == "DOWN"
    assert event.feed_group == "INDEX:NIFTY"


def test_event_id_stability_not_affected_by_feed_metrics():
    base_payload = {
        "trade_key": "NIFTY|2026-03-05|22500|CE|BUY",
        "intent": "rejected",
        "ts_epoch_ms": 1740723900000,
        "symbol": "NIFTY",
        "source": "unit_test",
        "reject_reason": "spread_wide",
        "gate_decisions": [],
        "metrics_snapshot": {},
        "feed_group": "OPT:NIFTY",
        "feed_state": "DEGRADED",
    }
    p1 = dict(base_payload)
    p1["feed_metrics"] = {"tick_age_p50": 1.0, "spread_p95": 0.01}
    p2 = dict(base_payload)
    p2["feed_metrics"] = {"tick_age_p50": 9.0, "spread_p95": 0.09}
    e1 = TradeIntentEvent.from_dict(p1)
    e2 = TradeIntentEvent.from_dict(p2)
    assert e1.event_id == e2.event_id


def test_reject_event_contains_feed_state_when_feed_gate_blocks(tmp_path):
    path = tmp_path / "decision_events.jsonl"
    row = {
        "symbol": "NIFTY",
        "ts_epoch": 1_740_723_900,
        "side": "BUY",
        "strike": 22500,
        "option_type": "CE",
        "execution_allowed": 0,
        "reason_code": "feed_state_DOWN",
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    events = load_decision_telemetry_events(paths=[path])
    assert len(events) == 1
    event = events[0]
    assert event.intent == "rejected"
    assert event.feed_state == "DOWN"
    assert isinstance(event.feed_metrics, dict)
    assert event.feed_group == "INDEX:NIFTY"
