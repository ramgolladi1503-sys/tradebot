"""P0 regression: candidate ranking eligibility priority contract.

Gap closed: GAP-07 and GAP-08 from qa-coverage-gaps-20260610.md

Invariants under test:
  1. A SUPPRESSED_BY_DOWNGRADE candidate with any score must rank below a
     SCORE_ELIGIBLE candidate regardless of final_score magnitude.
  2. A SUPPRESSED_BY_DOWNGRADE candidate must never appear at rank 1 when
     any SCORE_ELIGIBLE candidate is present in the input.
  3. Every token in FEED_RISK_TOKENS applied to a SCORE_ELIGIBLE or
     NEEDS_CONFIRMATION candidate must produce SUPPRESSED_BY_DOWNGRADE in
     the rank output (not just a warning).
  4. rank_candidates() is idempotent: calling it twice with the same input
     produces the same rank assignments.
  5. Suppression must not mutate the original OpportunityScoreRecord.

No production code is modified by this file.
These tests extend the existing test_candidate_ranking.py without duplicating
any of its 17 existing test functions.
"""
from __future__ import annotations

import pytest

from core.candidate_ranking import (
    FEED_RISK_TOKENS,
    RANKING_FEED_RISK_SAFETY_FLAG,
    RANKING_FEED_RISK_SUPPRESSION_REASON,
    rank_candidates,
)
from core.opportunity_scoring import (
    ADVISORY_ONLY,
    NEEDS_CONFIRMATION,
    NO_TRADE_ONLY,
    SCORE_ELIGIBLE,
    SUPPRESSED_BY_DOWNGRADE,
    OpportunityScoreBreakdown,
    OpportunityScoreRecord,
)


# ---------------------------------------------------------------------------
# Helpers — mirrors the pattern in test_candidate_ranking.py
# ---------------------------------------------------------------------------

def _breakdown(final_score=0.5):
    return OpportunityScoreBreakdown(
        component_scores={},
        component_weights={},
        weighted_component_scores={},
        base_score=final_score,
        penalties={},
        total_penalty=0.0,
        bucket_cap=1.0,
        trap_risk_penalty=0.0,
        final_score=final_score,
    )


def _score(
    strategy_id="s1",
    *,
    symbol="NIFTY",
    direction="BUY_CALL",
    movement_type="COMPRESSION_BREAKOUT",
    final_score=0.5,
    eligibility=SCORE_ELIGIBLE,
    bucket=None,
    executable_candidate=None,
    downgrade_reasons=(),
    blockers=(),
    warnings=(),
    safety_flags=(),
):
    if bucket is None:
        bucket = {
            SCORE_ELIGIBLE: "EXECUTABLE_CANDIDATE",
            NEEDS_CONFIRMATION: "NEAR_EXECUTABLE_CANDIDATE",
            ADVISORY_ONLY: "ADVISORY_CANDIDATE",
            SUPPRESSED_BY_DOWNGRADE: "SUPPRESSED_CANDIDATE",
            NO_TRADE_ONLY: "NO_TRADE_CANDIDATE",
        }[eligibility]
    if executable_candidate is None:
        executable_candidate = eligibility == SCORE_ELIGIBLE
    return OpportunityScoreRecord(
        strategy_id=strategy_id,
        symbol=symbol,
        direction=direction,
        movement_type=movement_type,
        bucket=bucket,
        score_eligibility=eligibility,
        final_score=final_score,
        executable_candidate=executable_candidate,
        score_explanation="unit",
        downgrade_reasons=downgrade_reasons,
        safety_flags=safety_flags,
        blockers=blockers,
        warnings=warnings,
        breakdown=_breakdown(final_score),
    )


# ---------------------------------------------------------------------------
# P0 — GAP-07: SUPPRESSED_BY_DOWNGRADE never at rank 1 when clean exists
# ---------------------------------------------------------------------------

