import pytest

from core.candidate_classifier import classify_candidates
from core.candidate_pool import (
    build_candidate_lifecycle_snapshots,
    build_candidate_pool,
    candidate_pool_dedupe_key,
)
from core.candidate_ranking import rank_candidates
from core.hard_downgrade_engine import apply_hard_downgrades
from core.movement_contract import StrategyCandidate
from core.opportunity_scoring import score_opportunities


def _candidate(**overrides):
    payload = {
        "schema_version": 1,
        "strategy_id": "compression_strategy",
        "movement_type": "COMPRESSION_BREAKOUT",
        "symbol": "NIFTY",
        "direction": "BUY_CALL",
        "status": "VALIDATED_CANDIDATE",
        "raw_score": 0.72,
        "confidence_score": 0.70,
        "price_structure_score": 0.74,
        "option_confirmation_score": 0.68,
        "liquidity_score": 0.81,
        "freshness_score": 1.0,
        "volatility_score": 0.66,
        "regime_alignment_score": 0.77,
        "entry_trigger": "unit_test_trigger",
        "invalid_if": "unit_test_invalid",
        "rank_reason": "unit test candidate",
        "blockers": (),
        "warnings": (),
    }
    payload.update(overrides)
    return StrategyCandidate(**payload)


def test_candidate_pool_dedupes_by_symbol_direction_movement_and_strategy():
    first = _candidate()
    duplicate = _candidate(raw_score=0.6)
    other_direction = _candidate(direction="BUY_PUT")

    pool = build_candidate_pool([first, duplicate, other_direction])

    assert len(pool.candidates) == 2
    assert len(pool.duplicates_removed) == 1
    assert pool.duplicates_removed[0].raw_score == 0.6
    assert candidate_pool_dedupe_key(first) == (
        "NIFTY",
        "BUY_CALL",
        "COMPRESSION_BREAKOUT",
        "compression_strategy",
    )


def test_candidate_pool_summary_counts_statuses_blockers_and_warnings():
    validated = _candidate(strategy_id="compression", warnings=("NEAR_RESISTANCE",))
    blocked = _candidate(
        strategy_id="opening_drive",
        movement_type="OPENING_DRIVE",
        status="BLOCKED_CANDIDATE",
        blockers=("STALE_OPTION_LTP", "WIDE_SPREAD"),
        warnings=("LATE_ENTRY",),
        freshness_score=0.0,
        liquidity_score=0.2,
    )
    no_trade = _candidate(
        strategy_id="no_trade_chop",
        movement_type="NO_TRADE_CHOP",
        direction="NO_TRADE",
        status="NO_TRADE",
        raw_score=0.0,
        confidence_score=0.0,
        price_structure_score=0.0,
        option_confirmation_score=0.0,
        liquidity_score=0.0,
        freshness_score=0.0,
        volatility_score=0.0,
        regime_alignment_score=0.0,
        blockers=("NO_TRADE_CHOP",),
        rank_reason="chop suppressed candidates",
    )

    pool = build_candidate_pool([validated, blocked, no_trade])
    summary = pool.summary()

    assert summary.total_count == 3
    assert summary.validated_count == 1
    assert summary.blocked_count == 1
    assert summary.no_trade_count == 1
    assert summary.executable_eligible_count == 1
    assert summary.hard_blocked_count == 2
    assert summary.by_strategy == {
        "compression": 1,
        "no_trade_chop": 1,
        "opening_drive": 1,
    }
    assert summary.by_movement_type["COMPRESSION_BREAKOUT"] == 1
    assert summary.by_direction["BUY_CALL"] == 2
    assert summary.blocker_counts["STALE_OPTION_LTP"] == 1
    assert summary.blocker_counts["WIDE_SPREAD"] == 1
    assert summary.blocker_counts["NO_TRADE_CHOP"] == 1
    assert summary.warning_counts["NEAR_RESISTANCE"] == 1
    assert summary.warning_counts["LATE_ENTRY"] == 1

    as_dict = pool.to_dict()
    assert as_dict["summary"]["total_count"] == 3
    assert len(as_dict["candidates"]) == 3


