"""Integration, adversarial, determinism, and decay watchdog tests for Trade Truth."""

import pytest
from core.trade_truth import (
    build_trade_truth_record,
    replay_truth_record,
    TruthStore,
    evaluate_strategy_decay,
    TRUTH_SCHEMA_VERSION,
)
from core.trade_truth.store import TruthStoreError


def test_scenario_a_accepted_candidate():
    candidate = {
        "candidate_id": "cand_accepted_1",
        "strategy_id": "BREAKOUT_PRO",
        "symbol": "NIFTY26MAR24500CE",
        "underlying": "NIFTY",
        "strike": 24500.0,
        "direction": "BUY_CALL",
        "entry_price": 105.0,
    }
    market = {
        "symbol": "NIFTY26MAR24500CE",
        "underlying": "NIFTY",
        "ltp": 105.0,
        "bid": 104.5,
        "ask": 105.5,
        "spread": 1.0,
        "quote_age_sec": 0.5,
        "market_state_integrity": "VALID",
    }
    analytical = {
        "regime": "TRENDING",
        "features_used": {"momentum": 1.45},
    }
    decision = {
        "final_action": "ENTRY",
        "governance_decision": "ALLOWED",
        "risk_result": "PASS",
        "reason_codes": ["VOLATILITY_EXPANSION"],
    }
    outcome = {
        "status": "OBSERVED",
        "mfe_abs": 125.0,
        "mae_abs": 98.0,
        "realized_outcome": "TARGET_HIT",
    }

    record = build_trade_truth_record(
        trace_id="trace_scen_a",
        session_id="session_live",
        candidate=candidate,
        market_snapshot=market,
        analytical_context=analytical,
        decision_context=decision,
        outcome_context=outcome,
    )

    assert record.decision.final_action == "ENTRY"
    assert record.outcome.realized_outcome == "TARGET_HIT"
    assert record.is_order_action is False
    assert record.broker_api_called is False

    replay = replay_truth_record(record.to_dict())
    assert replay.parity is True
    assert replay.status == "PARITY_VERIFIED"


def test_scenario_b_rejected_counterfactual():
    candidate = {
        "candidate_id": "cand_rejected_1",
        "strategy_id": "MOMENTUM_PULLBACK",
        "symbol": "BANKNIFTY26MAR48000PE",
        "direction": "BUY_PUT",
        "entry_price": 250.0,
    }
    market = {
        "symbol": "BANKNIFTY26MAR48000PE",
        "ltp": 250.0,
        "bid": 240.0,
        "ask": 260.0,
        "spread": 20.0,
        "market_state_integrity": "VALID",
    }
    decision = {
        "final_action": "NO_TRADE",
        "governance_decision": "BLOCKED",
        "risk_result": "REJECT",
        "blockers": ["SPREAD_TOO_WIDE"],
        "reason_codes": ["SPREAD_TOO_WIDE"],
    }
    outcome = {
        "status": "OBSERVED",
        "mfe_abs": 280.0,
        "mae_abs": 230.0,
        "realized_outcome": "TIMEOUT",
    }

    record = build_trade_truth_record(
        trace_id="trace_scen_b",
        session_id="session_live",
        candidate=candidate,
        market_snapshot=market,
        decision_context=decision,
        outcome_context=outcome,
    )

    assert record.execution.is_counterfactual is True
    assert record.outcome.is_counterfactual is True
    assert "SPREAD_TOO_WIDE" in record.decision.reason_codes

    replay = replay_truth_record(record.to_dict())
    assert replay.parity is True
    assert replay.status == "PARITY_VERIFIED"


def test_scenario_c_stale_market_data():
    candidate = {"candidate_id": "cand_stale_1", "direction": "BUY_CALL"}
    market = {
        "symbol": "NIFTY26MAR24000CE",
        "ltp": 120.0,
        "quote_age_sec": 15.0,
        "market_state_integrity": "STALE",
    }
    decision = {
        "final_action": "NO_TRADE",
        "governance_decision": "BLOCKED",
        "risk_result": "REJECT",
        "blockers": ["FEED_STALE"],
        "reason_codes": ["FEED_STALE"],
    }

    record = build_trade_truth_record(
        trace_id="trace_scen_c",
        session_id="session_live",
        candidate=candidate,
        market_snapshot=market,
        decision_context=decision,
    )

    assert record.market.market_state_integrity == "STALE"
    assert "FEED_STALE" in record.decision.reason_codes
    assert record.execution.executable_market_state == "NOT_EXECUTABLE"