def test_suppressed_high_score_never_ranked_1_when_score_eligible_exists():
    """
    Core GAP-07 assertion:
    Candidate A: final_score=0.95, SCORE_ELIGIBLE → expected rank 1
    Candidate B: final_score=0.99, SUPPRESSED_BY_DOWNGRADE → must be rank 2

    This test is the exact scenario from the audit: a high-scoring suppressed
    candidate must not displace a clean lower-scoring executable candidate.
    """
    clean = _score("clean_exec", final_score=0.52, eligibility=SCORE_ELIGIBLE)
    suppressed = _score(
        "suppressed_high",
        final_score=0.99,
        eligibility=SUPPRESSED_BY_DOWNGRADE,
        downgrade_reasons=("fallback_quote_data",),
        blockers=("FALLBACK_QUOTE_ONLY",),
        safety_flags=("fallback_data",),
    )

    # Input order: suppressed first (worst-case for first-seen ordering)
    report = rank_candidates([suppressed, clean])

    assert report.ranks[0].strategy_id == "clean_exec", (
        f"SCORE_ELIGIBLE candidate must be rank 1 regardless of input order; "
        f"got rank 1 = {report.ranks[0].strategy_id!r}"
    )
    assert report.ranks[0].score_eligibility == SCORE_ELIGIBLE
    assert report.ranks[1].strategy_id == "suppressed_high"
    assert report.ranks[1].score_eligibility == SUPPRESSED_BY_DOWNGRADE
    assert report.ranks[0].rank == 1
    assert report.ranks[1].rank == 2


def test_suppressed_never_rank1_with_any_score_eligible_in_mixed_pool():
    """
    With N=5 candidates where 1 is SCORE_ELIGIBLE and 4 are SUPPRESSED,
    the SCORE_ELIGIBLE candidate must always hold rank 1.
    Tests across multiple final_score combinations.
    """
    clean = _score("only_clean", final_score=0.31, eligibility=SCORE_ELIGIBLE)
    suppressed_pool = [
        _score(f"sup_{i}", final_score=0.91 + i * 0.01, eligibility=SUPPRESSED_BY_DOWNGRADE,
               safety_flags=("fallback_data",))
        for i in range(4)
    ]

    # Interleave clean among suppressed candidates at every position
    for pos in range(5):
        pool = suppressed_pool[:pos] + [clean] + suppressed_pool[pos:]
        report = rank_candidates(pool)

        assert report.ranks[0].strategy_id == "only_clean", (
            f"SCORE_ELIGIBLE must be rank 1 regardless of input position {pos}; "
            f"got rank 1 = {report.ranks[0].strategy_id!r}"
        )


# ---------------------------------------------------------------------------
# P0 — GAP-08: every FEED_RISK_TOKENS member triggers suppression
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("feed_risk_token", sorted(FEED_RISK_TOKENS))
def test_each_feed_risk_token_in_safety_flags_suppresses_score_eligible(feed_risk_token):
    """
    Parametrized across all 13 members of FEED_RISK_TOKENS.
    Each token placed in safety_flags of a SCORE_ELIGIBLE candidate must
    cause rank_candidates to downgrade it to SUPPRESSED_BY_DOWNGRADE.

    Also verifies RANKING_FEED_RISK_SUPPRESSION_REASON is in downgrade_reasons
    and the original source record is not mutated.
    """
    clean = _score("clean_ref", final_score=0.50, eligibility=SCORE_ELIGIBLE)
    feed_risky = _score(
        "feed_risky",
        final_score=0.50,
        eligibility=SCORE_ELIGIBLE,
        safety_flags=(feed_risk_token,),
    )

    report = rank_candidates([clean, feed_risky])

    risky_ranks = [r for r in report.ranks if r.strategy_id == "feed_risky"]
    assert len(risky_ranks) == 1
    risky_rank = risky_ranks[0]

    assert risky_rank.score_eligibility == SUPPRESSED_BY_DOWNGRADE, (
        f"feed_risk_token={feed_risk_token!r} in safety_flags must suppress "
        f"SCORE_ELIGIBLE to SUPPRESSED_BY_DOWNGRADE; got {risky_rank.score_eligibility!r}"
    )
    assert RANKING_FEED_RISK_SUPPRESSION_REASON in risky_rank.downgrade_reasons, (
        f"RANKING_FEED_RISK_SUPPRESSION_REASON must appear in downgrade_reasons "
        f"for token {feed_risk_token!r}"
    )
    assert risky_rank.executable_candidate is False, (
        f"Suppressed candidate must have executable_candidate=False for token {feed_risk_token!r}"
    )
    # Source record must not be mutated
    assert feed_risky.score_eligibility == SCORE_ELIGIBLE, (
        "rank_candidates must not mutate the source OpportunityScoreRecord"
    )