def test_candidate_pool_exposes_filtered_candidate_groups():
    eligible = _candidate(strategy_id="eligible")
    hard_blocked = _candidate(
        strategy_id="blocked",
        blockers=("FALLBACK_QUOTE_ONLY",),
        freshness_score=0.2,
    )
    no_trade = _candidate(
        strategy_id="no_trade",
        movement_type="NO_TRADE_CHOP",
        direction="NO_TRADE",
        status="NO_TRADE",
        raw_score=0.0,
        confidence_score=0.0,
        price_structure_score=0.0,
        option_confirmation_score=0.0,
        liquidity_score=0.0,
        freshness_score=0.0,
        volatility_score=0.0,
        regime_alignment_score=0.0,
        blockers=("NO_TRADE_CHOP",),
    )

    pool = build_candidate_pool([eligible, hard_blocked, no_trade], dedupe=False)

    assert pool.executable_eligible_candidates() == (eligible,)
    assert pool.hard_blocked_candidates() == (hard_blocked, no_trade)
    assert pool.no_trade_candidates() == (no_trade,)


def test_candidate_pool_rejects_non_candidate_items():
    with pytest.raises(TypeError, match="candidate_pool_item_not_strategy_candidate"):
        build_candidate_pool([{"bad": "payload"}])  # type: ignore[list-item]


def test_lifecycle_snapshot_joins_classification_downgrade_score_and_rank():
    candidate = _candidate(
        strategy_id="clean_breakout",
        lineage={"candidate_id": "candidate-1", "candidate_intent_id": "intent-1"},
        evidence={"evidence_refs": ["evidence://cycle/1"]},
    )
    pool = build_candidate_pool([candidate])
    classifications = classify_candidates(pool.candidates)
    downgrades = apply_hard_downgrades(classifications)
    scores = score_opportunities(pool.candidates, downgrades)
    ranks = rank_candidates(scores)

    snapshots = pool.lifecycle_snapshots(
        classifications=classifications,
        downgrades=downgrades,
        scores=scores,
        ranks=ranks,
        selector_buckets={"clean_breakout": "EXECUTABLE"},
    )

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.candidate_id == "candidate-1"
    assert snapshot.source_intent_id == "intent-1"
    assert snapshot.lifecycle_state == "SELECTED"
    assert snapshot.capability == "EXECUTION_SAFE"
    assert snapshot.classification_bucket == "EXECUTABLE_CANDIDATE"
    assert snapshot.downgraded_bucket == "EXECUTABLE_CANDIDATE"
    assert snapshot.score_eligibility == "SCORE_ELIGIBLE"
    assert snapshot.final_score is not None
    assert snapshot.rank == 1
    assert snapshot.evidence_refs == ("evidence://cycle/1",)
    payload = snapshot.to_dict()
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False


def test_lifecycle_snapshot_blocks_fallback_from_execution_safe():
    fallback = _candidate(
        strategy_id="fallback_candidate",
        blockers=("FALLBACK_QUOTE_ONLY",),
        warnings=("fallback_quote_used",),
        freshness_score=0.1,
    )
    pool = build_candidate_pool([fallback])
    classifications = classify_candidates(pool.candidates)
    downgrades = apply_hard_downgrades(classifications)
    scores = score_opportunities(pool.candidates, downgrades)
    ranks = rank_candidates(scores)

    snapshot = pool.lifecycle_snapshots(
        classifications=classifications,
        downgrades=downgrades,
        scores=scores,
        ranks=ranks,
        selector_buckets={"fallback_candidate": "EXECUTABLE"},
    )[0]

    assert snapshot.lifecycle_state == "BLOCKED"
    assert snapshot.capability == "BLOCKED"
    assert snapshot.downgraded_bucket == "SUPPRESSED_CANDIDATE"
    assert "fallback_quote_data" in snapshot.downgrade_reasons
    assert "fallback_data" in snapshot.safety_flags
    assert snapshot.rank is not None


def test_lifecycle_snapshot_does_not_invent_downstream_truth_when_reports_missing():
    raw = _candidate(
        strategy_id="raw_candidate",
        status="RAW_CANDIDATE",
        lineage={},
        evidence={},
    )

    snapshot = build_candidate_lifecycle_snapshots([raw])[0]

    assert snapshot.lifecycle_state == "INTENT_CREATED"
    assert snapshot.capability == "DISPLAY_SAFE"
    assert snapshot.classification_bucket is None
    assert snapshot.downgraded_bucket is None
    assert snapshot.score_eligibility is None
    assert snapshot.final_score is None
    assert snapshot.rank is None
    assert snapshot.source_intent_id is None
