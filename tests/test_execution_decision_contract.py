from __future__ import annotations

from copy import deepcopy

import pytest

from core.execution_decision_contract import ExecutionState, infer_execution_decision


def _executable_candidate(**updates):
    candidate = {
        "trade_id": "NIFTY-EXEC-1",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "execution_entry": 121.5,
        "execution_entry_status": "executable",
        "execution_status": "executable",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
        "quote_source": "live",
        "option_ltp_source": "live",
        "quote_validation_status": "OK",
        "blockers": [],
        "hard_blockers": [],
        "source_flags": {},
    }
    candidate.update(updates)
    return candidate


def test_complete_consistent_candidate_is_executable():
    decision = infer_execution_decision(_executable_candidate())
    assert decision.state is ExecutionState.EXECUTABLE
    assert decision.allowed is True
    assert decision.blockers == ()
    assert decision.legacy_conflicts == ()


@pytest.mark.parametrize("quote_source", ["rest_fallback", "REST_RECOVERY", "subscription_failed"])
def test_fallback_quote_sources_are_never_executable(quote_source):
    decision = infer_execution_decision(
        _executable_candidate(quote_source=quote_source, option_ltp_source=quote_source)
    )
    assert decision.allowed is False
    assert decision.state is not ExecutionState.EXECUTABLE
    assert "fallback_quote_source" in decision.blockers


@pytest.mark.parametrize(
    "quote_status",
    ["STALE_OPTION_LTP", "PRICE_MISMATCH", "UNTRUSTED", "SUBSCRIPTION_FAILED"],
)
def test_invalid_quote_truth_is_never_executable(quote_status):
    decision = infer_execution_decision(
        _executable_candidate(quote_validation_status=quote_status)
    )
    assert decision.allowed is False
    assert quote_status.lower() in decision.blockers


def test_recovered_fallback_row_is_advisory_only_even_with_execute_fields():
    decision = infer_execution_decision(
        _executable_candidate(
            row_kind="recovered_fallback",
            source_flags={"candidate_origin": "fallback", "recovered_fallback": True},
        )
    )
    assert decision.state is ExecutionState.ADVISORY_ONLY
    assert decision.allowed is False
    assert "synthetic_or_fallback_candidate" in decision.blockers


def test_soft_reject_trade_id_is_advisory_only():
    decision = infer_execution_decision(_executable_candidate(trade_id="softrej_nifty_1"))
    assert decision.state is ExecutionState.ADVISORY_ONLY
    assert decision.allowed is False


def test_execution_allowed_without_entry_is_blocked_and_conflicted():
    decision = infer_execution_decision(
        _executable_candidate(execution_entry=None)
    )
    assert decision.state is ExecutionState.BLOCKED
    assert decision.allowed is False
    assert "execution_allowed_without_execution_entry" in decision.legacy_conflicts


def test_positive_and_negative_legacy_signals_are_reported():
    decision = infer_execution_decision(
        _executable_candidate(permission="ADVISORY_ONLY", final_action="QUEUE_ONLY")
    )
    assert decision.allowed is False
    assert decision.state is ExecutionState.ADVISORY_ONLY
    assert "positive_and_negative_legacy_execution_signals" in decision.legacy_conflicts


def test_hard_blocker_overrides_all_positive_execution_fields():
    decision = infer_execution_decision(
        _executable_candidate(hard_blockers=["daily_loss_limit"])
    )
    assert decision.allowed is False
    assert decision.state is ExecutionState.BLOCKED
    assert decision.primary_reason == "daily_loss_limit"
    assert "blocked_candidate_has_positive_execution_signals" in decision.legacy_conflicts


def test_inference_is_pure_and_does_not_mutate_candidate():
    candidate = _executable_candidate(
        source_flags={"quote_source": "live"},
        blockers=[],
    )
    original = deepcopy(candidate)
    first = infer_execution_decision(candidate)
    second = infer_execution_decision(candidate)
    assert candidate == original
    assert first == second


def test_object_candidates_are_supported():
    class Candidate:
        pass

    candidate = Candidate()
    for key, value in _executable_candidate().items():
        setattr(candidate, key, value)
    decision = infer_execution_decision(candidate)
    assert decision.allowed is True
