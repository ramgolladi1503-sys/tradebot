from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from core.causal_pulse import NativePulseTracker
from core.causal_shadow_decision import ShadowDecisionResult
from core.causal_strategy_harness import CausalCandidate, StrategyEvaluationResult
from core.causal_trade_truth_emitter import build_canonical_trade_truth
from core.observation_lineage import (
    build_observation_lineage_record,
    compare_snapshot_tick_event_ids,
    current_tick_store_lineage,
    snapshot_tick_lineage,
    verify_observation_lineage_record,
)


def _build(snapshot, process_local=None):
    feed = {"feed_state": "RUNNING", "observed": True}
    from core.causal_pulse import sha256_canonical

    process_lineage = process_local if process_local is not None else current_tick_store_lineage([])
    tick_lineage = snapshot_tick_lineage(snapshot)
    pulse_input = {
        "cycle_count": 1,
        "interval_end_epoch": 10.0,
        "market_open": True,
        "feed_live": True,
        "market_snapshot_sha256": sha256_canonical(snapshot),
        "tick_lineage": tick_lineage,
        "process_local_tick_lineage": process_lineage,
        "tick_store_snapshot_correlation": compare_snapshot_tick_event_ids(tick_lineage, process_lineage),
        "feed_health_truth_sha256": sha256_canonical(feed),
    }
    pulse = NativePulseTracker("run-1", "a" * 40).next_pulse(pulse_input, timestamp_epoch=10.0)
    candidate = CausalCandidate(
        candidate_id="cand-1", pulse_id=pulse.pulse_id, strategy_id="strategy-1",
        symbol="NIFTY", instrument_token=256265, direction="BUY", entry_price=100.0,
        stop_loss=95.0, target_price=110.0, regime="UNKNOWN", confidence=0.5,
        timestamp_epoch=10.0, timestamp_ist="1970-01-01T05:30:10+05:30",
        payload_sha256="b" * 64,
    )
    strategy = StrategyEvaluationResult(
        pulse_id=pulse.pulse_id, regime="UNKNOWN", candidates=[candidate],
        rejections=[], evaluated_symbol_count=1, timestamp_epoch=10.0,
    )
    decisions = ShadowDecisionResult(
        pulse_id=pulse.pulse_id, selected_candidates=[candidate], rejected_decisions=[],
        risk_verdict="OBSERVATION_ONLY", timestamp_epoch=10.0,
    )
    truth = build_canonical_trade_truth(
        pulse=pulse, market_snapshot=snapshot, feed_health_truth=feed,
        strategy_result=strategy, decision_result=decisions,
    )
    record = build_observation_lineage_record(
        pulse=pulse, pulse_input=pulse_input, market_snapshot=snapshot,
        feed_health_truth=feed, strategy_result=strategy,
        process_local_tick_lineage=process_lineage,
        decision_result=decisions, trade_truth_record=truth,
    )
    return record, pulse, strategy, decisions, truth, pulse_input, feed


