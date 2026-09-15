"""Tests for Outcome Collector statefulness and Hash Chain recovery across restarts."""

import json
from pathlib import Path
import pytest

from core.trade_truth import (
    build_trade_truth_record,
    TruthStore,
    TruthStoreError,
    replay_truth_record,
)
from core.trade_truth.outcome_collector import (
    compute_horizons_mfe_mae,
    attach_outcome_amendment,
    PricePoint,
)


def test_outcome_collector_stateful_horizons():
    """Verify +1/+3/+5/+10/+15/+30 horizon semantics with deterministic clock fixtures."""
    decision_epoch = 1000.0
    entry_price = 100.0
    direction = "BUY_CALL"

    # Price points arriving across time
    prices = [
        PricePoint(timestamp_epoch=1030.0, ltp=105.0),   # inside +1m (1060s)
        PricePoint(timestamp_epoch=1050.0, ltp=108.0),   # inside +1m, MFE=8
        PricePoint(timestamp_epoch=1120.0, ltp=95.0),    # inside +3m (1180s), MAE=5
        PricePoint(timestamp_epoch=1250.0, ltp=115.0),   # inside +5m (1300s), MFE=15
        PricePoint(timestamp_epoch=1500.0, ltp=120.0),   # inside +10m (1600s), MFE=20
        PricePoint(timestamp_epoch=1800.0, ltp=110.0),   # inside +15m (1900s)
        PricePoint(timestamp_epoch=2700.0, ltp=130.0),   # inside +30m (2800s), MFE=30
    ]

    res = compute_horizons_mfe_mae(
        decision_epoch=decision_epoch,
        entry_price=entry_price,
        direction=direction,
        price_series=prices,
    )

    assert res["status"] == "OBSERVED"
    assert res["mfe_abs"] == 30.0
    assert res["mae_abs"] == 5.0
    h = res["horizons"]
    assert "+1m" in h and h["+1m"]["mfe"] == 8.0
    assert "+3m" in h and h["+3m"]["mae"] == 5.0
    assert "+5m" in h and h["+5m"]["mfe"] == 15.0
    assert "+10m" in h and h["+10m"]["mfe"] == 20.0
    assert "+30m" in h and h["+30m"]["mfe"] == 30.0


def test_outcome_amendment_is_append_only(tmp_path):
    store_file = tmp_path / "truth_amend.jsonl"
    store = TruthStore(store_file)

    # 1. Original decision record
    rec_orig = build_trade_truth_record(
        trace_id="trace_amend_1",
        session_id="s_amend",
        candidate={"candidate_id": "c_amend_1", "direction": "BUY_CALL", "entry_price": 100.0},
        market_snapshot={"symbol": "NIFTY", "ltp": 100.0, "ask": 100.5, "market_state_integrity": "VALID"},
        decision_context={"final_action": "ENTRY", "governance_decision": "ALLOWED"},
        sequence_number=store.next_sequence_number,
        previous_record_hash=store.last_record_hash,
    )
    store.write_record(rec_orig)

    # Original decision hash must be preserved
    orig_hash = rec_orig.live_decision_hash

    # 2. Forward prices arrive later -> attach outcome amendment
    forward_prices = [
        PricePoint(timestamp_epoch=1060.0, ltp=110.0),
        PricePoint(timestamp_epoch=1180.0, ltp=120.0),
    ]
    amended = attach_outcome_amendment(rec_orig.to_dict(), forward_prices, store)

    # Verify store now has 2 records: 1 original, 1 amendment
    records = list(store.read_records())
    assert len(records) == 2
    assert records[0]["record_type"] == "DECISION_TRUTH"
    assert records[1]["record_type"] == "OUTCOME_AMENDMENT"
    assert records[1]["parent_truth_record_id"] == records[0]["identity"]["truth_record_id"]

    # Original record was NOT mutated
    assert records[0]["live_decision_hash"] == orig_hash
    assert records[0]["sequence_number"] == 1
    assert records[1]["sequence_number"] == 2
    assert records[1]["previous_record_hash"] == records[0]["record_hash"]

    # Verify cryptographic chain
    valid, msg = store.verify_chain_integrity()
    assert valid is True
    assert msg == "VALID_CHAIN"


def test_hash_chain_across_restarts_and_tampering(tmp_path):
    store_file = tmp_path / "chain_tamper.jsonl"

    # Step 1: Write initial 3 records
    store1 = TruthStore(store_file)
    for i in range(1, 4):
        rec = build_trade_truth_record(
            trace_id=f"t_{i}",
            session_id="s1",
            candidate={"candidate_id": f"c_{i}"},
            market_snapshot={"symbol": "NIFTY"},
            sequence_number=store1.next_sequence_number,
            previous_record_hash=store1.last_record_hash,
        )
        store1.write_record(rec)

    # Step 2: Simulate process exit & restart
    store2 = TruthStore(store_file)
    assert store2.next_sequence_number == 4
    assert store2.last_record_hash != "GENESIS"

    # Step 3: Append 4th record after restart
    rec4 = build_trade_truth_record(
        trace_id="t_4",
        session_id="s1",
        candidate={"candidate_id": "c_4"},
        market_snapshot={"symbol": "NIFTY"},
        sequence_number=store2.next_sequence_number,
        previous_record_hash=store2.last_record_hash,
    )
    store2.write_record(rec4)

    valid, msg = store2.verify_chain_integrity()
    assert valid is True
    assert msg == "VALID_CHAIN"

    # Step 4: Tamper A — Delete middle record (record 2)
    lines = store_file.read_text().splitlines()
    store_file_del = tmp_path / "chain_del.jsonl"
    store_file_del.write_text("\n".join([lines[0], lines[2], lines[3]]) + "\n")
    store_del = TruthStore(store_file_del)
    valid_del, msg_del = store_del.verify_chain_integrity()
    assert valid_del is False
    assert "TRUTH_CHAIN_BROKEN" in msg_del

    # Step 5: Tamper B — Reorder records (swap record 2 and record 3)
    store_file_swap = tmp_path / "chain_swap.jsonl"
    store_file_swap.write_text("\n".join([lines[0], lines[2], lines[1], lines[3]]) + "\n")
    store_swap = TruthStore(store_file_swap)
    valid_swap, msg_swap = store_swap.verify_chain_integrity()
    assert valid_swap is False
    assert "TRUTH_CHAIN_BROKEN" in msg_swap

    # Step 6: Tamper C — Truncate last record (corrupt json)
    store_file_trunc = tmp_path / "chain_trunc.jsonl"
    store_file_trunc.write_text("\n".join(lines[:3]) + "\n" + lines[3][: len(lines[3]) // 2] + "\n")
    store_trunc = TruthStore(store_file_trunc)
    with pytest.raises(TruthStoreError, match="TRUTH_CORRUPT"):
        list(store_trunc.read_records())
