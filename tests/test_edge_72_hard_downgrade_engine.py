from __future__ import annotations

import json

from core.candidate_hard_downgrade import (
    DOWNGRADE_DECISION_ADVISORY_ONLY,
    DOWNGRADE_DECISION_BLOCKED,
    DOWNGRADE_DECISION_CANDIDATE_READY,
    HARD_DOWNGRADE_CLASSIFICATION_BLOCKED,
    HARD_DOWNGRADE_CLASSIFICATION_INVALID,
    HARD_DOWNGRADE_EMPTY_INPUT,
    HARD_DOWNGRADE_EVIDENCE_INCOMPLETE,
    HARD_DOWNGRADE_MALFORMED_CANDIDATE,
    HARD_DOWNGRADE_UNKNOWN_DIRECTION,
    HARD_DOWNGRADE_UNKNOWN_FAMILY,
    HARD_DOWNGRADE_UNKNOWN_REGIME,
    CANDIDATE_HARD_DOWNGRADE_SOURCE,
    apply_candidate_hard_downgrades,
)
from core.regime_state import REGIME_BULL_TREND, REGIME_RANGE_BOUND
from core.strategy_candidate_classification import classify_strategy_candidates
from core.strategy_candidate_normalization import normalize_strategy_candidates
from core.strategy_candidate_pool import build_strategy_candidate_pool
from core.strategy_spec import DIRECTION_BUY_CALL, FAMILY_VWAP, StrategySpec


def _spec(
    strategy_id="sample_strategy",
    instruments=("NIFTY",),
    declared_regimes=(REGIME_BULL_TREND, REGIME_RANGE_BOUND),
    required_evidence_keys=("market_state", "regime_state", "feed_health_truth", "quote_truth"),
):
    return StrategySpec(
        strategy_id=strategy_id,
        name="Sample Strategy",
        family=FAMILY_VWAP,
        module_path="strategies.sample",
        callable_name="generate_signal",
        instruments=instruments,
        declared_regimes=declared_regimes,
        blocked_regimes=("UNKNOWN", "OUT_OF_SESSION", "LIQUIDITY_STRESSED", "VOLATILITY_STRESSED"),
        required_market_state_dimensions=("trend", "volatility", "breadth", "liquidity", "session"),
        required_evidence_keys=required_evidence_keys,
        direction_capabilities=(DIRECTION_BUY_CALL,),
        min_market_state_confidence=0.6,
        description="Sample metadata",
    )


def _evidence_keys():
    return (
        "market_state",
        "regime_state",
        "feed_health_truth",
        "quote_truth",
        "strategy_quality_audit",
        "paper_outcome_journal",
    )


def _classification_report(*, regime=REGIME_BULL_TREND, instruments=("NIFTY",), spec=None):
    pool = build_strategy_candidate_pool(
        regime=regime,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[spec or _spec(instruments=instruments)],
    )
    normalized = normalize_strategy_candidates(pool)
    return classify_strategy_candidates(normalized)


def test_hard_downgrade_keeps_clean_classified_candidates_ready_without_scoring():
    classified = _classification_report(instruments=("BANKNIFTY", "NIFTY"))

    report = apply_candidate_hard_downgrades(classified)

    assert report.valid is True
    assert report.blockers == ()
    assert report.blocked_decisions == ()
    assert report.candidate_ready_ids == (
        "sample_strategy:banknifty:buy_call:bull_trend",
        "sample_strategy:nifty:buy_call:bull_trend",
    )
    decision = report.get("sample-strategy:nifty:buy-call:bull-trend")
    assert decision.decision == DOWNGRADE_DECISION_CANDIDATE_READY
    assert decision.candidate_ready is True
    assert decision.advisory_only is False
    assert decision.blocked is False
    assert decision.reasons == ()
    assert "score" not in decision.to_payload()
    assert "rank" not in decision.to_payload()


def test_hard_downgrade_payload_is_read_only_non_action_and_not_runtime_wired():
    report = apply_candidate_hard_downgrades(_classification_report())
    payload = json.loads(report.to_json())

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["source"] == CANDIDATE_HARD_DOWNGRADE_SOURCE
    assert payload["metadata"]["does_not_import_strategy_modules"] is True
    assert payload["metadata"]["does_not_execute_strategy_callables"] is True
    assert payload["metadata"]["does_not_rank_candidates"] is True
    assert payload["metadata"]["does_not_score_edge"] is True
    assert payload["metadata"]["does_not_select_candidates"] is True
    assert payload["metadata"]["does_not_allocate_capital"] is True
    assert payload["decisions"][0]["is_order_action"] is False
    assert payload["decisions"][0]["broker_api_called"] is False


