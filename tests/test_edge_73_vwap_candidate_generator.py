"""Safety regression tests for VWAP CandidateIntent generation."""

from __future__ import annotations

from core.vwap_candidate_generator import (
    VWAP_DEVIATION_TOO_SMALL,
    VWAP_INVALID_NUMERIC_INPUT,
    VWAP_MISSING_INSTRUMENT,
    VWAP_MISSING_LTP,
    VWAP_MISSING_MARKET_STATE,
    VWAP_MISSING_VWAP,
    VWAP_SLOPE_NOT_CONFIRMED,
    build_vwap_candidate_intents,
)


def _base_snapshot(**overrides):
    payload = {
        "symbol": "NIFTY",
        "ltp": 22650.0,
        "vwap": 22600.0,
        "vwap_slope": 0.4,
        "regime": "TREND",
    }
    payload.update(overrides)
    return payload


def test_vwap_generator_creates_upside_candidate_intent_and_pool_entry():
    report = build_vwap_candidate_intents(_base_snapshot(), min_deviation_bps=15.0, min_slope=0.1)
    intent = report.generated_intents[0]
    payload = report.to_payload()

    assert report.generated_intents[1:] == ()
    assert report.valid is True
    assert report.pool_ready is True
    assert intent.strategy_id == "vwap_v1"
    assert intent.instrument == "NIFTY"
    assert intent.direction == "BUY_CALL"
    assert intent.family == "vwap"
    assert intent.regime == "TREND"
    assert intent.intent_type == "ENTRY"
    assert intent.blockers == ()
    assert intent.metadata["vwap_position"] == "ABOVE_VWAP"
    assert intent.metadata["does_not_rank_candidates"] is True
    assert intent.metadata["does_not_score_edge"] is True
    assert report.pool_report.eligible_candidate_intent_ids == (intent.candidate_intent_id,)
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["metadata"]["does_not_touch_runtime"] is True


def test_vwap_generator_creates_downside_candidate_intent():
    report = build_vwap_candidate_intents(
        _base_snapshot(ltp=22540.0, vwap=22600.0, vwap_slope=-0.4),
        min_deviation_bps=15.0,
        min_slope=0.1,
    )
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is True
    assert intent.direction == "BUY_PUT"
    assert intent.intent_type == "ENTRY"
    assert intent.metadata["vwap_position"] == "BELOW_VWAP"
    assert report.pool_report.eligible_candidate_intent_ids == (intent.candidate_intent_id,)


def test_vwap_generator_blocks_neutral_zone():
    report = build_vwap_candidate_intents(_base_snapshot(ltp=22605.0), min_deviation_bps=15.0)
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert intent.intent_type == "NO_TRADE"
    assert intent.blockers == (VWAP_DEVIATION_TOO_SMALL,)
    assert intent.metadata["vwap_position"] == "NEUTRAL_ZONE"
    assert report.pool_report.eligible_intents == ()
    assert report.pool_report.blocked_candidate_intent_ids == (intent.candidate_intent_id,)


def test_vwap_generator_blocks_unconfirmed_slope():
    report = build_vwap_candidate_intents(_base_snapshot(vwap_slope=-0.2), min_deviation_bps=15.0, min_slope=0.1)
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "BUY_CALL"
    assert intent.intent_type == "NO_TRADE"
    assert intent.blockers == (VWAP_SLOPE_NOT_CONFIRMED,)
    assert "vwap_uptrend_blocked_by_slope" in intent.warnings
    assert report.pool_report.blocked_candidate_intent_ids == (intent.candidate_intent_id,)


def test_vwap_generator_blocks_absent_snapshot_fail_closed():
    report = build_vwap_candidate_intents(None)
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert intent.instrument == "UNKNOWN"
    assert VWAP_MISSING_MARKET_STATE in intent.blockers
    assert VWAP_MISSING_INSTRUMENT in intent.blockers
    assert VWAP_MISSING_LTP in intent.blockers
    assert VWAP_MISSING_VWAP in intent.blockers
    assert report.pool_report.blocked_candidate_intent_ids == (intent.candidate_intent_id,)


def test_vwap_generator_blocks_invalid_numeric_input():
    report = build_vwap_candidate_intents(_base_snapshot(ltp="bad-value"))
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert VWAP_INVALID_NUMERIC_INPUT in intent.blockers
    assert VWAP_MISSING_LTP in intent.blockers
    assert intent.metadata["vwap_position"] == "UNKNOWN"


def test_vwap_generator_payload_entries_are_non_action():
    report = build_vwap_candidate_intents(_base_snapshot())
    payload = report.to_payload()

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["generated_intents"][0]["is_order_action"] is False
    assert payload["generated_intents"][0]["broker_api_called"] is False
    assert payload["pool_report"]["is_order_action"] is False
    assert payload["pool_report"]["broker_api_called"] is False
