from __future__ import annotations

import pytest

from core.trade_state_machine import (
    TradeStateTransitionError,
    TradeStateV1,
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

