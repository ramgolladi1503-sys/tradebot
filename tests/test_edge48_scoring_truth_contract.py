from __future__ import annotations

from core.scoring_truth_contract import (
    ADVISORY_SCORE_CAP,
    DEBUG_ONLY_SCORE_CAP,
    HARD_REJECT_SCORE_CAP,
    RANKABLE_SCORE_CAP,
    SOFT_REJECT_SCORE_CAP,
    harden_scoring_truth,
)


def test_hard_reject_zeroes_high_score():
    decision = harden_scoring_truth(
        {
            "candidate_id": "EDGE48-HARD",
            "candidate_state": "executable",
            "execution_allowed": True,
            "reasons": ["stale_quote"],
        },
        {"final_score": 0.97},
    )

    assert decision.raw_score == 0.97
    assert decision.truth_score == HARD_REJECT_SCORE_CAP
    assert decision.score_cap == HARD_REJECT_SCORE_CAP
    assert decision.score_allowed_for_ranking is False
    assert decision.score_allowed_for_execution is False
    assert decision.score_rejected is True
    assert "hard_reject_zero_score" in decision.reasons
    assert decision.context["is_order_action"] is False
    assert decision.context["broker_api_called"] is False


def test_debug_only_zeroes_score_even_when_price_is_feasible():
    decision = harden_scoring_truth(
        {
            "candidate_id": "EDGE48-DEBUG",
            "debug_candidate": True,
            "execution_entry_status": "executable",
        },
        {"final_score": 0.88},
    )

    assert decision.truth_score == DEBUG_ONLY_SCORE_CAP
    assert decision.score_allowed_for_ranking is False
    assert decision.score_allowed_for_execution is False
    assert decision.score_rejected is True


def test_advisory_score_is_capped_below_rankable():
    decision = harden_scoring_truth(
        {
            "candidate_id": "EDGE48-ADVISORY",
            "advisory_only": True,
            "execution_entry_status": "executable",
        },
        {"final_score": 0.92},
    )

    assert decision.truth_score == ADVISORY_SCORE_CAP
    assert decision.score_allowed_for_ranking is False
    assert decision.score_allowed_for_execution is False
    assert "advisory_score_cap" in decision.reasons


def test_rankable_candidate_without_price_truth_is_soft_capped_not_rankable():
    decision = harden_scoring_truth(
        {
            "candidate_id": "EDGE48-RANKABLE-NOPRICE",
            "rankable": True,
        },
        {"final_score": 0.91},
    )

    assert decision.score_cap == SOFT_REJECT_SCORE_CAP
    assert decision.truth_score == SOFT_REJECT_SCORE_CAP
    assert decision.score_allowed_for_ranking is False
    assert decision.score_allowed_for_execution is False
    assert "price_not_score_trusted" in decision.reasons


def test_rankable_candidate_with_price_truth_is_capped_to_rankable_ceiling():
    decision = harden_scoring_truth(
        {
            "candidate_id": "EDGE48-RANKABLE",
            "rankable": True,
            "entry_price": 101.5,
        },
        {"final_score": 0.99},
    )

    assert decision.score_cap == RANKABLE_SCORE_CAP
    assert decision.truth_score == RANKABLE_SCORE_CAP
    assert decision.score_allowed_for_ranking is True
    assert decision.score_allowed_for_execution is False


def test_executable_requires_execution_permission_for_execution_allowed_flag():
    decision = harden_scoring_truth(
        {
            "candidate_id": "EDGE48-EXEC-NO-PERMISSION",
            "candidate_class": "executable",
            "entry_price": 101.5,
            "execution_allowed": False,
        },
        {"final_score": 0.82},
    )

    assert decision.truth_score == 0.82
    assert decision.score_allowed_for_ranking is True
    assert decision.score_allowed_for_execution is False
    assert "execution_permission_not_granted" in decision.reasons


def test_executable_with_permission_can_remain_execution_allowed():
    decision = harden_scoring_truth(
        {
            "candidate_id": "EDGE48-EXEC",
            "candidate_class": "executable",
            "entry_price": 101.5,
            "execution_allowed": True,
        },
        {"final_score": 0.82},
    )

    assert decision.truth_score == 0.82
    assert decision.score_allowed_for_ranking is True
    assert decision.score_allowed_for_execution is True
    assert decision.score_rejected is False
