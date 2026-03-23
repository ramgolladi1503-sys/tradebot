from __future__ import annotations

import pytest

from core.trade_state_machine import (
    TradeLifecycleState,
    TradeLifecycleTransitionError,
    TradeStateTransitionError,
    TradeStateV1,
    rehydrate_trade_lifecycle,
    transition_trade_lifecycle,
    transition_trade_state,
)


def test_valid_transition_new_to_candidate():
    trade = {"trade_id": "t1", "trade_state_v1": "NEW"}
    out = transition_trade_state(trade, TradeStateV1.CANDIDATE)
    assert out["trade_state_v1"] == "CANDIDATE"


def test_invalid_transition_candidate_to_filled_raises():
    trade = {"trade_id": "t2", "trade_state_v1": "CANDIDATE"}
    with pytest.raises(TradeStateTransitionError):
        transition_trade_state(trade, TradeStateV1.FILLED)


def test_approved_requires_expected_entry_and_snapshot_id():
    missing_expected = {"trade_id": "t3", "trade_state_v1": "CANDIDATE", "snapshot_id": "snap-1"}
    with pytest.raises(ValueError, match="approved_requires_expected_entry"):
        transition_trade_state(missing_expected, TradeStateV1.APPROVED)

    missing_snapshot = {"trade_id": "t4", "trade_state_v1": "CANDIDATE", "expected_entry": 101.25}
    with pytest.raises(ValueError, match="approved_requires_snapshot_id"):
        transition_trade_state(missing_snapshot, TradeStateV1.APPROVED)


def test_approved_transition_passes_with_required_fields():
    trade = {
        "trade_id": "t5",
        "trade_state_v1": "CANDIDATE",
        "expected_entry": 102.5,
        "snapshot_id": "snap-abc",
    }
    out = transition_trade_state(trade, TradeStateV1.APPROVED)
    assert out["trade_state_v1"] == "APPROVED"
    assert out["trade_lifecycle_state"] == "execution_pending"


def test_valid_canonical_trade_lifecycle_path_succeeds():
    trade = {"trade_id": "t6"}

    trade = transition_trade_lifecycle(trade, TradeLifecycleState.SCORED, reason="scored_candidate")
    trade = transition_trade_lifecycle(trade, TradeLifecycleState.RANKED, reason="ranked_candidate")
    trade = transition_trade_lifecycle(trade, TradeLifecycleState.ADVISORY, reason="display_only")
    trade = transition_trade_lifecycle(trade, TradeLifecycleState.EXECUTION_PENDING, reason="ready_to_route")
    trade = transition_trade_lifecycle(trade, TradeLifecycleState.ACTIVE, reason="execution_filled")
    trade = transition_trade_lifecycle(trade, TradeLifecycleState.EXIT_PENDING, reason="exit_order_submitted")
    trade = transition_trade_lifecycle(trade, TradeLifecycleState.CLOSED, reason="position_closed")
    trade = transition_trade_lifecycle(trade, TradeLifecycleState.RECONCILED, reason="broker_reconciled")

    assert trade["trade_lifecycle_state"] == "reconciled"
    assert trade["trade_lifecycle_reason"] == "broker_reconciled"
    assert [event["state"] for event in trade["trade_lifecycle_history"]] == [
        "idea_created",
        "scored",
        "ranked",
        "advisory",
        "execution_pending",
        "active",
        "exit_pending",
        "closed",
        "reconciled",
    ]


def test_invalid_canonical_trade_lifecycle_transition_rejected_with_reason():
    trade = {"trade_id": "t7"}
    with pytest.raises(TradeLifecycleTransitionError, match="invalid_trade_lifecycle_transition:idea_created->active") as exc:
        transition_trade_lifecycle(trade, TradeLifecycleState.ACTIVE, reason="skip_execution_pending")
    assert exc.value.reason == "skip_execution_pending"


def test_restart_recovery_rehydrates_canonical_state():
    trade = {
        "trade_id": "t8",
        "trade_state_v1": "APPROVED",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "execution_status": "executable",
    }

    out = rehydrate_trade_lifecycle(trade, reason="restart_rehydrated")

    assert out["trade_lifecycle_state"] == "execution_pending"
    assert out["trade_lifecycle_reason"] == "restart_rehydrated"
    assert out["trade_lifecycle_history"][-1]["state"] == "execution_pending"