def test_lineage_record_closes_tick_snapshot_pulse_candidate_decision_and_truth():
    source_payload = {
        "instrument_token": 256265,
        "underlying_symbol": "NIFTY",
        "last_price": 100.0,
        "volume": 1,
        "oi": 2,
        "source_timestamp_field": "exchange_timestamp",
        "source_timestamp_epoch": 8.0,
    }
    source_hash = hashlib.sha256(json.dumps(source_payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    snapshot = {"snapshot_id": "snapshot-1", "ticks": {"index": {
        "instrument_token": 256265, "timestamp_epoch": 8.0,
        "last_price": 100.0,
        "timestamp_authority": "EXCHANGE_TIMESTAMP", "source_timestamp_epoch": 8.0,
        "receive_timestamp_epoch": 8.1, "timestamp_fallback_used": False,
        "timestamp_source_field": "exchange_timestamp",
        "source_event_id": f"feed-1:1:256265:{source_hash[:16]}",
        "source_event_sha256": source_hash, "source_event_payload": source_payload,
    }, "options": {}}}
    record, *_ = _build(snapshot)
    valid, errors = verify_observation_lineage_record(record)
    assert valid, errors
    assert record["tick_lineage"]["ticks"]["256265"]["event_identity_status"] == "VERIFIED_EVENT_PAYLOAD"
    assert record["strategy_candidates"] == record["selected_candidate_ids"] == ["cand-1"]
    assert record["trade_truth_pulse_id"] == record["pulse_id"]
    assert record["authority"]["allowed_for_live_execution"] is False


def test_lineage_keeps_missing_tick_identity_unknown_and_rejects_mutation():
    snapshot = {"ticks": {"index": {"instrument_token": 256265, "timestamp_epoch": 8.0}, "options": {}}}
    record, *_ = _build(snapshot)
    assert record["tick_lineage"]["ticks"]["256265"]["event_identity_status"] == "UNKNOWN_EVENT_ID_UNAVAILABLE"
    valid, errors = verify_observation_lineage_record(record)
    assert valid, errors

    changed = dict(record)
    changed["tick_lineage"] = {"status": "TICK_IDENTITIES_PRESENT", "ticks": {}}
    valid, errors = verify_observation_lineage_record(changed)
    assert not valid
    assert "TICK_LINEAGE_MISMATCH" in errors

    record, *_ = _build({"ticks": {"index": {
        "instrument_token": 256265, "timestamp_epoch": 8.0, "last_price": 100.0,
        "timestamp_authority": "EXCHANGE_TIMESTAMP", "timestamp_source_field": "exchange_timestamp",
        "source_timestamp_epoch": 8.0, "receive_timestamp_epoch": 8.1,
        "source_event_id": "feed:1:256265:abc", "source_event_sha256": "a" * 64,
        "source_event_payload": {"instrument_token": 256265, "last_price": 100.0,
            "source_timestamp_epoch": 8.0, "source_timestamp_field": "exchange_timestamp"},
    }, "options": {}}})
    valid, errors = verify_observation_lineage_record(record)
    assert not valid
    assert any(error.startswith("TICK_EVENT_BINDING_INVALID:") for error in errors)


def test_lineage_builder_rejects_output_linked_to_another_pulse():
    snapshot = {"ticks": {"index": {}, "options": {}}}
    record, pulse, strategy, decisions, truth, pulse_input, feed = _build(snapshot)
    wrong_decisions = replace(decisions, pulse_id="other-pulse")
    with pytest.raises(ValueError, match="LINEAGE_DECISION_PULSE_MISMATCH"):
        build_observation_lineage_record(
            pulse=pulse, pulse_input=pulse_input, market_snapshot=snapshot,
            feed_health_truth=feed, strategy_result=strategy,
            process_local_tick_lineage=current_tick_store_lineage([]),
            decision_result=wrong_decisions, trade_truth_record=truth,
        )


def test_independent_lineage_verifier_rejects_pulse_and_candidate_binding_mutations():
    record, *_ = _build({"ticks": {"index": {}, "options": {}}})
    changed_pulse = dict(record)
    changed_pulse["pulse"] = dict(record["pulse"], sequence_num=999)
    valid, errors = verify_observation_lineage_record(changed_pulse)
    assert not valid
    assert "PULSE_IDENTITY_INVALID" in errors

    changed_candidate = dict(record)
    changed_candidate["candidate_bindings"] = [{"candidate_id": "cand-1", "pulse_id": "wrong", "payload_sha256": "0" * 64}]
    valid, errors = verify_observation_lineage_record(changed_candidate)
    assert not valid
    assert "CANDIDATE_BINDINGS_PULSE_JOIN_MISMATCH" in errors


def test_process_local_tick_store_event_is_bound_into_pulse_record(monkeypatch, tmp_path):
    from config import config as cfg
    from core import tick_store

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "lineage_ticks.sqlite"), raising=False)
    monkeypatch.setattr(cfg, "TICK_STORE_ASYNC_DB_WRITES", False, raising=False)
    tick_store._INIT_DONE = False
    tick_store._LAST_TICK_BY_TOKEN.clear()
    source_payload = {
        "instrument_token": 256265, "underlying_symbol": "NIFTY", "last_price": 100.0,
        "volume": 1, "oi": 2, "source_timestamp_field": "exchange_timestamp",
        "source_timestamp_epoch": 8.0,
    }
    source_hash = hashlib.sha256(json.dumps(source_payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    assert tick_store.insert_tick(
        ts=8.0, token=256265, last_price=100.0,
        timestamp_authority="EXCHANGE_TIMESTAMP", timestamp_source_field="exchange_timestamp",
        source_timestamp_epoch=8.0, receive_timestamp_epoch=8.1, timestamp_fallback_used=False,
        source_event_id=f"feed-1:1:256265:{source_hash[:16]}",
        source_event_sha256=source_hash, source_event_payload=source_payload,
    )
    direct = current_tick_store_lineage([256265])
    assert direct["tokens"]["256265"]["event_identity_status"] == "VERIFIED_EVENT_PAYLOAD"
    assert direct["strategy_input_correlation"] == "UNKNOWN_UNLESS_SHARED_EVENT_ID_PRESENT"
    record, *_ = _build({"ticks": {"index": {}, "options": {}}}, process_local=direct)
    valid, errors = verify_observation_lineage_record(record)
    assert valid, errors
    assert record["process_local_tick_lineage"]["tokens"]["256265"]["source_event_id"] == f"feed-1:1:256265:{source_hash[:16]}"
    assert record["tick_store_snapshot_correlation"]["status"] == "UNKNOWN_NO_SHARED_VERIFIABLE_EVENT_IDS"
    snapshot = {"ticks": {"index": {
        "instrument_token": 256265, "last_price": 100.0, "timestamp_epoch": 8.0,
        "timestamp_authority": "EXCHANGE_TIMESTAMP", "timestamp_source_field": "exchange_timestamp",
        "source_timestamp_epoch": 8.0, "receive_timestamp_epoch": 8.1,
        "source_event_id": f"feed-1:1:256265:{source_hash[:16]}",
        "source_event_sha256": source_hash, "source_event_payload": source_payload,
    }, "options": {}}}
    matched_record, *_ = _build(snapshot, process_local=direct)
    assert matched_record["tick_store_snapshot_correlation"]["status"] == "VERIFIED_SHARED_EVENT_IDS"
    assert matched_record["tick_store_snapshot_correlation"]["matched_tokens"] == ["256265"]
