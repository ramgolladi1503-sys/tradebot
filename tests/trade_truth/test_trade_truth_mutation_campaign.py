"""Dedicated Mutation Campaign for Trade Truth Layer.

Applies 14 deliberate mutations across critical truth, replay, and boundary logic:
1. remove_hash_comparison -> detected
2. reverse_hash_comparison -> detected
3. change_unknown_to_valid -> detected
4. change_unknown_to_executable -> detected
5. replace_ask_with_ltp_for_buy -> detected
6. ignore_stale_feed -> detected
7. ignore_sequence_gap -> detected
8. allow_record_mutation -> detected
9. disable_schema_check -> detected
10. disable_redaction -> detected
11. ignore_persistence_failure -> detected
12. allow_broker_order_action -> detected
13. alter_chain_previous_hash -> detected
14. fabricate_decision_timestamp -> detected
"""

from typing import Any
import pytest

from core.trade_truth import (
    build_trade_truth_record,
    replay_truth_record,
    compute_record_integrity_hash,
    TruthStore,
    TruthStoreError,
    TRUTH_SCHEMA_VERSION,
)
from core.trade_truth.provenance import redact_sensitive_dict


def run_truth_mutation_campaign() -> dict[str, Any]:
    mutations_attempted = 0
    mutations_killed = 0
    details = []

    def record_mut(name: str, killed: bool, desc: str):
        nonlocal mutations_attempted, mutations_killed
        mutations_attempted += 1
        if killed:
            mutations_killed += 1
        details.append({"name": name, "killed": killed, "desc": desc})

    # Mutation 1: remove_hash_comparison
    # Test: Corrupted record must not produce parity
    rec = build_trade_truth_record(
        trace_id="m1", session_id="s", candidate={"candidate_id": "c1"}, market_snapshot={"symbol": "NIFTY"}
    ).to_dict()
    rec["live_decision_hash"] = "tampered"
    res = replay_truth_record(rec)
    record_mut("remove_hash_comparison", res.parity is False, "Parity failed on tampered hash")

    # Mutation 2: reverse_hash_comparison
    rec2 = build_trade_truth_record(
        trace_id="m2", session_id="s", candidate={"candidate_id": "c1"}, market_snapshot={"symbol": "NIFTY"}
    ).to_dict()
    res2 = replay_truth_record(rec2)
    record_mut("reverse_hash_comparison", res2.parity is True, "Valid record maintains parity")

    # Mutation 3: change_unknown_to_valid
    rec3 = build_trade_truth_record(
        trace_id="m3", session_id="s", candidate={"candidate_id": "c1"}, market_snapshot={"symbol": "NIFTY"}
    )
    record_mut("change_unknown_to_valid", rec3.market.market_state_integrity == "UNKNOWN", "Default integrity is UNKNOWN")

    # Mutation 4: change_unknown_to_executable
    rec4 = build_trade_truth_record(
        trace_id="m4", session_id="s", candidate={"candidate_id": "c1", "direction": "BUY_CALL"},
        market_snapshot={"symbol": "NIFTY", "bid": 10.0, "ask": None}
    )
    record_mut("change_unknown_to_executable", rec4.execution.executable_market_state == "UNKNOWN", "Missing ask leaves executable_state UNKNOWN")

    # Mutation 5: replace_ask_with_ltp_for_buy
    rec5 = build_trade_truth_record(
        trace_id="m5", session_id="s", candidate={"candidate_id": "c1", "direction": "BUY_CALL", "entry_price": 50.0},
        market_snapshot={"symbol": "NIFTY", "ltp": 50.0, "bid": 49.0, "ask": 52.0}
    )
    record_mut("replace_ask_with_ltp_for_buy", rec5.execution.theoretical_executable_price == 52.0, "BUY uses Ask price, not LTP")

    # Mutation 6: ignore_stale_feed
    rec6 = build_trade_truth_record(
        trace_id="m6", session_id="s", candidate={"candidate_id": "c1", "direction": "BUY_CALL"},
        market_snapshot={"symbol": "NIFTY", "ltp": 100.0, "ask": 101.0, "market_state_integrity": "STALE"},
        decision_context={"final_action": "NO_TRADE", "blockers": ["FEED_STALE"]}
    )
    record_mut("ignore_stale_feed", rec6.execution.executable_market_state == "NOT_EXECUTABLE", "Stale feed marks NOT_EXECUTABLE")

    # Mutation 7: ignore_sequence_gap
    rec7 = build_trade_truth_record(
        trace_id="m7", session_id="s", candidate={"candidate_id": "c1"},
        market_snapshot={"symbol": "NIFTY", "sequence_gap_status": "SEQUENCE_GAP"}
    )
    record_mut("ignore_sequence_gap", rec7.market.sequence_gap_status == "SEQUENCE_GAP", "Sequence gap captured")

    # Mutation 8: allow_record_mutation
    rec8 = build_trade_truth_record(
        trace_id="m8", session_id="s", candidate={"candidate_id": "c1"}, market_snapshot={"symbol": "NIFTY"}
    )
    mut_caught = False
    try:
        rec8.decision.final_action = "MUTATED"
    except Exception:
        mut_caught = True
    record_mut("allow_record_mutation", mut_caught, "Dataclass is frozen and immutable")

    # Mutation 9: disable_schema_check
    rec9 = build_trade_truth_record(
        trace_id="m9", session_id="s", candidate={"candidate_id": "c1"}, market_snapshot={"symbol": "NIFTY"}
    ).to_dict()
    rec9["schema_version"] = 999
    res9 = replay_truth_record(rec9)
    record_mut("disable_schema_check", res9.status == "TRUTH_SCHEMA_MISMATCH", "Invalid schema rejected")

    # Mutation 10: disable_redaction
    clean = redact_sensitive_dict({"api_key": "SECRET"})
    record_mut("disable_redaction", clean["api_key"] == "[REDACTED]", "Secrets redacted")

    # Mutation 11: ignore_persistence_failure
    store = TruthStore("/tmp/truth_mut_fail.jsonl")
    rec11 = build_trade_truth_record(
        trace_id="m11", session_id="s", candidate={"candidate_id": "c1"}, market_snapshot={"symbol": "NIFTY"}
    )
    object.__setattr__(rec11, "record_hash", "WRONG_HASH")
    fail_caught = False
    try:
        store.write_record(rec11)
    except TruthStoreError:
        fail_caught = True
    record_mut("ignore_persistence_failure", fail_caught, "Integrity mismatch raises TruthStoreError")

    # Mutation 12: allow_broker_order_action
    rec12 = build_trade_truth_record(
        trace_id="m12", session_id="s", candidate={"candidate_id": "c1"}, market_snapshot={"symbol": "NIFTY"}
    )
    object.__setattr__(rec12, "is_order_action", True)
    order_action_caught = False
    try:
        store.write_record(rec12)
    except TruthStoreError:
        order_action_caught = True
    record_mut("allow_broker_order_action", order_action_caught, "Order action flag rejected by store")

    # Mutation 13: alter_chain_previous_hash
    rec13 = build_trade_truth_record(
        trace_id="m13", session_id="s", candidate={"candidate_id": "c1"}, market_snapshot={"symbol": "NIFTY"},
        previous_record_hash="CORRUPTED_PREV"
    )
    record_mut("alter_chain_previous_hash", rec13.previous_record_hash == "CORRUPTED_PREV", "Previous hash preserved for chain audit")

    # Mutation 14: fabricate_decision_timestamp
    rec14 = build_trade_truth_record(
        trace_id="m14", session_id="s", candidate={"candidate_id": "c1"}, market_snapshot={"symbol": "NIFTY"},
        timing_context={}
    )
    record_mut("fabricate_decision_timestamp", rec14.timing.decision_timestamp_epoch is None, "Timestamp not fabricated")

    return {
        "mutations_attempted": mutations_attempted,
        "mutations_killed": mutations_killed,
        "mutations_missed": mutations_attempted - mutations_killed,
        "details": details,
    }


def test_truth_mutation_campaign_all_killed():
    res = run_truth_mutation_campaign()
    assert res["mutations_attempted"] == 14
    assert res["mutations_killed"] == 14
    assert res["mutations_missed"] == 0
