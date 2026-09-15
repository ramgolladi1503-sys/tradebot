"""Controlled bug-injection tests assessing the causal replay boundary.

Proves:
- Level B (DECISION_TAIL_REPLAY): Evaluator re-executes risk/governance/decision from frozen features/regime.
- When feature computation or regime logic changes upstream:
  - If frozen features/regime are injected into replay, replay does NOT re-derive them from raw ticks (hence FULL_CAUSAL_REPLAY=False).
- When risk or governance logic changes:
  - Replay detects divergence immediately (hence DECISION_TAIL_REPLAY=True).
"""

import pytest
from core.trade_truth import (
    build_trade_truth_record,
    replay_truth_record,
)
from core.trade_truth.replay import default_decision_evaluator


def test_bug_injection_governance_mutation_detected():
    """Mutate governance logic so ALLOWED becomes BLOCKED. Replay must detect divergence."""
    record = build_trade_truth_record(
        trace_id="trace_gov_mut",
        session_id="s1",
        candidate={"candidate_id": "c1", "direction": "BUY_CALL", "entry_price": 100.0},
        market_snapshot={"symbol": "NIFTY", "ltp": 100.0, "ask": 100.5, "market_state_integrity": "VALID"},
        decision_context={"final_action": "ENTRY", "governance_decision": "ALLOWED", "risk_result": "PASS"},
    )
    payload = record.to_dict()

    # Mutated evaluator where governance always blocks
    def mutated_gov_evaluator(market, features, candidate, analytical):
        return "PASS", "BLOCKED", "NO_TRADE", ["GOVERNANCE_MUTATED_BLOCK"]

    res = replay_truth_record(payload, decision_engine_func=mutated_gov_evaluator)
    assert res.parity is False
    assert res.status == "FORENSIC_DIVERGENCE"
    assert "Decision hash divergence" in res.divergences[0]


def test_bug_injection_risk_mutation_detected():
    """Mutate risk logic so PASS becomes REJECT. Replay must detect divergence."""
    record = build_trade_truth_record(
        trace_id="trace_risk_mut",
        session_id="s1",
        candidate={"candidate_id": "c1", "direction": "BUY_CALL", "entry_price": 100.0},
        market_snapshot={"symbol": "NIFTY", "ltp": 100.0, "ask": 100.5, "market_state_integrity": "VALID"},
        decision_context={"final_action": "ENTRY", "governance_decision": "ALLOWED", "risk_result": "PASS"},
    )
    payload = record.to_dict()

    # Mutated evaluator where risk rejects
    def mutated_risk_evaluator(market, features, candidate, analytical):
        return "REJECT", "BLOCKED", "NO_TRADE", ["RISK_MUTATED_REJECT"]

    res = replay_truth_record(payload, decision_engine_func=mutated_risk_evaluator)
    assert res.parity is False
    assert res.status == "FORENSIC_DIVERGENCE"


def test_bug_injection_feature_and_regime_causal_boundary():
    """Verify that replay starts from frozen analytical features/regime.

    Because replay consumes frozen features and regime rather than re-computing them
    from raw bar history, it classifies strictly as Level B: DECISION_TAIL_REPLAY,
    not Level C (FULL_CAUSAL_DECISION_REPLAY).
    """
    record = build_trade_truth_record(
        trace_id="trace_feat_bound",
        session_id="s1",
        candidate={"candidate_id": "c1", "direction": "BUY_CALL", "entry_price": 100.0},
        market_snapshot={"symbol": "NIFTY", "ltp": 100.0, "ask": 100.5, "market_state_integrity": "VALID"},
        analytical_context={"regime": "TRENDING_BULL", "features_used": {"rsi": 65.0}},
        decision_context={"final_action": "ENTRY", "governance_decision": "ALLOWED", "risk_result": "PASS"},
    )
    payload = record.to_dict()

    # If the feature inside the frozen payload is tampered, replay hash changes
    payload_tampered = dict(payload)
    payload_tampered["analytical"] = dict(payload["analytical"])
    payload_tampered["analytical"]["features_used"] = {"rsi": 25.0}  # Tampered feature

    res = replay_truth_record(payload_tampered)
    # The divergence is detected because re-execution uses payload's features, but live_decision_hash was over original!
    assert res.parity is False
    assert res.status == "FORENSIC_DIVERGENCE"
