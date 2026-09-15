"""Unit tests for Trade Truth Layer models, hashing, provenance, and storage."""

import pytest
import time
from core.trade_truth import (
    TradeTruthRecord,
    TRUTH_SCHEMA_VERSION,
    build_trade_truth_record,
    compute_live_decision_hash,
    compute_record_integrity_hash,
    TruthStore,
    replay_truth_record,
)
from core.trade_truth.provenance import redact_sensitive_dict, compute_config_hash
from core.trade_truth.store import TruthStoreError


def test_build_trade_truth_record_accepted(tmp_path):
    candidate = {
        "candidate_id": "cand_101",
        "strategy_id": "ORB_5MIN",
        "symbol": "NIFTY26MAR24000CE",
        "underlying": "NIFTY",
        "strike": 24000.0,
        "expiry": "2026-03-26",
        "direction": "BUY_CALL",
        "entry_price": 150.0,
        "rank_score": 0.88,
    }
    market = {
        "symbol": "NIFTY26MAR24000CE",
        "underlying": "NIFTY",
        "ltp": 150.5,
        "bid": 150.0,
        "ask": 151.0,
        "spread": 1.0,
        "quote_age_sec": 0.2,
        "data_source": "WEBSOCKET",
        "market_state_integrity": "VALID",
    }
    analytical = {
        "regime": "TRENDING_BULL",
        "regime_confidence": 0.92,
        "features_used": {"rsi_14": 62.5, "adx_14": 28.0},
        "signal_confidence": 0.85,
    }
    decision = {
        "final_action": "ENTRY",
        "governance_decision": "ALLOWED",
        "risk_result": "PASS",
        "reason_codes": ["MOMENTUM_ALIGNMENT", "SPREAD_OK"],
        "blockers": [],
    }

    record = build_trade_truth_record(
        trace_id="trace_acc_001",
        session_id="session_test",
        candidate=candidate,
        market_snapshot=market,
        analytical_context=analytical,
        decision_context=decision,
    )

    assert record.schema_version == TRUTH_SCHEMA_VERSION
    assert record.identity.trace_id == "trace_acc_001"
    assert record.identity.candidate_id == "cand_101"
    assert record.identity.strategy_id == "ORB_5MIN"
    assert record.decision.governance_decision == "ALLOWED"
    assert record.decision.final_action == "ENTRY"
    # BUY execution realism: ask side price evaluated
    assert record.execution.theoretical_executable_price == 151.0
    assert record.execution.is_counterfactual is False
    assert record.is_order_action is False
    assert record.broker_api_called is False
    assert record.orders_placed == 0
    assert record.live_decision_hash != ""
    assert record.record_hash != ""

    # Replay parity verification
    replay_res = replay_truth_record(record.to_dict())
    assert replay_res.parity is True
    assert replay_res.record_integrity_valid is True
    assert replay_res.status == "PARITY_VERIFIED"
    assert replay_res.live_decision_hash == replay_res.replay_decision_hash


def test_build_trade_truth_record_rejected_counterfactual():
    candidate = {
        "candidate_id": "cand_rej_002",
        "strategy_id": "MEAN_REVERSION",
        "symbol": "BANKNIFTY26MAR50000PE",
        "underlying": "BANKNIFTY",
        "strike": 50000.0,
        "direction": "BUY_PUT",
        "entry_price": 220.0,
    }
    market = {
        "symbol": "BANKNIFTY26MAR50000PE",
        "underlying": "BANKNIFTY",
        "ltp": 220.0,
        "bid": 215.0,
        "ask": 225.0,
        "spread": 10.0,
        "quote_age_sec": 4.5,
        "market_state_integrity": "STALE",
    }
    decision = {
        "final_action": "NO_TRADE",
        "governance_decision": "BLOCKED",
        "risk_result": "REJECT",
        "blockers": ["FEED_STALE", "SPREAD_TOO_WIDE"],
        "reason_codes": ["FEED_STALE", "SPREAD_TOO_WIDE"],
    }

    record = build_trade_truth_record(
        trace_id="trace_rej_002",
        session_id="session_test",
        candidate=candidate,
        market_snapshot=market,
        decision_context=decision,
    )

    assert record.decision.final_action == "NO_TRADE"
    assert record.decision.governance_decision == "BLOCKED"
    assert record.execution.is_counterfactual is True
    assert "FEED_STALE" in record.decision.reason_codes
    assert "SPREAD_TOO_WIDE" in record.decision.reason_codes

    replay_res = replay_truth_record(record.to_dict())
    assert replay_res.parity is True
    assert replay_res.status == "PARITY_VERIFIED"


def test_redaction_and_config_hash():
    dirty_dict = {
        "api_key": "SECRET_KEY_123",
        "nested": {
            "auth_token": "BEARER_XYZ",
            "normal_field": 42,
        },
        "password_hash": "abc",
        "user": "test_trader",
    }
    clean = redact_sensitive_dict(dirty_dict)
    assert clean["api_key"] == "[REDACTED]"
    assert clean["nested"]["auth_token"] == "[REDACTED]"
    assert clean["nested"]["normal_field"] == 42
    assert clean["password_hash"] == "[REDACTED]"
    assert clean["user"] == "test_trader"

    cfg_hash = compute_config_hash()
    assert isinstance(cfg_hash, str)
    assert len(cfg_hash) == 64


def test_truth_store_persists_and_fails_closed_on_tamper(tmp_path):
    store_file = tmp_path / "trade_truth.jsonl"
    store = TruthStore(store_file)

    candidate = {"candidate_id": "cand_tamper_1"}
    market = {"symbol": "NIFTY", "ltp": 24000.0}
    decision = {"final_action": "NO_TRADE", "governance_decision": "BLOCKED"}

    record = build_trade_truth_record(
        trace_id="trace_tamper_1",
        session_id="session_tamper",
        candidate=candidate,
        market_snapshot=market,
        decision_context=decision,
    )

    # Persist
    ok = store.write_record(record)
    assert ok is True

    # Retrieve
    retrieved_list = store.get_by_trace_id("trace_tamper_1")
    assert len(retrieved_list) >= 1
    retrieved = retrieved_list[0]
    assert retrieved["identity"]["trace_id"] == "trace_tamper_1"

    # Integrity verification
    replay_res = replay_truth_record(retrieved)
    assert replay_res.record_integrity_valid is True

    # Tamper with record
    retrieved["decision"]["final_action"] = "MODIFIED_ACTION"
    replay_tampered = replay_truth_record(retrieved)
    assert replay_tampered.parity is False
    assert replay_tampered.status == "FORENSIC_DIVERGENCE"
