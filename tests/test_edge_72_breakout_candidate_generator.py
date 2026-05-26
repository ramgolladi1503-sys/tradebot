"""Safety regression tests for breakout CandidateIntent generation.

The suite proves blocked breakout hypotheses cannot become pool-ready and
that serialized evidence remains non-action: is_order_action, broker_api_called,
and live_order_action are explicitly false.
"""

from __future__ import annotations

from core.breakout_candidate_generator import (
    BREAKOUT_CANDIDATE_GENERATOR_SOURCE,
    BREAKOUT_INVALID_RANGE,
    BREAKOUT_MISSING_INSTRUMENT,
    BREAKOUT_MISSING_LTP,
    BREAKOUT_MISSING_MARKET_STATE,
    BREAKOUT_NO_RANGE_BREAK,
    BREAKOUT_VOLUME_NOT_CONFIRMED,
    build_breakout_candidate_intents,
)


def _base_snapshot(**overrides):
    payload = {
        "symbol": "NIFTY",
        "ltp": 22620.0,
        "orb_high": 22600.0,
        "orb_low": 22550.0,
        "vol_z": 0.9,
        "regime": "TREND",
    }
    payload.update(overrides)
    return payload


def test_breakout_generator_creates_upside_candidate_intent_and_pool_entry():
    report = build_breakout_candidate_intents(_base_snapshot())
    intent = report.generated_intents[0]
    payload = report.to_payload()

    assert report.generated_intents[1:] == ()
    assert report.valid is True
    assert report.pool_ready is True
    assert intent.strategy_id == "breakout_v1"
    assert intent.instrument == "NIFTY"
    assert intent.direction == "BUY_CALL"
    assert intent.family == "breakout"
    assert intent.regime == "TREND"
    assert intent.intent_type == "ENTRY"
    assert intent.blockers == ()
    assert intent.metadata["range_position"] == "ABOVE_RANGE"
    assert report.pool_report.eligible_candidate_intent_ids == (intent.candidate_intent_id,)
    assert payload["source"] == BREAKOUT_CANDIDATE_GENERATOR_SOURCE
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["metadata"]["does_not_rank_candidates"] is True
    assert payload["metadata"]["does_not_score_edge"] is True
    assert payload["metadata"]["does_not_touch_runtime"] is True


def test_breakout_generator_creates_downside_candidate_intent():
    report = build_breakout_candidate_intents(_base_snapshot(ltp=22520.0))
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is True
    assert intent.direction == "BUY_PUT"
    assert intent.intent_type == "ENTRY"
    assert intent.metadata["range_position"] == "BELOW_RANGE"
    assert report.pool_report.eligible_candidate_intent_ids == (intent.candidate_intent_id,)


def test_breakout_generator_blocks_inside_range_without_rejecting_evidence():
    report = build_breakout_candidate_intents(_base_snapshot(ltp=22580.0))
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert intent.intent_type == "NO_TRADE"
    assert intent.blockers == (BREAKOUT_NO_RANGE_BREAK,)
    assert intent.metadata["range_position"] == "INSIDE_RANGE"
    assert report.pool_report.eligible_intents == ()
    assert report.pool_report.blocked_candidate_intent_ids == (intent.candidate_intent_id,)


def test_breakout_generator_blocks_low_volume_breakout():
    report = build_breakout_candidate_intents(_base_snapshot(vol_z=0.1), min_volume_z=0.5)
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "BUY_CALL"
    assert intent.intent_type == "NO_TRADE"
    assert intent.blockers == (BREAKOUT_VOLUME_NOT_CONFIRMED,)
    assert "breakout_hypothesis_blocked_by_volume" in intent.warnings
    assert report.pool_report.blocked_candidate_intent_ids == (intent.candidate_intent_id,)


def test_breakout_generator_blocks_invalid_range():
    report = build_breakout_candidate_intents(_base_snapshot(orb_high=22500.0, orb_low=22550.0))
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert intent.blockers == (BREAKOUT_INVALID_RANGE,)
    assert intent.metadata["range_position"] == "INVALID_RANGE"


def test_breakout_generator_blocks_missing_snapshot_fail_closed():
    report = build_breakout_candidate_intents(None)
    intent = report.generated_intents[0]

    assert report.valid is True
    assert report.pool_ready is False
    assert intent.direction == "NO_TRADE"
    assert intent.instrument == "UNKNOWN"
    assert BREAKOUT_MISSING_MARKET_STATE in intent.blockers
    assert BREAKOUT_MISSING_INSTRUMENT in intent.blockers
    assert BREAKOUT_MISSING_LTP in intent.blockers
    assert report.pool_report.blocked_candidate_intent_ids == (intent.candidate_intent_id,)


def test_breakout_generator_payload_entries_are_non_action():
    report = build_breakout_candidate_intents(_base_snapshot())
    payload = report.to_payload()

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["generated_intents"][0]["is_order_action"] is False
    assert payload["generated_intents"][0]["broker_api_called"] is False
    assert payload["pool_report"]["is_order_action"] is False
    assert payload["pool_report"]["broker_api_called"] is False
