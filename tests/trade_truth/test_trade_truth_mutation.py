"""Mutation testing for Trade Truth Layer invariants and gating."""

import pytest
from core.trade_truth import (
    build_trade_truth_record,
    replay_truth_record,
    compute_record_integrity_hash,
    TruthStore,
)
from core.trade_truth.store import TruthStoreError


def test_mutation_hash_mismatch_detected():
    record = build_trade_truth_record(
        trace_id="trace_mut_1",
        session_id="s1",
        candidate={"candidate_id": "c1", "direction": "BUY_CALL"},
        market_snapshot={"symbol": "NIFTY", "ltp": 100.0},
        decision_context={"final_action": "ENTRY", "governance_decision": "ALLOWED"},
    )
    payload = record.to_dict()

    # Mutation 1: Change decision without updating hash
    payload["decision"]["final_action"] = "EXIT"
    res = replay_truth_record(payload)
    assert res.parity is False
    assert res.status == "FORENSIC_DIVERGENCE"


def test_mutation_stale_feed_detection():
    # Stale feed must mark executable state as NOT_EXECUTABLE
    record = build_trade_truth_record(
        trace_id="trace_mut_stale",
        session_id="s1",
        candidate={"candidate_id": "c1", "direction": "BUY_CALL"},
        market_snapshot={"symbol": "NIFTY", "ltp": 100.0, "market_state_integrity": "STALE"},
        decision_context={"final_action": "NO_TRADE", "blockers": ["FEED_STALE"]},
    )
    assert record.market.market_state_integrity == "STALE"
    assert record.execution.executable_market_state == "NOT_EXECUTABLE"


def test_mutation_ask_side_execution_price_for_buy():
    # Mutation: BUY order must evaluate ask price, not simply LTP
    record = build_trade_truth_record(
        trace_id="trace_mut_ask",
        session_id="s1",
        candidate={"candidate_id": "c1", "direction": "BUY_CALL", "entry_price": 50.0},
        market_snapshot={"symbol": "NIFTY", "ltp": 50.0, "bid": 49.0, "ask": 52.0},
        decision_context={"final_action": "ENTRY"},
    )
    assert record.execution.theoretical_executable_price == 52.0


def test_mutation_store_rejects_order_action_violation():
    store = TruthStore("/tmp/truth_store_guard.jsonl")
    record = build_trade_truth_record(
        trace_id="trace_mut_guard",
        session_id="s1",
        candidate={"candidate_id": "c1"},
        market_snapshot={"symbol": "NIFTY"},
        decision_context={"final_action": "ENTRY"},
    )

    # Mutate to violate safety invariant
    object.__setattr__(record, "is_order_action", True)
    with pytest.raises(TruthStoreError, match="Safety invariant violated"):
        store.write_record(record)
