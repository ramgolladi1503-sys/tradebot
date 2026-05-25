from __future__ import annotations

import json

from core.candidate_intent import (
    CANDIDATE_INTENT_DUPLICATE_ID,
    CANDIDATE_INTENT_EMPTY_INPUT,
    CANDIDATE_INTENT_FORBIDDEN_ACTION_FIELD,
    CANDIDATE_INTENT_INVALID_DIRECTION,
    CANDIDATE_INTENT_INVALID_SAFETY_FLAGS,
    CANDIDATE_INTENT_MISSING_FIELD,
    CANDIDATE_INTENT_SOURCE,
    INTENT_TYPE_ENTRY,
    create_candidate_intent,
    validate_candidate_intent,
    validate_candidate_intents,
)


def _intent(**overrides):
    values = {
        "strategy_id": "breakout_v1",
        "instrument": "NIFTY",
        "direction": "BUY_CALL",
        "regime": "BULL_TREND",
        "family": "breakout",
        "trigger": "price breaks opening range with volume expansion",
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


def test_candidate_intent_payload_is_read_only_non_action_and_not_order_intent():
    intent = _intent()
    payload = json.loads(intent.to_json())

    assert payload["candidate_intent_id"] == "breakout_v1:nifty:buy_call:bull_trend:entry"
    assert payload["intent_type"] == INTENT_TYPE_ENTRY
    assert payload["pool_eligible"] is True
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["source"] == CANDIDATE_INTENT_SOURCE
    assert "quantity" not in payload
    assert "price" not in payload
    assert "order_type" not in payload


def test_candidate_intent_validation_accepts_valid_intent_and_normalizes_lookup():
    report = validate_candidate_intent(_intent(candidate_intent_id="Breakout-V1 NIFTY Buy-Call"))

    assert report.valid is True
    assert report.rejected_intents == ()
    assert report.candidate_intent_ids == ("breakout_v1_nifty_buy_call",)
    assert report.get("breakout v1 nifty buy call").strategy_id == "breakout_v1"
    assert report.to_payload()["is_order_action"] is False
    assert report.metadata["does_not_create_order_intent"] is True


def test_candidate_intent_validation_rejects_missing_required_fields():
    payload = _intent().to_payload()
    payload["trigger"] = ""
    payload["required_evidence_keys"] = []

    report = validate_candidate_intent(payload)

    assert report.valid is False
    assert report.intents == ()
    assert report.rejected_intents[0].blockers == (CANDIDATE_INTENT_MISSING_FIELD,)
    assert CANDIDATE_INTENT_MISSING_FIELD in report.warnings


def test_candidate_intent_validation_rejects_unsafe_action_flags():
    payload = _intent().to_payload()
    payload["is_order_action"] = True
    payload["broker_api_called"] = True

    report = validate_candidate_intent(payload)

    assert report.valid is False
    assert report.intents == ()
    assert report.rejected_intents[0].blockers == (CANDIDATE_INTENT_INVALID_SAFETY_FLAGS,)


def test_candidate_intent_validation_rejects_forbidden_order_fields():
    payload = _intent().to_payload()
    payload["quantity"] = 75
    payload["order_type"] = "MARKET"

    report = validate_candidate_intent(payload)

    assert report.valid is False
    assert report.intents == ()
    assert report.rejected_intents[0].blockers == (CANDIDATE_INTENT_FORBIDDEN_ACTION_FIELD,)


def test_candidate_intent_validation_rejects_unknown_direction():
    payload = _intent(direction="SIDEWAYS").to_payload()

    report = validate_candidate_intent(payload)

    assert report.valid is False
    assert report.intents == ()
    assert report.rejected_intents[0].blockers == (CANDIDATE_INTENT_INVALID_DIRECTION,)


def test_candidate_intent_validation_rejects_duplicate_intent_ids():
    first = _intent(candidate_intent_id="duplicate")
    second = _intent(candidate_intent_id="duplicate", instrument="BANKNIFTY")

    report = validate_candidate_intents((first, second))

    assert report.valid is False
    assert report.candidate_intent_ids == ("duplicate",)
    assert report.rejected_intents[0].blockers == (CANDIDATE_INTENT_DUPLICATE_ID,)


def test_blocked_candidate_intent_is_contract_valid_but_not_pool_eligible():
    intent = _intent(blockers=("weak_signal",), warnings=("needs_confirmation",))

    report = validate_candidate_intent(intent)
    accepted = report.get(intent.candidate_intent_id)

    assert report.valid is True
    assert accepted.pool_eligible is False
    assert accepted.blockers == ("weak_signal",)
    assert accepted.warnings == ("needs_confirmation",)
    assert accepted.is_order_action is False


def test_candidate_intent_validation_blocks_empty_input():
    report = validate_candidate_intents(())

    assert report.valid is False
    assert report.intents == ()
    assert report.rejected_intents == ()
    assert report.blockers == (CANDIDATE_INTENT_EMPTY_INPUT,)
