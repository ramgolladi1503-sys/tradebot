from __future__ import annotations

from core.candidate_status_contract import (
    EXECUTION_ALLOWED_STATUS,
    EXECUTION_BLOCKED_STATUS,
    EXECUTION_PERMISSION_UNKNOWN_STATUS,
    PRICE_FEASIBLE_STATUS,
    PRICE_NOT_FEASIBLE_STATUS,
    PRICE_UNKNOWN_STATUS,
    classify_candidate_status_contract,
)


def test_legacy_executable_entry_status_only_means_price_feasible_not_execution_allowed():
    decision = classify_candidate_status_contract(
        {
            "execution_entry_status": "executable",
            "execution_allowed": False,
        }
    )

    assert decision.price_feasibility_status == PRICE_FEASIBLE_STATUS
    assert decision.price_feasible is True
    assert decision.execution_permission_status == EXECUTION_BLOCKED_STATUS
    assert decision.execution_allowed is False
    assert decision.context["legacy_execution_entry_status"] == "executable"
    assert decision.context["is_order_action"] is False
    assert decision.context["broker_api_called"] is False


def test_advisory_only_feasible_entry_remains_execution_blocked():
    decision = classify_candidate_status_contract(
        {
            "execution_entry_status": "executable",
            "advisory_only": True,
        }
    )

    assert decision.price_feasibility_status == PRICE_FEASIBLE_STATUS
    assert decision.execution_permission_status == EXECUTION_BLOCKED_STATUS
    assert decision.execution_allowed is False
    assert "advisory_only" in decision.context["markers"]


def test_explicit_execution_allowed_requires_permission_not_just_price():
    decision = classify_candidate_status_contract(
        {
            "entry_price": 101.25,
            "execution_allowed": True,
        }
    )

    assert decision.price_feasibility_status == PRICE_FEASIBLE_STATUS
    assert decision.execution_permission_status == EXECUTION_ALLOWED_STATUS
    assert decision.price_feasible is True
    assert decision.execution_allowed is True


def test_stale_quote_makes_price_not_feasible_and_execution_blocked():
    decision = classify_candidate_status_contract(
        {
            "execution_entry_status": "executable",
            "reasons": ["stale_quote"],
            "execution_allowed": True,
        }
    )

    assert decision.price_feasibility_status == PRICE_NOT_FEASIBLE_STATUS
    assert decision.price_feasible is False
    assert decision.execution_permission_status == EXECUTION_BLOCKED_STATUS
    assert decision.execution_allowed is False
    assert "stale_quote" in decision.reasons


def test_unknown_price_and_permission_fail_closed_to_unknown_not_allowed():
    decision = classify_candidate_status_contract({"symbol": "NIFTY"})

    assert decision.price_feasibility_status == PRICE_UNKNOWN_STATUS
    assert decision.execution_permission_status == EXECUTION_PERMISSION_UNKNOWN_STATUS
    assert decision.price_feasible is False
    assert decision.execution_allowed is False
    assert "price_feasibility_unknown" in decision.reasons
    assert "execution_permission_unknown" in decision.reasons


def test_source_flags_are_supported_without_mutating_candidate():
    candidate = {
        "source_flags": {
            "execution_feasibility_status": "executable",
            "execution_allowed": False,
            "planning_only": True,
        }
    }

    decision = classify_candidate_status_contract(candidate)

    assert decision.price_feasibility_status == PRICE_FEASIBLE_STATUS
    assert decision.execution_permission_status == EXECUTION_BLOCKED_STATUS
    assert decision.execution_allowed is False
    assert candidate["source_flags"]["planning_only"] is True