def test_hard_downgrade_turns_incomplete_evidence_into_advisory_only():
    classified = _classification_report(
        spec=_spec(required_evidence_keys=("market_state", "regime_state")),
    )

    report = apply_candidate_hard_downgrades(classified)

    decision = report.decisions[0]
    assert report.valid is True
    assert decision.decision == DOWNGRADE_DECISION_ADVISORY_ONLY
    assert decision.hard_downgraded is True
    assert decision.candidate_ready is False
    assert decision.advisory_only is True
    assert HARD_DOWNGRADE_EVIDENCE_INCOMPLETE in decision.reasons
    assert report.advisory_only_ids == ("sample_strategy:nifty:buy_call:bull_trend",)


def test_hard_downgrade_turns_unknown_metadata_into_advisory_only():
    classified = classify_strategy_candidates(
        (
            {
                "canonical_candidate_id": "unknown_strategy:gold:sideways:mystery_regime",
                "strategy_id": "unknown_strategy",
                "instrument": "GOLD",
                "regime": "MYSTERY_REGIME",
                "direction": "SIDEWAYS",
                "family": "MYSTERY_FAMILY",
                "required_evidence_keys": _evidence_keys(),
            },
        )
    )

    report = apply_candidate_hard_downgrades(classified)

    decision = report.decisions[0]
    assert decision.decision == DOWNGRADE_DECISION_ADVISORY_ONLY
    assert decision.candidate_ready is False
    assert decision.advisory_only is True
    assert HARD_DOWNGRADE_UNKNOWN_DIRECTION in decision.reasons
    assert HARD_DOWNGRADE_UNKNOWN_REGIME in decision.reasons
    assert HARD_DOWNGRADE_UNKNOWN_FAMILY in decision.reasons


def test_hard_downgrade_blocks_empty_input_fail_closed():
    report = apply_candidate_hard_downgrades(())

    assert report.valid is False
    assert report.decisions == ()
    assert report.blocked_decisions == ()
    assert report.blockers == (HARD_DOWNGRADE_EMPTY_INPUT,)


def test_hard_downgrade_blocks_invalid_classification_report_fail_closed():
    invalid_classified = classify_strategy_candidates(())

    report = apply_candidate_hard_downgrades(invalid_classified)

    assert invalid_classified.valid is False
    assert report.valid is False
    assert report.decisions == ()
    assert HARD_DOWNGRADE_CLASSIFICATION_INVALID in report.blockers
    assert HARD_DOWNGRADE_EMPTY_INPUT in report.blockers
    assert any(reason.startswith("classification:") for reason in report.blockers)


def test_hard_downgrade_keeps_classification_blocked_rows_blocked():
    classified = classify_strategy_candidates(
        (
            {
                "canonical_candidate_id": "bad",
                "strategy_id": "",
                "instrument": "NIFTY",
                "regime": REGIME_BULL_TREND,
                "direction": DIRECTION_BUY_CALL,
                "family": FAMILY_VWAP,
                "required_evidence_keys": _evidence_keys(),
            },
        )
    )

    report = apply_candidate_hard_downgrades(classified)

    assert report.valid is True
    assert report.decisions == ()
    blocked = report.blocked_decisions[0]
    assert blocked.decision == DOWNGRADE_DECISION_BLOCKED
    assert blocked.blocked is True
    assert blocked.candidate_ready is False
    assert HARD_DOWNGRADE_CLASSIFICATION_BLOCKED in blocked.blockers
    assert report.blocked_ids == ("bad",)


def test_hard_downgrade_blocks_malformed_payloads():
    report = apply_candidate_hard_downgrades((object(),))

    assert report.valid is True
    assert report.decisions == ()
    blocked = report.blocked_decisions[0]
    assert blocked.decision == DOWNGRADE_DECISION_BLOCKED
    assert HARD_DOWNGRADE_MALFORMED_CANDIDATE in blocked.blockers


def test_hard_downgrade_does_not_import_strategy_modules_or_run_callables():
    classified = _classification_report(spec=_spec(strategy_id="metadata_only_strategy"))

    report = apply_candidate_hard_downgrades(classified)

    decision = report.get("metadata_only_strategy:nifty:buy_call:bull_trend")
    assert decision.candidate_ready is True
    assert decision.is_order_action is False
    assert decision.broker_api_called is False
    assert report.metadata["does_not_import_strategy_modules"] is True
    assert report.metadata["does_not_execute_strategy_callables"] is True
