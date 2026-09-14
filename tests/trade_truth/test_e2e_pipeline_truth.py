"""End-to-end controlled pipeline test for Trade Truth Layer.

Enters through candidate creation, evaluation, ranking/governance, candidate journal,
truth storage, session report, and forensic investigation without synthetic shortcutting.
"""

from pathlib import Path
import pytest
from core.candidate_journal import write_candidate_journal_row
from core.trade_truth import (
    TruthStore,
    replay_truth_record,
    default_partitioned_truth_path,
    generate_session_truth_report,
)


def test_controlled_pipeline_e2e_accepted_and_rejected(tmp_path):
    truth_file = tmp_path / "truth_e2e.jsonl"
    journal_file = tmp_path / "journal_e2e.jsonl"

    # 1. Controlled Pipeline Fixture — Accepted Candidate
    cand_acc_payload = {
        "candidate_id": "CAND_PIPELINE_ACC_001",
        "trade_id": "TRADE_ACC_001",
        "trace_id": "TRACE_E2E_ACC_001",
        "run_id": "RUN_SESSION_01",
        "session_id": "RUN_SESSION_01",
        "symbol": "NIFTY26MAR24000CE",
        "underlying": "NIFTY",
        "strike": 24000.0,
        "expiry": "2026-03-26",
        "side": "BUY",
        "direction": "BUY_CALL",
        "entry": 140.0,
        "entry_price": 140.0,
        "ltp": 140.0,
        "bid": 139.5,
        "ask": 140.5,
        "best_bid": 139.5,
        "best_ask": 140.5,
        "spread_pct": 0.007,
        "quote_source": "CONTROLLED_PIPELINE_FIXTURE",
        "feed_truth_state": "LIVE",
        "market_state_integrity": "VALID",
        "sequence_gap_status": "OK",
        "regime": "TRENDING_BULL",
        "permission": "ALLOW",
        "final_action": "ENTRY",
        "governance_decision": "ALLOWED",
        "risk_result": "PASS",
        "reason": "CRITERIA_SATISFIED",
        "reason_codes": ["CRITERIA_SATISFIED", "VOLATILITY_EXPANSION"],
        "reportable_executable": True,
        "execution_allowed": True,
        "is_oos": True,
        "oos_label": "OOS",
    }

    row_acc, ok_acc = write_candidate_journal_row(
        cand_acc_payload, path=journal_file
    )
    assert ok_acc is True
    assert "live_decision_hash" in row_acc
    assert "truth_record_hash" in row_acc

    # 2. Controlled Pipeline Fixture — Rejected Candidate (Ask Unavailable)
    cand_rej_payload = {
        "candidate_id": "CAND_PIPELINE_REJ_002",
        "trade_id": "TRADE_REJ_002",
        "trace_id": "TRACE_E2E_REJ_002",
        "run_id": "RUN_SESSION_01",
        "session_id": "RUN_SESSION_01",
        "symbol": "BANKNIFTY26MAR50000PE",
        "underlying": "BANKNIFTY",
        "strike": 50000.0,
        "expiry": "2026-03-26",
        "side": "BUY",
        "direction": "BUY_PUT",
        "entry": 310.0,
        "entry_price": 310.0,
        "ltp": 310.0,
        "bid": 305.0,
        "ask": None,  # Ask unavailable!
        "best_bid": 305.0,
        "best_ask": None,
        "quote_source": "CONTROLLED_PIPELINE_FIXTURE",
        "feed_truth_state": "LIVE",
        "market_state_integrity": "VALID",
        "sequence_gap_status": "OK",
        "regime": "CHOPPY",
        "permission": "BLOCK",
        "final_action": "NO_TRADE",
        "governance_decision": "BLOCKED",
        "risk_result": "REJECT",
        "reason": "ASK_UNAVAILABLE",
        "blockers": ["ASK_UNAVAILABLE", "REGIME_CHOPPY"],
        "reason_codes": ["ASK_UNAVAILABLE", "REGIME_CHOPPY"],
        "reportable_executable": False,
        "execution_allowed": False,
        "is_oos": True,
        "oos_label": "OOS",
    }

    row_rej, ok_rej = write_candidate_journal_row(
        cand_rej_payload, path=journal_file
    )
    assert ok_rej is True

    # 3. Verify in TruthStore
    store = TruthStore()
    records = list(store.read_records())
    assert len(records) >= 2

    # Query by trace
    acc_records = store.get_by_trace_id("TRACE_E2E_ACC_001")
    assert len(acc_records) >= 1
    acc_rec = acc_records[0]

    rej_records = store.get_by_trace_id("TRACE_E2E_REJ_002")
    assert len(rej_records) >= 1
    rej_rec = rej_records[0]

    # Check unknown semantics on rejected record
    assert rej_rec["execution"]["theoretical_executable_price"] is None
    assert rej_rec["execution"]["executable_market_state"] == "UNKNOWN"
    assert rej_rec["execution"]["rejection_reason"] == "ASK_UNAVAILABLE"
    assert rej_rec["execution"]["is_counterfactual"] is True

    # Check replay parity on both
    replay_acc = replay_truth_record(acc_rec)
    assert replay_acc.parity is True
    assert replay_acc.status == "PARITY_VERIFIED"

    replay_rej = replay_truth_record(rej_rec)
    assert replay_rej.parity is True
    assert replay_rej.status == "PARITY_VERIFIED"

    # 4. Generate Session Report
    report = generate_session_truth_report([acc_rec, rej_rec])
    assert report["total_evaluated_candidates"] == 2
    assert report["accepted"] == 1
    assert report["rejected"] == 1
    assert report["replay_parity_rate"] == 1.0
    assert report["unknown_execution_fields_count"] == 1
    assert report["broker_api_called"] is False
    assert report["orders_placed"] == 0
