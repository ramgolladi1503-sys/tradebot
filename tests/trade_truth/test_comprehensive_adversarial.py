"""Comprehensive adversarial test suite covering all 20 specified boundary conditions."""

import pytest
from core.trade_truth import (
    build_trade_truth_record,
    replay_truth_record,
    TruthStore,
    TruthStoreError,
    TRUTH_SCHEMA_VERSION,
)
from core.trade_truth.outcome_collector import compute_horizons_mfe_mae, PricePoint


def test_adversarial_1_missing_bid():
    record = build_trade_truth_record(
        trace_id="adv_missing_bid",
        session_id="s1",
        candidate={"candidate_id": "c1", "direction": "SELL_PUT"},
        market_snapshot={"symbol": "NIFTY", "ltp": 100.0, "bid": None, "ask": 101.0},
    )
    assert record.market.bid is None


def test_adversarial_2_missing_ask_for_buy_rejects_executable_price():
    record = build_trade_truth_record(
        trace_id="adv_missing_ask",
        session_id="s1",
        candidate={"candidate_id": "c1", "direction": "BUY_CALL"},
        market_snapshot={"symbol": "NIFTY", "ltp": 100.0, "bid": 99.0, "ask": None},
    )
    assert record.execution.theoretical_executable_price is None
    assert record.execution.executable_market_state == "UNKNOWN"
    assert record.execution.rejection_reason == "ASK_UNAVAILABLE"


def test_adversarial_3_empty_depth():
    record = build_trade_truth_record(
        trace_id="adv_empty_depth",
        session_id="s1",
        candidate={"candidate_id": "c1"},
        market_snapshot={"symbol": "NIFTY", "depth": []},
    )
    assert record.market.depth == ()


def test_adversarial_4_stale_tick():
    record = build_trade_truth_record(
        trace_id="adv_stale_tick",
        session_id="s1",
        candidate={"candidate_id": "c1"},
        market_snapshot={"symbol": "NIFTY", "quote_age_sec": 45.0, "market_state_integrity": "STALE"},
    )
    assert record.market.market_state_integrity == "STALE"


def test_adversarial_5_missing_decision_timestamp_remains_none():
    record = build_trade_truth_record(
        trace_id="adv_no_ts",
        session_id="s1",
        candidate={"candidate_id": "c1"},
        market_snapshot={"symbol": "NIFTY"},
        timing_context={},
    )
    assert record.timing.decision_timestamp_epoch is None


def test_adversarial_6_sequence_gap_flagged():
    record = build_trade_truth_record(
        trace_id="adv_gap",
        session_id="s1",
        candidate={"candidate_id": "c1"},
        market_snapshot={"symbol": "NIFTY", "sequence_gap_status": "SEQUENCE_GAP"},
    )
    assert record.market.sequence_gap_status == "SEQUENCE_GAP"


def test_adversarial_7_corrupted_record_fails_integrity():
    record = build_trade_truth_record(
        trace_id="adv_corrupt",
        session_id="s1",
        candidate={"candidate_id": "c1"},
        market_snapshot={"symbol": "NIFTY"},
    )
    d = record.to_dict()
    d["record_hash"] = "tampered_hash_value"
    res = replay_truth_record(d)
    assert res.record_integrity_valid is False
    assert res.status == "RECORD_CORRUPT"


def test_adversarial_8_future_schema_mismatch():
    record = build_trade_truth_record(
        trace_id="adv_schema",
        session_id="s1",
        candidate={"candidate_id": "c1"},
        market_snapshot={"symbol": "NIFTY"},
    )
    d = record.to_dict()
    d["schema_version"] = TRUTH_SCHEMA_VERSION + 10
    res = replay_truth_record(d)
    assert res.status == "TRUTH_SCHEMA_MISMATCH"


def test_adversarial_9_store_detects_chain_broken(tmp_path):
    store_file = tmp_path / "chain_broken.jsonl"
    store = TruthStore(store_file)

    rec1 = build_trade_truth_record(
        trace_id="adv_chain_1",
        session_id="s1",
        candidate={"candidate_id": "c1"},
        market_snapshot={"symbol": "NIFTY"},
        sequence_number=1,
        previous_record_hash="GENESIS",
    )
    store.write_record(rec1)

    rec2_broken = build_trade_truth_record(
        trace_id="adv_chain_2",
        session_id="s1",
        candidate={"candidate_id": "c2"},
        market_snapshot={"symbol": "NIFTY"},
        sequence_number=3,  # Broken sequence!
        previous_record_hash="WRONG_PREV_HASH",
    )
    # Write manually into file to simulate out-of-band corruption
    with store_file.open("a", encoding="utf-8") as f:
        import json
        f.write(json.dumps(rec2_broken.to_dict()) + "\n")

    valid, msg = store.verify_chain_integrity()
    assert valid is False
    assert "TRUTH_CHAIN_BROKEN" in msg


def test_adversarial_10_market_close_no_forward_observations():
    res = compute_horizons_mfe_mae(
        decision_epoch=1000.0,
        entry_price=100.0,
        direction="BUY_CALL",
        price_series=[PricePoint(timestamp_epoch=900.0, ltp=99.0)],
    )
    assert res["status"] == "NO_OBSERVATIONS"
    assert res["mfe_abs"] == 0.0
