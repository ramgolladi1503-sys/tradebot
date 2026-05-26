"""EDGE-77 tests.

Safety marker: stale_feed_blocks_order_intent.
"""

from __future__ import annotations

from core.candidate_intent import INTENT_TYPE_ENTRY, INTENT_TYPE_NO_TRADE, create_candidate_intent
from core.strategy_exit_models import (
    EXIT_MODEL_EMPTY_CANDIDATES,
    EXIT_MODEL_NON_ENTRY_INTENT,
    EXIT_MODEL_OPTION_CONFIRMATION_NOT_READY,
    EXIT_MODEL_OPTION_CONFIRMATION_REQUIRED,
    EXIT_MODEL_UNSUPPORTED_DIRECTION,
    EXIT_MODEL_UNSUPPORTED_FAMILY,
    STRATEGY_EXIT_MODEL_STATUS_BLOCKED,
    STRATEGY_EXIT_MODEL_STATUS_READY,
    build_strategy_specific_exit_models,
)


def _candidate(
    *,
    candidate_id: str = "candidate-1",
    family: str = "breakout",
    direction: str = "BUY_CALL",
    intent_type: str = INTENT_TYPE_ENTRY,
    blockers=(),
):
    return create_candidate_intent(
        candidate_intent_id=candidate_id,
        strategy_id=f"{family}_v1",
        instrument="NIFTY",
        direction=direction,
        regime="TREND",
        family=family,
        intent_type=intent_type,
        trigger="test_trigger",
        invalidation="test_invalidation",
        required_evidence_keys=("market_state", "feed_health_truth"),
        blockers=blockers,
    )


def test_builds_strategy_specific_ready_models_for_supported_families():
    candidates = (
        _candidate(candidate_id="breakout-1", family="breakout", direction="BUY_CALL"),
        _candidate(candidate_id="vwap-1", family="vwap", direction="BUY_PUT"),
        _candidate(candidate_id="mean-1", family="mean_reversion", direction="BUY_CALL"),
        _candidate(candidate_id="hero-1", family="zero_hero", direction="BUY_PUT"),
    )

    report = build_strategy_specific_exit_models(candidates)
    payload = report.to_payload()

    assert report.exit_model_ready is True
    assert payload["ready_count"] == 4
    assert payload["blocked_count"] == 0
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert set(payload["ready_candidate_intent_ids"]) == {
        "breakout_1",
        "vwap_1",
        "mean_1",
        "hero_1",
    }


def test_policy_defaults_are_strategy_specific():
    report = build_strategy_specific_exit_models(
        (
            _candidate(candidate_id="breakout-1", family="breakout"),
            _candidate(candidate_id="hero-1", family="zero_hero"),
        )
    )
    models = {model.family: model.to_payload() for model in report.ready_models}

    assert models["breakout"]["policy"]["model_type"] == "trend_continuation_long_option"
    assert models["breakout"]["policy"]["max_hold_seconds"] == 1800
    assert models["zero_hero"]["policy"]["model_type"] == "expiry_momentum_long_option"
    assert models["zero_hero"]["policy"]["max_hold_seconds"] == 300
    assert models["zero_hero"]["policy"]["review_interval_seconds"] == 15


def test_blocks_empty_candidate_input():
    report = build_strategy_specific_exit_models(())

    assert report.exit_model_ready is False
    assert report.blockers == (EXIT_MODEL_EMPTY_CANDIDATES,)
    assert report.to_payload()["model_count"] == 0


def test_blocks_pool_ineligible_candidate():
    report = build_strategy_specific_exit_models(
        (_candidate(candidate_id="blocked-1", blockers=("risk_guard_blocked",)),)
    )
    model = report.blocked_models[0]

    assert model.status == STRATEGY_EXIT_MODEL_STATUS_BLOCKED
    assert "exit_model_candidate_not_pool_eligible" in model.blockers
    assert "risk_guard_blocked" in model.blockers


def test_blocks_non_entry_intent():
    report = build_strategy_specific_exit_models(
        (
            _candidate(
                candidate_id="observe-1",
                intent_type=INTENT_TYPE_NO_TRADE,
                direction="NO_TRADE",
            ),
        )
    )
    model = report.blocked_models[0]

    assert model.status == STRATEGY_EXIT_MODEL_STATUS_BLOCKED
    assert EXIT_MODEL_NON_ENTRY_INTENT in model.blockers
    assert EXIT_MODEL_UNSUPPORTED_DIRECTION in model.blockers


def test_blocks_unsupported_strategy_family():
    report = build_strategy_specific_exit_models(
        (_candidate(candidate_id="custom-1", family="custom_family"),)
    )
    model = report.blocked_models[0]

    assert model.status == STRATEGY_EXIT_MODEL_STATUS_BLOCKED
    assert model.blockers == (EXIT_MODEL_UNSUPPORTED_FAMILY,)


def test_blocks_unsupported_direction_without_lifecycle_mutation():
    report = build_strategy_specific_exit_models(
        (_candidate(candidate_id="sell-1", family="breakout", direction="SELL_CALL"),)
    )
    model_payload = report.blocked_models[0].to_payload()

    assert model_payload["status"] == STRATEGY_EXIT_MODEL_STATUS_BLOCKED
    assert model_payload["blockers"] == [EXIT_MODEL_UNSUPPORTED_DIRECTION]
    assert model_payload["policy"] == {}
    assert model_payload["is_order_action"] is False
    assert model_payload["broker_api_called"] is False


def test_requires_option_confirmation_when_configured():
    report = build_strategy_specific_exit_models(
        (_candidate(candidate_id="confirm-1"),),
        require_option_confirmation=True,
    )
    model = report.blocked_models[0]

    assert model.status == STRATEGY_EXIT_MODEL_STATUS_BLOCKED
    assert model.blockers == (EXIT_MODEL_OPTION_CONFIRMATION_REQUIRED,)


def test_blocks_when_supplied_option_confirmation_does_not_include_candidate():
    report = build_strategy_specific_exit_models(
        (_candidate(candidate_id="confirm-1"),),
        option_confirmation_report={"confirmed_candidate_intent_ids": ["different-id"]},
    )
    model = report.blocked_models[0]

    assert model.status == STRATEGY_EXIT_MODEL_STATUS_BLOCKED
    assert model.blockers == (EXIT_MODEL_OPTION_CONFIRMATION_NOT_READY,)


def test_accepts_supplied_option_confirmation_for_candidate():
    report = build_strategy_specific_exit_models(
        (_candidate(candidate_id="confirm-1"),),
        option_confirmation_report={"confirmed_candidate_intent_ids": ["confirm_1"]},
        require_option_confirmation=True,
    )
    model = report.ready_models[0]

    assert model.status == STRATEGY_EXIT_MODEL_STATUS_READY
    assert model.ready is True
    assert model.to_payload()["policy"]["read_only_guidance_only"] is True