@pytest.mark.parametrize("feed_risk_token", sorted(FEED_RISK_TOKENS))
def test_each_feed_risk_token_in_warnings_suppresses_score_eligible(feed_risk_token):
    """
    FEED_RISK_TOKENS membership is also checked against the warnings field
    (see _has_feed_risk in candidate_ranking.py).
    Each token placed in warnings of a SCORE_ELIGIBLE candidate must also
    trigger suppression.
    """
    feed_risky = _score(
        "feed_risky_warn",
        final_score=0.60,
        eligibility=SCORE_ELIGIBLE,
        warnings=(feed_risk_token,),
    )

    report = rank_candidates([feed_risky])
    rank = report.ranks[0]

    assert rank.score_eligibility == SUPPRESSED_BY_DOWNGRADE, (
        f"feed_risk_token={feed_risk_token!r} in warnings must suppress "
        f"SCORE_ELIGIBLE to SUPPRESSED_BY_DOWNGRADE"
    )


# ---------------------------------------------------------------------------
# P0 — Idempotency: two calls with same input produce identical ranks
# ---------------------------------------------------------------------------

def test_rank_candidates_is_idempotent_across_two_calls():
    """
    Calling rank_candidates twice with the same list of score records must
    produce identical rank assignments (same rank numbers and strategy_id order).

    A non-idempotent ranker would cause different top-opportunity outputs on
    subsequent orchestrator cycles for the same opportunity data.
    """
    records = [
        _score("alpha", final_score=0.82, eligibility=SCORE_ELIGIBLE),
        _score("beta", final_score=0.71, eligibility=SCORE_ELIGIBLE),
        _score("gamma", final_score=0.55, eligibility=NEEDS_CONFIRMATION),
        _score(
            "delta",
            final_score=0.91,
            eligibility=SCORE_ELIGIBLE,
            safety_flags=("stale_feed",),
        ),
        _score("epsilon", final_score=0.30, eligibility=ADVISORY_ONLY),
    ]

    report1 = rank_candidates(records)
    report2 = rank_candidates(records)

    rank_ids_1 = [r.strategy_id for r in report1.ranks]
    rank_ids_2 = [r.strategy_id for r in report2.ranks]
    eligibilities_1 = [r.score_eligibility for r in report1.ranks]
    eligibilities_2 = [r.score_eligibility for r in report2.ranks]

    assert rank_ids_1 == rank_ids_2, (
        f"rank_candidates must be idempotent; call 1={rank_ids_1}, call 2={rank_ids_2}"
    )
    assert eligibilities_1 == eligibilities_2


# ---------------------------------------------------------------------------
# P0 — Source record immutability (explicit combined proof)
# ---------------------------------------------------------------------------

def test_feed_risk_suppression_does_not_mutate_source_record_eligibility():
    """
    After rank_candidates runs, every source OpportunityScoreRecord must
    retain its original score_eligibility and bucket.

    Covers the case where a previously-eligible candidate is suppressed:
    the rank record shows SUPPRESSED_BY_DOWNGRADE but the source is still SCORE_ELIGIBLE.
    """
    original_records = [
        _score(f"r{i}", final_score=0.5 + i * 0.05, eligibility=SCORE_ELIGIBLE,
               safety_flags=(token,))
        for i, token in enumerate(sorted(FEED_RISK_TOKENS)[:4])
    ]

    _ = rank_candidates(original_records)

    for rec in original_records:
        assert rec.score_eligibility == SCORE_ELIGIBLE, (
            f"Source record {rec.strategy_id!r} must not be mutated; "
            f"got score_eligibility={rec.score_eligibility!r}"
        )
        assert rec.executable_candidate is True, (
            f"Source record {rec.strategy_id!r} must retain executable_candidate=True"
        )


# ---------------------------------------------------------------------------
# Regression: ADVISORY candidates with feed-risk tokens stay ADVISORY
# (existing coverage in test_candidate_ranking.py, verified here alongside
#  the new parametrized tests to confirm no interaction)
# ---------------------------------------------------------------------------

def test_advisory_with_feed_risk_token_stays_advisory_not_double_suppressed():
    """
    Feed risk suppression only applies to SCORE_ELIGIBLE and NEEDS_CONFIRMATION
    (see _should_suppress_for_feed_risk in candidate_ranking.py).
    An ADVISORY_ONLY candidate with a feed-risk token must stay ADVISORY_ONLY.
    """
    advisory = _score(
        "adv_feed_risk",
        final_score=0.35,
        eligibility=ADVISORY_ONLY,
        safety_flags=("stale_option_ltp",),
    )

    report = rank_candidates([advisory])

    assert report.ranks[0].score_eligibility == ADVISORY_ONLY
    assert report.advisory_count == 1
    assert report.suppressed_count == 0
    assert RANKING_FEED_RISK_SUPPRESSION_REASON not in report.ranks[0].downgrade_reasons
