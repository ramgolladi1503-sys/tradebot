from types import SimpleNamespace

import core.canonical_execution_decision as contract
from core.canonical_execution_decision import ExecutionState


def _truth(*, allowed: bool, reasons=(), reason_code="ok"):
    return SimpleNamespace(
        execution_allowed=allowed,
        reasons=tuple(reasons),
        reason_code=reason_code,
        context={"source": "unit"},
    )


def _candidate(**updates):
    row = {
        "execution_allowed": True,
        "eligible_for_execution": True,
        "tradable": True,
        "execution_entry": 101.5,
        "execution_entry_status": "executable",
        "execution_status": "executable",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
        "candidate_status": "ranked",
        "hard_blockers": [],
        "blockers": [],
    }
    row.update(updates)
    return row


def test_complete_candidate_becomes_executable(monkeypatch):
    monkeypatch.setattr(
        contract,
        "classify_executable_truth",
        lambda _candidate: _truth(allowed=True),
    )
    decision = contract.derive_canonical_execution_decision(_candidate())
    assert decision.state is ExecutionState.EXECUTABLE
    assert decision.allowed is True
    assert decision.primary_reason == "ok"
    assert decision.contradictions == ()


def test_fallback_truth_is_blocked_even_when_legacy_fields_claim_execute(monkeypatch):
    monkeypatch.setattr(
        contract,
        "classify_executable_truth",
        lambda _candidate: _truth(
            allowed=False,
            reasons=("fallback_driven_data",),
            reason_code="fallback_driven_data",
        ),
    )
    decision = contract.derive_canonical_execution_decision(_candidate())
    assert decision.state is ExecutionState.BLOCKED
    assert decision.allowed is False
    assert decision.primary_reason == "fallback_driven_data"


def test_advisory_only_truth_remains_non_executable(monkeypatch):
    monkeypatch.setattr(
        contract,
        "classify_executable_truth",
        lambda _candidate: _truth(
            allowed=False,
            reasons=("planning_only",),
            reason_code="planning_only",
        ),
    )
    decision = contract.derive_canonical_execution_decision(
        _candidate(
            execution_allowed=False,
            eligible_for_execution=False,
            tradable=False,
            execution_entry=None,
            execution_entry_status="non_executable",
            execution_status="advisory_only",
            permission="ADVISORY_ONLY",
            final_action="ADVISORY_ONLY",
            readiness="ADVISORY_ONLY",
            candidate_status="advisory_only",
        )
    )
    assert decision.state is ExecutionState.ADVISORY_ONLY
    assert decision.allowed is False


def test_contradictory_legacy_fields_fail_closed(monkeypatch):
    monkeypatch.setattr(
        contract,
        "classify_executable_truth",
        lambda _candidate: _truth(allowed=True),
    )
    decision = contract.derive_canonical_execution_decision(
        _candidate(hard_blockers=["stale_quote"])
    )
    assert decision.state is ExecutionState.BLOCKED
    assert decision.allowed is False
    assert "legacy_positive_and_negative_execution_signals" in decision.contradictions


def test_missing_execution_entry_fails_closed(monkeypatch):
    monkeypatch.setattr(
        contract,
        "classify_executable_truth",
        lambda _candidate: _truth(allowed=True),
    )
    decision = contract.derive_canonical_execution_decision(
        _candidate(execution_entry=None)
    )
    assert decision.state is ExecutionState.BLOCKED
    assert decision.primary_reason in {
        "execution_allowed_without_execution_entry",
        "executable_entry_status_without_execution_entry",
    }


def test_compare_legacy_and_canonical_exposes_mismatch(monkeypatch):
    monkeypatch.setattr(
        contract,
        "classify_executable_truth",
        lambda _candidate: _truth(
            allowed=False,
            reasons=("stale_option_ltp",),
            reason_code="stale_option_ltp",
        ),
    )
    result = contract.compare_legacy_and_canonical(_candidate())
    assert result["legacy_allowed"] is True
    assert result["canonical_allowed"] is False
    assert result["match"] is False
