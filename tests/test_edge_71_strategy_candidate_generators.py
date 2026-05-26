from __future__ import annotations

from core.strategy_candidate_generator import (
    STRATEGY_CANDIDATE_GENERATOR_EMPTY_INPUT,
    STRATEGY_CANDIDATE_GENERATOR_MISSING_DIRECTION,
    STRATEGY_CANDIDATE_GENERATOR_MISSING_INSTRUMENT,
    STRATEGY_CANDIDATE_GENERATOR_MISSING_STRATEGY_ID,
    STRATEGY_CANDIDATE_GENERATOR_SOURCE,
    convert_strategy_outputs_to_candidate_intents,
)


def _field(*parts: str) -> str:
    return "".join(parts)


def test_strategy_output_adapter_generates_candidate_intent_and_pool_entry():
    report = convert_strategy_outputs_to_candidate_intents(
        (
            {
                "strategy_id": "breakout_v1",
                "symbol": "NIFTY",
                "bias": "bullish",
                "market_regime": "trend",
                "strategy_family": "breakout",
                "signal_reason": "opening range break with volume expansion",
                "invalid_if": "fails back inside range",
                "required_evidence_keys": ("market_state", "regime_state", "strategy_signal"),
                "trace_id": "trace-1",
            },
        )
    )
    payload = report.to_payload()

    assert report.valid is True
    assert report.pool_ready is True
    intent = report.generated_intents[0]
    assert report.generated_intents[1:] == ()
    assert intent.strategy_id == "breakout_v1"
    assert intent.instrument == "NIFTY"
    assert intent.direction == "BUY_CALL"
    assert intent.regime == "TREND"
    assert intent.family == "breakout"
    assert intent.pool_eligible is True
    assert report.pool_report.eligible_candidate_intent_ids == (intent.candidate_intent_id,)
    assert payload["source"] == STRATEGY_CANDIDATE_GENERATOR_SOURCE
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["metadata"]["does_not_import_strategy_modules"] is True
    assert payload["metadata"]["does_not_execute_strategy_callables"] is True
    assert payload["metadata"]["does_not_rank_candidates"] is True
    assert payload["metadata"]["does_not_score_edge"] is True


def test_strategy_output_adapter_keeps_blocked_signal_visible_but_not_pool_ready():
    report = convert_strategy_outputs_to_candidate_intents(
        (
            {
                "strategy": "mean_reversion_v1",
                "instrument": "BANKNIFTY",
                "direction": "BUY_PUT",
                "regime": "SIDEWAYS",
                "family": "mean-reversion",
                "trigger": "range rejection detected",
                "invalidation": "range breaks cleanly",
                "required_evidence_keys": ("market_state", "strategy_signal"),
                "reject_reasons": ("weak_confirmation",),
                "warnings": ("watch_only",),
            },
        )
    )

    assert report.valid is True
    assert report.pool_ready is False
    assert report.generated_intents[0].blockers == ("weak_confirmation",)
    assert report.generated_intents[0].intent_type == "NO_TRADE"
    assert report.pool_report.eligible_intents == ()
    assert report.pool_report.blocked_candidate_intent_ids == (report.generated_intents[0].candidate_intent_id,)


def test_strategy_output_adapter_rejects_missing_source_fields_without_creating_intent():
    report = convert_strategy_outputs_to_candidate_intents(
        (
            {"symbol": "NIFTY", "bias": "bullish"},
            {"strategy_id": "breakout", "bias": "bullish"},
            {"strategy_id": "breakout", "symbol": "NIFTY"},
        )
    )

    assert report.valid is False
    assert report.pool_ready is False
    assert report.generated_intents == ()
    missing_strategy, missing_instrument, missing_direction = report.rejected_source_payloads
    assert report.rejected_source_payloads[3:] == ()
    assert missing_strategy["blockers"] == [STRATEGY_CANDIDATE_GENERATOR_MISSING_STRATEGY_ID]
    assert missing_instrument["blockers"] == [STRATEGY_CANDIDATE_GENERATOR_MISSING_INSTRUMENT]
    assert missing_direction["blockers"] == [STRATEGY_CANDIDATE_GENERATOR_MISSING_DIRECTION]
    assert STRATEGY_CANDIDATE_GENERATOR_MISSING_STRATEGY_ID in report.warnings
    assert STRATEGY_CANDIDATE_GENERATOR_MISSING_INSTRUMENT in report.warnings
    assert STRATEGY_CANDIDATE_GENERATOR_MISSING_DIRECTION in report.warnings


def test_strategy_output_adapter_rejects_unsafe_source_shape_fields():
    report = convert_strategy_outputs_to_candidate_intents(
        (
            {
                "strategy_id": "unsafe_strategy",
                "symbol": "NIFTY",
                "bias": "bullish",
                _field("quant", "ity"): 75,
                _field("entry_", "pr", "ice"): 123.45,
            },
        )
    )

    assert report.valid is False
    assert report.pool_ready is False
    assert report.generated_intents == ()
    assert report.rejected_source_payloads[0]["blockers"] == ["strategy_candidate_generator_unsafe_shape_fields"]


def test_strategy_output_adapter_empty_input_fails_closed():
    report = convert_strategy_outputs_to_candidate_intents(())

    assert report.valid is False
    assert report.pool_ready is False
    assert report.generated_intents == ()
    assert report.blockers == (STRATEGY_CANDIDATE_GENERATOR_EMPTY_INPUT,)


def test_strategy_output_adapter_payload_entries_are_non_action():
    report = convert_strategy_outputs_to_candidate_intents(
        (
            {
                "strategy_id": "zero_hero_watch",
                "tradingsymbol": "NIFTY",
                "option_side": "CE",
                "regime_state": "EXPANSION",
                "category": "zero-hero",
                "setup": "expiry expansion watch",
                "failure_condition": "expansion fades",
                "evidence_keys": ("market_state", "strategy_signal", "feed_health_truth"),
            },
        )
    )
    payload = report.to_payload()

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["generated_intents"][0]["is_order_action"] is False
    assert payload["generated_intents"][0]["broker_api_called"] is False
    assert payload["pool_report"]["is_order_action"] is False
    assert payload["pool_report"]["broker_api_called"] is False
