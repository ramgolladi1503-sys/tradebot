from __future__ import annotations

import json

from core.regime_state import REGIME_BULL_TREND
from core.strategy_candidate_normalization import (
    NORMALIZATION_DUPLICATE_CANDIDATE,
    NORMALIZATION_EMPTY_INPUT,
    NORMALIZATION_INVALID_CANDIDATE,
    NORMALIZATION_MISSING_FIELD,
    NORMALIZATION_POOL_INVALID,
    NORMALIZATION_STATUS_DUPLICATE_REJECTED,
    STRATEGY_CANDIDATE_NORMALIZATION_SOURCE,
    normalize_strategy_candidates,
)
from core.strategy_candidate_pool import build_strategy_candidate_pool
from core.strategy_spec import DIRECTION_BUY_CALL, FAMILY_VWAP, StrategySpec


def _spec(strategy_id="sample_strategy", instruments=("NIFTY",)):
    return StrategySpec(
        strategy_id=strategy_id,
        name="Sample Strategy",
        family=FAMILY_VWAP,
        module_path="strategies.sample",
        callable_name="generate_signal",
        instruments=instruments,
        declared_regimes=(REGIME_BULL_TREND,),
        blocked_regimes=("UNKNOWN", "OUT_OF_SESSION", "LIQUIDITY_STRESSED", "VOLATILITY_STRESSED"),
        required_market_state_dimensions=("trend", "volatility", "breadth", "liquidity", "session"),
        required_evidence_keys=("market_state", "regime_state", "feed_health_truth", "quote_truth"),
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


def _pool(*, instruments=("BANKNIFTY", "NIFTY"), strategy_id="sample_strategy"):
    return build_strategy_candidate_pool(
        regime=REGIME_BULL_TREND,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[_spec(strategy_id=strategy_id, instruments=instruments)],
    )


def test_normalization_keeps_deterministic_canonical_ids_from_edge_69_pool():
    report = normalize_strategy_candidates(_pool())

    assert report.valid is True
    assert report.blockers == ()
    assert report.rejected_candidates == ()
    assert report.canonical_candidate_ids == (
        "sample_strategy:banknifty:buy_call:bull_trend",
        "sample_strategy:nifty:buy_call:bull_trend",
    )
    assert report.get("sample-strategy:nifty:buy-call:bull-trend").strategy_id == "sample_strategy"
    assert report.normalized_candidates[0].metadata["normalization_key_fields"] == [
        "strategy_id",
        "instrument",
        "direction",
        "regime",
    ]


def test_normalization_payload_is_read_only_non_action_and_not_ranked_or_scored():
    report = normalize_strategy_candidates(_pool(instruments=("NIFTY",)))
    payload = json.loads(report.to_json())

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["source"] == STRATEGY_CANDIDATE_NORMALIZATION_SOURCE
    assert payload["metadata"]["does_not_import_strategy_modules"] is True
    assert payload["metadata"]["does_not_execute_strategy_callables"] is True
    assert payload["metadata"]["does_not_rank_candidates"] is True
    assert payload["metadata"]["does_not_score_edge"] is True
    assert payload["normalized_candidates"][0]["is_order_action"] is False
    assert payload["normalized_candidates"][0]["broker_api_called"] is False


def test_normalization_rejects_duplicate_candidates_without_mutating_first_candidate():
    pool = _pool(instruments=("NIFTY",))
    candidate = pool.candidates[0]

    report = normalize_strategy_candidates((candidate, candidate))
    payload = report.to_payload()

    assert report.valid is True
    assert payload["rejected_count"] == 1
    assert report.canonical_candidate_ids == ("sample_strategy:nifty:buy_call:bull_trend",)
    assert report.rejected_candidates[0].status == NORMALIZATION_STATUS_DUPLICATE_REJECTED
    assert report.rejected_candidates[0].canonical_candidate_id == "sample_strategy:nifty:buy_call:bull_trend"
    assert report.rejected_candidates[0].blockers == (NORMALIZATION_DUPLICATE_CANDIDATE,)
    assert NORMALIZATION_DUPLICATE_CANDIDATE in report.warnings


def test_normalization_rejects_dict_duplicate_after_case_and_spacing_normalization():
    pool = _pool(instruments=("NIFTY",))
    candidate = pool.candidates[0]
    duplicate_payload = candidate.to_payload()
    duplicate_payload.update(
        {
            "candidate_id": " Sample Strategy : Nifty : Buy Call : Bull Trend ",
            "strategy_id": " Sample-Strategy ",
            "instrument": " nifty ",
            "direction": " buy call ",
            "regime": " bull trend ",
        }
    )

    report = normalize_strategy_candidates((candidate, duplicate_payload))
    payload = report.to_payload()

    assert report.canonical_candidate_ids == ("sample_strategy:nifty:buy_call:bull_trend",)
    assert payload["rejected_count"] == 1
    assert report.rejected_candidates[0].blockers == (NORMALIZATION_DUPLICATE_CANDIDATE,)


def test_normalization_rejects_malformed_candidate_payloads():
    report = normalize_strategy_candidates(
        (
            {
                "candidate_id": "bad",
                "strategy_id": "",
                "instrument": "NIFTY",
                "direction": "BUY_CALL",
                "regime": "BULL_TREND",
                "family": "VWAP",
                "module_path": "strategies.sample",
                "callable_name": "generate_signal",
                "eligibility_status": "ELIGIBLE",
                "required_evidence_keys": (),
            },
        )
    )

    assert report.valid is True
    assert report.normalized_candidates == ()
    assert report.rejected_candidates[0].candidate_id == "bad"
    assert NORMALIZATION_MISSING_FIELD in report.rejected_candidates[0].blockers
    assert NORMALIZATION_INVALID_CANDIDATE in report.rejected_candidates[0].blockers
    assert NORMALIZATION_INVALID_CANDIDATE in report.warnings


def test_normalization_blocks_empty_input():
    report = normalize_strategy_candidates(())

    assert report.valid is False
    assert report.normalized_candidates == ()
    assert report.rejected_candidates == ()
    assert report.blockers == (NORMALIZATION_EMPTY_INPUT,)


def test_normalization_blocks_invalid_pool_report_fail_closed():
    invalid_pool = build_strategy_candidate_pool(
        regime="",
        direction="",
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[_spec()],
    )

    report = normalize_strategy_candidates(invalid_pool)

    assert invalid_pool.valid is False
    assert report.valid is False
    assert report.normalized_candidates == ()
    assert NORMALIZATION_POOL_INVALID in report.blockers


def test_normalization_does_not_import_strategy_modules_or_run_callables():
    pool = _pool(instruments=("NIFTY",), strategy_id="metadata_only_strategy")

    report = normalize_strategy_candidates(pool)

    assert report.valid is True
    candidate = report.get("metadata_only_strategy:nifty:buy_call:bull_trend")
    assert candidate.module_path == "strategies.sample"
    assert candidate.callable_name == "generate_signal"
    assert candidate.is_order_action is False
    assert candidate.broker_api_called is False
