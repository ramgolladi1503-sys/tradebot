"""EDGE-79 strategy conflict and consensus tests.

Safety marker: stale_feed_blocks_order_intent.
"""

from __future__ import annotations

from core.candidate_intent import INTENT_TYPE_ENTRY, INTENT_TYPE_NO_TRADE, create_candidate_intent
from core.strategy_conflict_consensus import (
    CONSENSUS_CANDIDATE_NOT_POOL_ELIGIBLE,
    CONSENSUS_DIRECTION_CONFLICT,
    CONSENSUS_EMPTY_CANDIDATES,
    CONSENSUS_FAMILY_CONFLICT,
    CONSENSUS_NO_ELIGIBLE_ENTRY,
    CONSENSUS_NON_ENTRY_INTENT,
    CONSENSUS_STATUS_BLOCKED,
    CONSENSUS_STATUS_READY,
    CONSENSUS_UNSUPPORTED_DIRECTION,
    build_strategy_conflict_consensus,
)


def _candidate(
    *,
    candidate_id: str,
    family: str,
    direction: str = "BUY_CALL",
    instrument: str = "NIFTY",
    intent_type: str = INTENT_TYPE_ENTRY,
    blockers=(),
):
    return create_candidate_intent(
        candidate_intent_id=candidate_id,
        strategy_id=f"{family}_v1",
        instrument=instrument,
        direction=direction,
        regime="TREND",
        family=family,
        intent_type=intent_type,
        trigger="test_trigger",
        invalidation="test_invalidation",
        required_evidence_keys=("market_state", "feed_health_truth"),
        blockers=blockers,
    )


def test_ready_consensus_for_same_instrument_same_direction_different_families():
    report = build_strategy_conflict_consensus(
        (
            _candidate(candidate_id="breakout-1", family="breakout", direction="BUY_CALL"),
            _candidate(candidate_id="vwap-1", family="vwap", direction="CALL"),
        )
    )
    payload = report.to_payload()

    assert report.consensus_ready is True
    assert payload["ready_count"] == 1
    decision = report.ready_decisions[0]
    assert decision.status == CONSENSUS_STATUS_READY
    assert decision.direction_group == "CALL"
    assert decision.candidate_intent_ids == ("breakout_1", "vwap_1")
    assert decision.family_ids == ("breakout", "vwap")
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False


def test_blocks_opposing_direction_groups_for_same_instrument():
    report = build_strategy_conflict_consensus(
        (
            _candidate(candidate_id="breakout-1", family="breakout", direction="BUY_CALL"),
            _candidate(candidate_id="mean-1", family="mean_reversion", direction="BUY_PUT"),
        )
    )

    assert report.consensus_ready is False
    assert CONSENSUS_NO_ELIGIBLE_ENTRY in report.blockers
    decision = report.blocked_decisions[0]
    assert decision.status == CONSENSUS_STATUS_BLOCKED
    assert decision.direction_group == "CONFLICT"
    assert CONSENSUS_DIRECTION_CONFLICT in decision.blockers
    assert set(decision.candidate_intent_ids) == {"breakout_1", "mean_1"}


def test_allows_separate_instruments_without_cross_instrument_conflict():
    report = build_strategy_conflict_consensus(
        (
            _candidate(candidate_id="nifty-call", family="breakout", direction="BUY_CALL", instrument="NIFTY"),
            _candidate(candidate_id="bank-put", family="vwap", direction="BUY_PUT", instrument="BANKNIFTY"),
        )
    )

    assert report.consensus_ready is True
    assert len(report.ready_decisions) == 2
    assert {decision.instrument for decision in report.ready_decisions} == {"NIFTY", "BANKNIFTY"}


def test_blocks_duplicate_family_same_direction_same_instrument():
    report = build_strategy_conflict_consensus(
        (
            _candidate(candidate_id="breakout-1", family="breakout", direction="BUY_CALL"),
            _candidate(candidate_id="breakout-2", family="breakout", direction="CALL"),
        )
    )

    assert report.consensus_ready is False
    decision = report.blocked_decisions[0]
    assert CONSENSUS_FAMILY_CONFLICT in decision.blockers
    assert decision.metadata["duplicate_families"] == ("breakout",)


def test_blocks_pool_ineligible_candidates_with_original_blockers():
    report = build_strategy_conflict_consensus(
        (
            _candidate(
                candidate_id="blocked-1",
                family="breakout",
                direction="BUY_CALL",
                blockers=("risk_guard_blocked",),
            ),
        )
    )

    assert report.consensus_ready is False
    decision = report.blocked_decisions[0]
    assert CONSENSUS_CANDIDATE_NOT_POOL_ELIGIBLE in decision.blockers
    assert "risk_guard_blocked" in decision.blockers


def test_blocks_non_entry_intent_even_when_pool_eligible():
    report = build_strategy_conflict_consensus(
        (
            _candidate(
                candidate_id="observe-1",
                family="breakout",
                direction="NO_TRADE",
                intent_type=INTENT_TYPE_NO_TRADE,
            ),
        )
    )

    assert report.consensus_ready is False
    decision = report.blocked_decisions[0]
    assert CONSENSUS_NON_ENTRY_INTENT in decision.blockers
    assert CONSENSUS_UNSUPPORTED_DIRECTION in decision.blockers


def test_blocks_empty_input():
    report = build_strategy_conflict_consensus(())

    assert report.consensus_ready is False
    assert CONSENSUS_EMPTY_CANDIDATES in report.blockers
    assert CONSENSUS_NO_ELIGIBLE_ENTRY in report.blockers
    assert report.ready_decisions == ()
    assert report.blocked_decisions == ()


def test_report_preserves_pool_report_payload():
    candidate = _candidate(candidate_id="breakout-1", family="breakout", direction="BUY_CALL")
    report = build_strategy_conflict_consensus((candidate,))
    payload = report.to_payload()

    assert payload["pool_report"]["pool_ready"] is True
    assert payload["pool_report"]["eligible_candidate_intent_ids"] == ["breakout_1"]
    assert payload["metadata"]["does_not_rank_candidates"] is True
    assert payload["metadata"]["does_not_score_edge"] is True
    assert payload["metadata"]["does_not_touch_runtime"] is True