def test_scenario_d_sequence_gap():
    candidate = {"candidate_id": "cand_gap_1", "direction": "BUY_CALL"}
    market = {
        "symbol": "NIFTY26MAR24000CE",
        "ltp": 120.0,
        "sequence_gap_status": "SEQUENCE_GAP",
        "market_state_integrity": "DEGRADED",
    }
    decision = {
        "final_action": "NO_TRADE",
        "governance_decision": "BLOCKED",
        "blockers": ["SEQUENCE_GAP_DETECTED"],
        "reason_codes": ["SEQUENCE_GAP_DETECTED"],
    }

    record = build_trade_truth_record(
        trace_id="trace_scen_d",
        session_id="session_live",
        candidate=candidate,
        market_snapshot=market,
        decision_context=decision,
    )

    assert record.market.sequence_gap_status == "SEQUENCE_GAP"
    assert record.market.market_state_integrity == "DEGRADED"


def test_determinism_across_multiple_runs():
    cand = {"candidate_id": "c1", "direction": "BUY_CALL", "entry_price": 100.0}
    mkt = {"symbol": "NIFTY", "ltp": 100.0, "ask": 101.0}
    ana = {"regime": "TRENDING", "features_used": {"feat1": 1.23456}}
    dec = {"final_action": "ENTRY", "governance_decision": "ALLOWED", "risk_result": "PASS"}

    r1 = build_trade_truth_record(
        trace_id="trace_det",
        session_id="s1",
        candidate=cand,
        market_snapshot=mkt,
        analytical_context=ana,
        decision_context=dec,
    )
    r2 = build_trade_truth_record(
        trace_id="trace_det",
        session_id="s1",
        candidate=cand,
        market_snapshot=mkt,
        analytical_context=ana,
        decision_context=dec,
    )
    r3 = build_trade_truth_record(
        trace_id="trace_det",
        session_id="s1",
        candidate=cand,
        market_snapshot=mkt,
        analytical_context=ana,
        decision_context=dec,
    )

    assert r1.live_decision_hash == r2.live_decision_hash == r3.live_decision_hash
    assert len(r1.live_decision_hash) == 64


def test_adversarial_tampered_schema_and_empty_values():
    candidate = {"candidate_id": "cand_adv_1"}
    market = {"symbol": "NIFTY"}
    decision = {}

    record = build_trade_truth_record(
        trace_id="trace_adv_1",
        session_id="s_adv",
        candidate=candidate,
        market_snapshot=market,
        decision_context=decision,
    )

    d = record.to_dict()
    d["schema_version"] = 999  # Incompatible future schema
    replay = replay_truth_record(d)
    assert replay.parity is False
    assert replay.status == "TRUTH_SCHEMA_MISMATCH"


def test_strategy_decay_watchdog():
    records = []
    # Generate 10 records for decaying strategy (MFE < MAE)
    for i in range(10):
        r = build_trade_truth_record(
            trace_id=f"decay_{i}",
            session_id="s1",
            candidate={"candidate_id": f"c_{i}", "strategy_id": "DECAYING_STRAT"},
            market_snapshot={"symbol": "NIFTY"},
            decision_context={"final_action": "ENTRY", "governance_decision": "ALLOWED"},
            outcome_context={
                "status": "OBSERVED",
                "mfe_abs": 10.0,
                "mae_abs": 50.0,
                "realized_outcome": "STOP_HIT",
            },
        )
        records.append(r.to_dict())

    evals = evaluate_strategy_decay(records)
    assert "DECAYING_STRAT" in evals
    decay_eval = evals["DECAYING_STRAT"]
    assert decay_eval.total_decisions == 10
    assert decay_eval.hit_rate == 0.0
    assert decay_eval.status == "EDGE_DECAY_SUSPECTED"
    assert decay_eval.recommendation == "DISABLE_PENDING_REVIEW"
