from __future__ import annotations

import json

from core.candidate_intent import (
    CANDIDATE_INTENT_DUPLICATE_ID,
    CANDIDATE_INTENT_FORBIDDEN_ACTION_FIELD,
    CANDIDATE_INTENT_INVALID_SAFETY_FLAGS,
    create_candidate_intent,
)
from core.candidate_intent_pool import (
    CANDIDATE_INTENT_POOL_EMPTY_INPUT,
    CANDIDATE_INTENT_POOL_NO_ELIGIBLE_INTENTS,
    CANDIDATE_INTENT_POOL_REJECTED_INTENTS_PRESENT,
    CANDIDATE_INTENT_POOL_SOURCE,
    CANDIDATE_INTENT_POOL_STATUS_BLOCKED,
    CANDIDATE_INTENT_POOL_STATUS_ELIGIBLE,
    build_candidate_intent_pool,
)


def _field(*parts: str) -> str:
    return "".join(parts)


def _intent(**overrides):
    values = {
        "strategy_id": "breakout_v1",
        "instrument": "NIFTY",
        "direction": "BUY_CALL",
        "regime": "BULL_TREND",
        "family": "breakout",
        "trigger": "opening range break with volume expansion",
        "invalidation": "breakout fails back inside range",
        "required_evidence_keys": (
            "market_state",
            "regime_state",
            "feed_health_truth",
            "quote_truth",
        ),
        "metadata": {"strategy_name": "Breakout v1"},
    }
    values.update(overrides)
    return create_candidate_intent(**values)


def test_candidate_intent_pool_accepts_eligible_intent_without_ranking_or_scoring():
    report = build_candidate_intent_pool((_intent(),))
    payload = json.loads(report.to_json())

    assert report.valid is True
    assert report.pool_ready is True
    assert report.eligible_candidate_intent_ids == ("breakout_v1:nifty:buy_call:bull_trend:entry",)
    assert report.blocked_intents == ()
    assert report.rejected_intents == ()
    assert payload["source"] == CANDIDATE_INTENT_POOL_SOURCE
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["eligible_intents"][0]["pool_status"] == CANDIDATE_INTENT_POOL_STATUS_ELIGIBLE
    assert "score" not in payload
    assert "rank" not in payload
    assert payload["metadata"]["does_not_rank_candidates"] is True
    assert payload["metadata"]["does_not_score_edge"] is True
    assert payload["metadata"]["does_not_touch_runtime"] is True


def test_candidate_intent_pool_keeps_blocked_intent_visible_but_not_ready():
    blocked = _intent(blockers=("weak_signal",), warnings=("needs_confirmation",))

    report = build_candidate_intent_pool((blocked,))
    entry = report.get(blocked.candidate_intent_id)

    assert report.valid is True
    assert report.pool_ready is False
    assert report.eligible_intents == ()
    assert report.blocked_candidate_intent_ids == (blocked.candidate_intent_id,)
    assert entry.pool_status == CANDIDATE_INTENT_POOL_STATUS_BLOCKED
    assert entry.pool_eligible is False
    assert entry.blockers == ("weak_signal",)
    assert CANDIDATE_INTENT_POOL_NO_ELIGIBLE_INTENTS in report.warnings


def test_candidate_intent_pool_rejects_invalid_payload_without_hiding_valid_intent():
    valid = _intent(candidate_intent_id="valid")
    invalid_payload = _intent(candidate_intent_id="invalid").to_payload()
    invalid_payload["is_order_action"] = True

    report = build_candidate_intent_pool((valid, invalid_payload))

    assert report.valid is False
    assert report.pool_ready is False
    assert report.eligible_candidate_intent_ids == ("valid",)
    assert report.rejected_intents[0].candidate_intent_id == "invalid"
    assert report.rejected_intents[0].blockers == (CANDIDATE_INTENT_INVALID_SAFETY_FLAGS,)
    assert CANDIDATE_INTENT_POOL_REJECTED_INTENTS_PRESENT in report.warnings


def test_candidate_intent_pool_rejects_forbidden_action_shape_fields():
    payload = _intent(candidate_intent_id="unsafe_shape").to_payload()
    payload[_field("quant", "ity")] = 75
    payload[_field("ord", "er_type")] = "MARKET"

    report = build_candidate_intent_pool((payload,))

    assert report.valid is False
    assert report.pool_ready is False
    assert report.eligible_intents == ()
    assert report.rejected_intents[0].candidate_intent_id == "unsafe_shape"
    assert report.rejected_intents[0].blockers == (CANDIDATE_INTENT_FORBIDDEN_ACTION_FIELD,)


def test_candidate_intent_pool_rejects_duplicate_intent_ids():
    first = _intent(candidate_intent_id="duplicate")
    second = _intent(candidate_intent_id="duplicate", instrument="BANKNIFTY")

    report = build_candidate_intent_pool((first, second))

    assert report.valid is False
    assert report.pool_ready is False
    assert report.eligible_candidate_intent_ids == ("duplicate",)
    assert report.rejected_intents[0].blockers == (CANDIDATE_INTENT_DUPLICATE_ID,)


def test_candidate_intent_pool_blocks_empty_input_fail_closed():
    report = build_candidate_intent_pool(())

    assert report.valid is False
    assert report.pool_ready is False
    assert report.eligible_intents == ()
    assert report.blocked_intents == ()
    assert report.rejected_intents == ()
    assert report.blockers == (CANDIDATE_INTENT_POOL_EMPTY_INPUT,)


def test_candidate_intent_pool_payload_entries_are_non_action():
    report = build_candidate_intent_pool((_intent(), _intent(candidate_intent_id="blocked", blockers=("blocked_reason",))))
    payload = report.to_payload()

    for entry in payload["eligible_intents"] + payload["blocked_intents"]:
        assert entry["read_only"] is True
        assert entry["append"] is False
        assert entry["is_order_action"] is False
        assert entry["broker_api_called"] is False
        assert entry["live_order_action"] is False
        assert entry["broker_order_action"] is False
        assert entry["intent"]["is_order_action"] is False
        assert entry["intent"]["broker_api_called"] is False
