from __future__ import annotations

import json

from core.candidate_hard_downgrade import (
    DOWNGRADE_DECISION_ADVISORY_ONLY,
    DOWNGRADE_DECISION_BLOCKED,
    DOWNGRADE_DECISION_CANDIDATE_READY,
    HARD_DOWNGRADE_EVIDENCE_INCOMPLETE,
    apply_candidate_hard_downgrades,
)
from core.candidate_readiness_summary import (
    CANDIDATE_READINESS_SUMMARY_SOURCE,
    READINESS_STATE_ADVISORY_ONLY,
    READINESS_STATE_BLOCKED,
    READINESS_STATE_INVALID,
    READINESS_STATE_READY,
    READINESS_SUMMARY_DOWNGRADE_INVALID,
    READINESS_SUMMARY_EMPTY_INPUT,
    READINESS_SUMMARY_MALFORMED_DECISION,
    READINESS_SUMMARY_UNKNOWN_DECISION,
    summarize_candidate_readiness,
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


def _downgrade_report(*, spec=None, instruments=("NIFTY",)):
    pool = build_strategy_candidate_pool(
        regime=REGIME_BULL_TREND,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[spec or _spec(instruments=instruments)],
    )
    normalized = normalize_strategy_candidates(pool)
    classified = classify_strategy_candidates(normalized)
    return apply_candidate_hard_downgrades(classified)


def test_readiness_summary_counts_ready_candidates_from_real_flow():
    downgrade = _downgrade_report(instruments=("BANKNIFTY", "NIFTY"))

    summary = summarize_candidate_readiness(downgrade)

    assert summary.valid is True
    assert summary.readiness_state == READINESS_STATE_READY
    assert summary.total_count == 2
    assert summary.ready_count == 2
    assert summary.advisory_only_count == 0
    assert summary.blocked_count == 0
    assert summary.invalid_count == 0
    assert summary.has_ready_candidates is True
    assert summary.has_only_advisory_candidates is False
    assert summary.candidate_ready_ids == (
        "sample_strategy:banknifty:buy_call:bull_trend",
        "sample_strategy:nifty:buy_call:bull_trend",
    )
    assert summary.reason_counts == {}


def test_readiness_summary_payload_is_read_only_non_action_and_not_ranked_or_scored():
    summary = summarize_candidate_readiness(_downgrade_report())
    payload = json.loads(summary.to_json())

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["source"] == CANDIDATE_READINESS_SUMMARY_SOURCE
    assert payload["metadata"]["does_not_import_strategy_modules"] is True
    assert payload["metadata"]["does_not_execute_strategy_callables"] is True
    assert payload["metadata"]["does_not_rank_candidates"] is True
    assert payload["metadata"]["does_not_score_edge"] is True
    assert payload["metadata"]["does_not_select_candidates"] is True
    assert payload["metadata"]["does_not_allocate_capital"] is True
    assert "score" not in payload
    assert "rank" not in payload
    assert "selected_candidate_id" not in payload


def test_readiness_summary_counts_advisory_only_candidates_and_reasons():
    downgrade = _downgrade_report(
        spec=_spec(required_evidence_keys=("market_state", "regime_state")),
    )

    summary = summarize_candidate_readiness(downgrade)

    assert summary.valid is True
    assert summary.readiness_state == READINESS_STATE_ADVISORY_ONLY
    assert summary.ready_count == 0
    assert summary.advisory_only_count == 1
    assert summary.blocked_count == 0
    assert summary.has_ready_candidates is False
    assert summary.has_only_advisory_candidates is True
    assert summary.advisory_only_ids == ("sample_strategy:nifty:buy_call:bull_trend",)
    assert summary.reason_counts[HARD_DOWNGRADE_EVIDENCE_INCOMPLETE] == 1


def test_readiness_summary_counts_blocked_decisions():
    downgrade = apply_candidate_hard_downgrades(
        classify_strategy_candidates(
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
    )

    summary = summarize_candidate_readiness(downgrade)

    assert summary.valid is True
    assert summary.readiness_state == READINESS_STATE_BLOCKED
    assert summary.ready_count == 0
    assert summary.advisory_only_count == 0
    assert summary.blocked_count == 1
    assert summary.blocked_ids == ("bad",)
    assert DOWNGRADE_DECISION_BLOCKED not in summary.reason_counts


def test_readiness_summary_fails_closed_on_empty_input():
    summary = summarize_candidate_readiness(())

    assert summary.valid is False
    assert summary.readiness_state == READINESS_STATE_INVALID
    assert summary.total_count == 0
    assert summary.blockers == (READINESS_SUMMARY_EMPTY_INPUT,)


def test_readiness_summary_fails_closed_on_invalid_downgrade_report():
    invalid_downgrade = apply_candidate_hard_downgrades(classify_strategy_candidates(()))

    summary = summarize_candidate_readiness(invalid_downgrade)

    assert invalid_downgrade.valid is False
    assert summary.valid is False
    assert summary.readiness_state == READINESS_STATE_INVALID
    assert READINESS_SUMMARY_DOWNGRADE_INVALID in summary.blockers
    assert any(blocker.startswith("downgrade:") for blocker in summary.blockers)


def test_readiness_summary_blocks_malformed_decision_payloads():
    summary = summarize_candidate_readiness((object(),))

    assert summary.valid is False
    assert summary.readiness_state == READINESS_STATE_INVALID
    assert READINESS_SUMMARY_MALFORMED_DECISION in summary.blockers
    assert summary.blocked_count == 1


def test_readiness_summary_warns_for_unknown_decision_without_promoting_ready():
    summary = summarize_candidate_readiness(
        (
            {
                "canonical_candidate_id": "sample:unknown:nifty",
                "strategy_id": "sample",
                "decision": "MAYBE",
                "reasons": ("manual_review",),
            },
        )
    )

    assert summary.valid is True
    assert summary.ready_count == 0
    assert summary.advisory_only_count == 0
    assert summary.blocked_count == 0
    assert summary.invalid_count == 1
    assert READINESS_SUMMARY_UNKNOWN_DECISION in summary.warnings
    assert summary.readiness_state == READINESS_STATE_BLOCKED


def test_readiness_summary_does_not_import_strategy_modules_or_run_callables():
    downgrade = _downgrade_report(spec=_spec(strategy_id="metadata_only_strategy"))

    summary = summarize_candidate_readiness(downgrade)

    assert summary.ready_count == 1
    assert summary.is_order_action is False
    assert summary.broker_api_called is False
    assert summary.metadata["does_not_import_strategy_modules"] is True
    assert summary.metadata["does_not_execute_strategy_callables"] is True
