from __future__ import annotations

from core.candidate_state_contract import (
    ADVISORY_STATE,
    DEBUG_ONLY_STATE,
    EXECUTABLE_STATE,
    HARD_REJECT_STATE,
    RANKABLE_STATE,
    SOFT_REJECT_STATE,
    classify_candidate_state,
)


def test_hard_reject_wins_over_executable_and_rankable_markers():
    decision = classify_candidate_state(
        {
            "execution_allowed": True,
            "rankable": True,
            "reasons": ["stale_option_ltp"],
        }
    )

    assert decision.state == HARD_REJECT_STATE
    assert decision.is_hard_reject is True
    assert decision.is_executable is False
    assert "stale_option_ltp" in decision.reasons
    assert decision.context["is_order_action"] is False
    assert decision.context["broker_api_called"] is False


def test_soft_reject_separates_no_signal_from_hard_reject():
    decision = classify_candidate_state({"reason_code": "no_signal"})

    assert decision.state == SOFT_REJECT_STATE
    assert decision.is_soft_reject is True
    assert decision.is_hard_reject is False
    assert decision.reasons == ("no_signal",)


def test_soft_reject_separates_no_candidates_survived():
    decision = classify_candidate_state({"status": "no_candidates_survived"})

    assert decision.state == SOFT_REJECT_STATE
    assert decision.is_soft_reject is True
    assert "no_candidates_survived" in decision.reasons


def test_advisory_only_is_not_rankable_or_executable():
    decision = classify_candidate_state(
        {
            "advisory_only": True,
            "rankable": True,
            "source_flags": {"execution_block_type": "advisory"},
        }
    )

    assert decision.state == ADVISORY_STATE
    assert decision.is_advisory is True
    assert decision.is_rankable is False
    assert decision.is_executable is False
    assert "advisory_only" in decision.reasons


def test_debug_only_is_separate_from_advisory():
    decision = classify_candidate_state(
        {
            "debug_candidate": True,
            "advisory_only": True,
        }
    )

    assert decision.state == DEBUG_ONLY_STATE
    assert decision.is_debug_only is True
    assert decision.is_advisory is False
    assert "debug_candidate" in decision.reasons


def test_rankable_is_separate_from_executable():
    decision = classify_candidate_state({"rankable": True})

    assert decision.state == RANKABLE_STATE
    assert decision.is_rankable is True
    assert decision.is_executable is False
    assert decision.reasons == ("rankable",)


def test_executable_requires_explicit_executable_marker():
    decision = classify_candidate_state(
        {
            "candidate_class": "EXECUTABLE",
            "execution_entry_status": "executable",
        }
    )

    assert decision.state == EXECUTABLE_STATE
    assert decision.is_executable is True
    assert decision.is_rankable is False
    assert "candidate_class:executable" in decision.reasons


def test_unclassified_candidate_fails_to_soft_reject():
    decision = classify_candidate_state({"symbol": "NIFTY"})

    assert decision.state == SOFT_REJECT_STATE
    assert decision.is_soft_reject is True
    assert decision.reasons == ("unclassified_candidate_state",)
