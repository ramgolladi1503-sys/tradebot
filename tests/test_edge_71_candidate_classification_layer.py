from __future__ import annotations

import json

from core.regime_state import REGIME_BULL_TREND, REGIME_RANGE_BOUND
from core.strategy_candidate_classification import (
    CLASSIFICATION_EMPTY_INPUT,
    CLASSIFICATION_EVIDENCE_INCOMPLETE,
    CLASSIFICATION_MISSING_FIELD,
    CLASSIFICATION_NORMALIZATION_INVALID,
    CLASSIFICATION_UNKNOWN_DIRECTION,
    CLASSIFICATION_UNKNOWN_FAMILY,
    CLASSIFICATION_UNKNOWN_REGIME,
    DIRECTION_CLASS_CALL_BIAS,
    EVIDENCE_CLASS_CORE_COMPLETE,
    EVIDENCE_CLASS_INCOMPLETE,
    FAMILY_CLASS_UNKNOWN,
    FAMILY_CLASS_VWAP,
    INSTRUMENT_CLASS_INDEX,
    REGIME_CLASS_RANGE,
    REGIME_CLASS_TREND,
    STRATEGY_CANDIDATE_CLASSIFICATION_SOURCE,
    classify_strategy_candidates,
)
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


def _normalized_report(*, regime=REGIME_BULL_TREND, instruments=("NIFTY",), spec=None):
    pool = build_strategy_candidate_pool(
        regime=regime,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[spec or _spec(instruments=instruments)],
    )
    return normalize_strategy_candidates(pool)


def test_classification_labels_normalized_candidates_from_real_pool_flow():
    normalized = _normalized_report(instruments=("BANKNIFTY", "NIFTY"))

    report = classify_strategy_candidates(normalized)

    assert report.valid is True
    assert report.blockers == ()
    assert report.blocked_candidates == ()
    assert report.canonical_candidate_ids == (
        "sample_strategy:banknifty:buy_call:bull_trend",
        "sample_strategy:nifty:buy_call:bull_trend",
    )
    candidate = report.get("sample-strategy:nifty:buy-call:bull-trend")
    assert candidate.direction_class == DIRECTION_CLASS_CALL_BIAS
    assert candidate.regime_class == REGIME_CLASS_TREND
    assert candidate.family_class == FAMILY_CLASS_VWAP
    assert candidate.instrument_class == INSTRUMENT_CLASS_INDEX
    assert candidate.evidence_class == EVIDENCE_CLASS_CORE_COMPLETE
    assert candidate.valid is True


def test_classification_payload_is_read_only_non_action_and_not_ranked_or_scored():
    report = classify_strategy_candidates(_normalized_report())
    payload = json.loads(report.to_json())

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["source"] == STRATEGY_CANDIDATE_CLASSIFICATION_SOURCE
    assert payload["metadata"]["does_not_import_strategy_modules"] is True
    assert payload["metadata"]["does_not_execute_strategy_callables"] is True
    assert payload["metadata"]["does_not_rank_candidates"] is True
    assert payload["metadata"]["does_not_score_edge"] is True
    assert payload["classified_candidates"][0]["is_order_action"] is False
    assert payload["classified_candidates"][0]["broker_api_called"] is False


def test_classification_groups_range_regime_without_scoring():
    report = classify_strategy_candidates(_normalized_report(regime=REGIME_RANGE_BOUND))

    candidate = report.get("sample_strategy:nifty:buy_call:range_bound")

    assert report.valid is True
    assert candidate.regime_class == REGIME_CLASS_RANGE
    assert candidate.direction_class == DIRECTION_CLASS_CALL_BIAS
    assert candidate.family_class == FAMILY_CLASS_VWAP
    assert "score" not in candidate.to_payload()
    assert "rank" not in candidate.to_payload()


def test_classification_warns_for_incomplete_evidence_without_blocking_metadata_row():
    normalized = _normalized_report(
        spec=_spec(required_evidence_keys=("market_state", "regime_state")),
    )

    report = classify_strategy_candidates(normalized)

    assert report.valid is True
    assert report.blocked_candidates == ()
    candidate = report.classified_candidates[0]
    assert candidate.evidence_class == EVIDENCE_CLASS_INCOMPLETE
    assert CLASSIFICATION_EVIDENCE_INCOMPLETE in candidate.warnings
    assert CLASSIFICATION_EVIDENCE_INCOMPLETE in report.warnings


def test_classification_blocks_empty_input():
    report = classify_strategy_candidates(())

    assert report.valid is False
    assert report.classified_candidates == ()
    assert report.blocked_candidates == ()
    assert report.blockers == (CLASSIFICATION_EMPTY_INPUT,)


def test_classification_blocks_invalid_normalization_report_fail_closed():
    invalid_normalized = normalize_strategy_candidates(())

    report = classify_strategy_candidates(invalid_normalized)

    assert invalid_normalized.valid is False
    assert report.valid is False
    assert report.classified_candidates == ()
    assert CLASSIFICATION_EMPTY_INPUT in report.blockers
    assert CLASSIFICATION_NORMALIZATION_INVALID in report.blockers


def test_classification_blocks_malformed_candidate_payload():
    report = classify_strategy_candidates(
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

    assert report.valid is True
    assert report.classified_candidates == ()
    assert report.blocked_candidates[0].canonical_candidate_id == "bad"
    assert report.blocked_candidates[0].blockers == (CLASSIFICATION_MISSING_FIELD,)


def test_classification_warns_for_unknown_metadata_classes():
    report = classify_strategy_candidates(
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

    candidate = report.classified_candidates[0]

    assert report.valid is True
    assert candidate.family_class == FAMILY_CLASS_UNKNOWN
    assert CLASSIFICATION_UNKNOWN_DIRECTION in candidate.warnings
    assert CLASSIFICATION_UNKNOWN_REGIME in candidate.warnings
    assert CLASSIFICATION_UNKNOWN_FAMILY in candidate.warnings


def test_classification_does_not_import_strategy_modules_or_run_callables():
    normalized = _normalized_report(spec=_spec(strategy_id="metadata_only_strategy"))

    report = classify_strategy_candidates(normalized)

    candidate = report.get("metadata_only_strategy:nifty:buy_call:bull_trend")
    assert candidate.valid is True
    assert candidate.is_order_action is False
    assert candidate.broker_api_called is False
    assert report.metadata["does_not_import_strategy_modules"] is True
    assert report.metadata["does_not_execute_strategy_callables"] is True
