"""Safety regression tests for mean-reversion CandidateIntent generation."""

from __future__ import annotations

from core.mean_reversion_candidate_generator import (
    MEAN_REVERSION_DEVIATION_TOO_SMALL,
    MEAN_REVERSION_INVALID_NUMERIC_INPUT,
    MEAN_REVERSION_MISSING_ANCHOR,
    MEAN_REVERSION_MISSING_INSTRUMENT,
    MEAN_REVERSION_MISSING_LTP,
    MEAN_REVERSION_MISSING_MARKET_STATE,
    MEAN_REVERSION_OSCILLATOR_NOT_CONFIRMED,
    build_mean_reversion_candidate_intents,
)


def _base_snapshot(**overrides):
    payload = {
        "symbol": "NIFTY",
        "ltp": 22690.0,
        "mean_anchor": 22600.0,
        "oscillator": -0.7,
        "regime": "RANGE",
    }
    payload.update(overrides)
    return payload


def test_mean_reversion_generator_creates_upper_extension_candidate_intent():
    report = build_mean_reversion_candidate_intents(
        _base_snapshot(),
        min_deviation_bps=30.0,
        min_oscillator_confirmation=0.2,
    )
    intent = report.generated_intents[0]
    payload = report.to_payload()

    assert report.generated_intents[1:] == ()
    assert report.valid is True
    assert report.pool_ready is True
    assert intent.strategy_id == "mean_reversion_v1"
    assert intent.instrument == "NIFTY"
    assert intent.direction == "BUY_PUT"
    assert intent.family == "mean_reversion"
    assert intent.regime == "RANGE"
    assert intent.intent_type == "ENTRY"
    assert intent.blockers == ()
    assert intent.metadata["reversion_state"] == "EXTENDED_ABOVE_ANCHOR"
    assert intent.metadata["does_not_rank_candidates"] is True
    assert intent.metadata["does_not_score_edge"] is True
    assert report.pool_report.eligible_candidate_intent_ids == (intent.candidate_intent_id,)
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["metadata"]["does_not_touch_runtime"] is True


def test_mean_reversion_generator_creates_lower_extension_candidate_intent():
    report = build_mean_reversion_candidate_intents(
        _base_snapshot(ltp=22510.0, mean_anchor=22600.0, oscillator=0.7),
        min_deviation_bps=30.0,
        min_oscillator_confirmation=0.2,
    )
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is True
    assert intent.direction == "BUY_CALL"
    assert intent.intent_type == "ENTRY"
    assert intent.metadata["reversion_state"] == "EXTENDED_BELOW_ANCHOR"
    assert report.pool_report.eligible_candidate_intent_ids == (intent.candidate_intent_id,)


def test_mean_reversion_generator_blocks_neutral_zone():
    report = build_mean_reversion_candidate_intents(_base_snapshot(ltp=22605.0), min_deviation_bps=30.0)
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert intent.intent_type == "NO_TRADE"
    assert intent.blockers == (MEAN_REVERSION_DEVIATION_TOO_SMALL,)
    assert intent.metadata["reversion_state"] == "NEUTRAL_ZONE"
    assert report.pool_report.eligible_intents == ()
    assert report.pool_report.blocked_candidate_intent_ids == (intent.candidate_intent_id,)


def test_mean_reversion_generator_blocks_unconfirmed_oscillator():
    report = build_mean_reversion_candidate_intents(
        _base_snapshot(oscillator=0.1),
        min_deviation_bps=30.0,
        min_oscillator_confirmation=0.2,
    )
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "BUY_PUT"
    assert intent.intent_type == "NO_TRADE"
    assert intent.blockers == (MEAN_REVERSION_OSCILLATOR_NOT_CONFIRMED,)
    assert "mean_reversion_down_blocked_by_oscillator" in intent.warnings
    assert report.pool_report.blocked_candidate_intent_ids == (intent.candidate_intent_id,)


def test_mean_reversion_generator_blocks_absent_snapshot_fail_closed():
    report = build_mean_reversion_candidate_intents(None)
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert intent.instrument == "UNKNOWN"
    assert MEAN_REVERSION_MISSING_MARKET_STATE in intent.blockers
    assert MEAN_REVERSION_MISSING_INSTRUMENT in intent.blockers
    assert MEAN_REVERSION_MISSING_LTP in intent.blockers
    assert MEAN_REVERSION_MISSING_ANCHOR in intent.blockers
    assert report.pool_report.blocked_candidate_intent_ids == (intent.candidate_intent_id,)


def test_mean_reversion_generator_blocks_invalid_numeric_input():
    report = build_mean_reversion_candidate_intents(_base_snapshot(ltp="bad-value"))
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert MEAN_REVERSION_INVALID_NUMERIC_INPUT in intent.blockers
    assert MEAN_REVERSION_MISSING_LTP in intent.blockers
    assert intent.metadata["reversion_state"] == "UNKNOWN"


def test_mean_reversion_generator_payload_entries_are_non_action():
    report = build_mean_reversion_candidate_intents(_base_snapshot())
    payload = report.to_payload()

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["generated_intents"][0]["is_order_action"] is False
    assert payload["generated_intents"][0]["broker_api_called"] is False
    assert payload["pool_report"]["is_order_action"] is False
    assert payload["pool_report"]["broker_api_called"] is False
