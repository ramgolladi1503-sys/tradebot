"""Safety regression tests for Zero Hero expiry CandidateIntent generation."""

from __future__ import annotations

from core.zero_hero_candidate_generator import (
    ZERO_HERO_INVALID_NUMERIC_INPUT,
    ZERO_HERO_MISSING_INSTRUMENT,
    ZERO_HERO_MISSING_MARKET_STATE,
    ZERO_HERO_MISSING_PREMIUM,
    ZERO_HERO_MISSING_UNDERLYING_MOMENTUM,
    ZERO_HERO_MOMENTUM_NOT_CONFIRMED,
    ZERO_HERO_NOT_EXPIRY_CONTEXT,
    ZERO_HERO_PREMIUM_OUT_OF_BOUNDS,
    ZERO_HERO_VOLUME_NOT_CONFIRMED,
    build_zero_hero_candidate_intents,
)


def _base_snapshot(**overrides):
    payload = {
        "symbol": "NIFTY",
        "premium": 12.0,
        "dte": 0,
        "underlying_momentum": 35.0,
        "vol_z": 0.9,
        "regime": "EXPIRY",
    }
    payload.update(overrides)
    return payload


def test_zero_hero_generator_creates_call_momentum_candidate_intent():
    report = build_zero_hero_candidate_intents(_base_snapshot())
    intent = report.generated_intents[0]
    payload = report.to_payload()

    assert report.generated_intents[1:] == ()
    assert report.valid is True
    assert report.pool_ready is True
    assert intent.strategy_id == "zero_hero_v1"
    assert intent.instrument == "NIFTY"
    assert intent.direction == "BUY_CALL"
    assert intent.family == "zero_hero"
    assert intent.regime == "EXPIRY"
    assert intent.intent_type == "ENTRY"
    assert intent.blockers == ()
    assert intent.metadata["expiry_context"] == "EXPIRY_CONTEXT"
    assert intent.metadata["premium_state"] == "TRADEABLE_PREMIUM"
    assert intent.metadata["does_not_rank_candidates"] is True
    assert intent.metadata["does_not_score_edge"] is True
    assert report.pool_report.eligible_candidate_intent_ids == (intent.candidate_intent_id,)
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["metadata"]["does_not_touch_runtime"] is True


def test_zero_hero_generator_creates_put_momentum_candidate_intent():
    report = build_zero_hero_candidate_intents(_base_snapshot(underlying_momentum=-35.0))
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is True
    assert intent.direction == "BUY_PUT"
    assert intent.intent_type == "ENTRY"
    assert intent.metadata["expiry_context"] == "EXPIRY_CONTEXT"
    assert report.pool_report.eligible_candidate_intent_ids == (intent.candidate_intent_id,)


def test_zero_hero_generator_blocks_non_expiry_context():
    report = build_zero_hero_candidate_intents(_base_snapshot(dte=2, is_expiry_day=False))
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert intent.intent_type == "NO_TRADE"
    assert intent.blockers == (ZERO_HERO_NOT_EXPIRY_CONTEXT,)
    assert intent.metadata["expiry_context"] == "NON_EXPIRY_CONTEXT"
    assert report.pool_report.eligible_intents == ()
    assert report.pool_report.blocked_candidate_intent_ids == (intent.candidate_intent_id,)


def test_zero_hero_generator_blocks_premium_out_of_bounds():
    report = build_zero_hero_candidate_intents(_base_snapshot(premium=40.0), max_premium=25.0)
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert intent.blockers == (ZERO_HERO_PREMIUM_OUT_OF_BOUNDS,)
    assert intent.metadata["premium_state"] == "PREMIUM_TOO_HIGH"


def test_zero_hero_generator_blocks_weak_momentum():
    report = build_zero_hero_candidate_intents(_base_snapshot(underlying_momentum=5.0), min_momentum_bps=20.0)
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert intent.blockers == (ZERO_HERO_MOMENTUM_NOT_CONFIRMED,)
    assert report.pool_report.blocked_candidate_intent_ids == (intent.candidate_intent_id,)


def test_zero_hero_generator_blocks_weak_volume():
    report = build_zero_hero_candidate_intents(_base_snapshot(vol_z=0.1), min_volume_z=0.5)
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert intent.blockers == (ZERO_HERO_VOLUME_NOT_CONFIRMED,)
    assert "zero_hero_blocked_by_volume" in intent.warnings
    assert report.pool_report.blocked_candidate_intent_ids == (intent.candidate_intent_id,)


def test_zero_hero_generator_blocks_absent_snapshot_fail_closed():
    report = build_zero_hero_candidate_intents(None)
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert intent.instrument == "UNKNOWN"
    assert ZERO_HERO_MISSING_MARKET_STATE in intent.blockers
    assert ZERO_HERO_MISSING_INSTRUMENT in intent.blockers
    assert ZERO_HERO_MISSING_PREMIUM in intent.blockers
    assert ZERO_HERO_MISSING_UNDERLYING_MOMENTUM in intent.blockers
    assert report.pool_report.blocked_candidate_intent_ids == (intent.candidate_intent_id,)


def test_zero_hero_generator_blocks_invalid_numeric_input():
    report = build_zero_hero_candidate_intents(_base_snapshot(premium="bad-value"))
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert ZERO_HERO_INVALID_NUMERIC_INPUT in intent.blockers
    assert ZERO_HERO_MISSING_PREMIUM in intent.blockers
    assert intent.metadata["premium_state"] == "UNKNOWN"


def test_zero_hero_generator_payload_entries_are_non_action():
    report = build_zero_hero_candidate_intents(_base_snapshot())
    payload = report.to_payload()

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["generated_intents"][0]["is_order_action"] is False
    assert payload["generated_intents"][0]["broker_api_called"] is False
    assert payload["pool_report"]["is_order_action"] is False
    assert payload["pool_report"]["broker_api_called"] is False
