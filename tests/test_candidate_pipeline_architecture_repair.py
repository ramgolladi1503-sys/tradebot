"""Deterministic unit tests for candidate qualification boundaries.

The primitive rows below are test fixtures only. They are not market replay,
live-market, latency, or strategy-performance evidence.
"""
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from core.causal_pulse import create_native_pulse
from core.causal_strategy_harness import (
    ApplicabilityState,
    ExecutionState,
    QualificationState,
    evaluate_causal_strategies,
)
from core.cas_primitive_producer import CASPrimitiveStore
from core.read_only_strategy_registry import CANONICAL_STRATEGIES


IST = ZoneInfo("Asia/Kolkata")
SOURCE_SHA = "a" * 40
SESSION_ID = "cas-unit-fixture"
TOKEN = 81234


def _cas_store(tmp_path, *, prices=(100.0, 99.0)):
    store = CASPrimitiveStore(
        tmp_path / "cas-fixture.json",
        session_id=SESSION_ID,
        source_sha=SOURCE_SHA,
        underlying_token=TOKEN,
    )
    target_times = {
        "0915": datetime(2026, 1, 5, 9, 15, tzinfo=IST),
        "1000": datetime(2026, 1, 5, 10, 0, tzinfo=IST),
    }
    for (name, target), price in zip(target_times.items(), prices, strict=True):
        target_epoch = target.timestamp()
        selected_epoch = target_epoch + 0.5
        tick = {
            "underlying_symbol": "NIFTY",
            "instrument_token": TOKEN,
            "timestamp_authority": "EXCHANGE_TIMESTAMP",
            "timestamp_source_field": "exchange_timestamp",
            "timestamp_epoch": selected_epoch,
            "source_timestamp_epoch": selected_epoch,
            "receive_timestamp_epoch": selected_epoch + 0.05,
            "timestamp_fallback_used": False,
            "last_price": price,
        }
        store.capture(
            name,
            target_epoch,
            tick,
            capture_timestamp_ist=datetime.fromtimestamp(selected_epoch, tz=IST).isoformat(),
        )
    return store


def _pulse(*, sequence=1, timestamp=None):
    decision_time = timestamp or datetime(2026, 1, 5, 15, 14, 0, 500000, tzinfo=IST)
    return create_native_pulse(
        session_id=SESSION_ID,
        sequence_num=sequence,
        timestamp_epoch=decision_time.timestamp(),
        payload={"unit_fixture": True},
        producer_sha=SOURCE_SHA,
    )


def _feed(symbol="NIFTY", *, confidence=0.95, direction="BUY", age=0.5, **extra):
    return {
        "websocket_ok": True,
        "symbols": [{
            "symbol": symbol,
            "feed_ok": age is not None and age <= 2.5,
            "instrument_token": TOKEN,
            "option_last_tick_age_sec": age,
            "confidence": confidence,
            "direction": direction,
            "ltp": 25000.0,
            **extra,
        }],
    }


def test_generic_confidence_and_completed_bar_cannot_create_cas_candidate():
    result = evaluate_causal_strategies(
        pulse=_pulse(),
        market_snapshot=None,
        feed_health_truth=_feed(is_completed_bar_signal=True, signal_mode="COMPLETED_BARS"),
    )

    assert result.candidates == []
    observation = result.observations[0]
    assert observation.qualification_state is QualificationState.UNKNOWN
    assert observation.reason_code == "CAS_PRIMITIVE_STORE_UNAVAILABLE"
    assert observation.source_event_or_snapshot_reference["generic_signal_used_for_qualification"] is False


def test_registry_is_the_only_symbol_applicability_authority(tmp_path):
    store = _cas_store(tmp_path)
    result = evaluate_causal_strategies(
        pulse=_pulse(),
        market_snapshot=None,
        feed_health_truth=_feed("NIFTY26JAN25000CE"),
        cas_primitive_store=store,
    )

    assert result.candidates == []
    assert result.observations[0].applicability_state is ApplicabilityState.INAPPLICABLE
    assert result.observations[0].reason_code == "REGISTRY_SYMBOL_NOT_APPLICABLE"


def test_verified_cas_qualification_creates_advisory_candidate_independent_of_feed_execution(tmp_path):
    store = _cas_store(tmp_path)
    result = evaluate_causal_strategies(
        pulse=_pulse(),
        market_snapshot=None,
        feed_health_truth=_feed(age=5.0),
        cas_primitive_store=store,
    )

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.strategy_id == "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1"
    assert candidate.strategy_qualified is True
    assert candidate.candidate_state.value == "QUALIFIED"
    assert candidate.execution_state is ExecutionState.ADVISORY_ONLY_FEED_STALE
    assert candidate.execution_eligible is False
    assert result.executable_candidates == []
    assert candidate.direction == "BUY"
    assert candidate.entry_price is None
    assert candidate.stop_loss is None
    assert candidate.target_price is None


def test_qualification_evidence_contains_strategy_identity_and_both_verified_primitives(tmp_path):
    store = _cas_store(tmp_path)
    candidate = evaluate_causal_strategies(
        pulse=_pulse(),
        market_snapshot=None,
        feed_health_truth=_feed(),
        cas_primitive_store=store,
    ).candidates[0]

    evidence = candidate.qualification_evidence
    assert evidence["evaluator"] == "core.cas_morning_reversal_advisory.evaluate"
    assert evidence["canonical_decision"]["strategy_id"] == candidate.strategy_id
    assert evidence["canonical_decision"]["read_only"] is True
    assert evidence["strategy_id"] == candidate.strategy_id
    assert len(evidence["spec_sha"]) == 64
    assert evidence["source_sha"] == SOURCE_SHA
    assert evidence["session_id"] == SESSION_ID
    assert evidence["signal_input_09_15"] == 100.0
    assert evidence["signal_input_10_00"] == 99.0
    assert set(evidence["primitive_references"]) == {"0915", "1000"}
    assert all(len(row["record_sha256"]) == 64 for row in evidence["primitive_references"].values())
    assert all(row["primitive"]["immutable"] is True for row in evidence["primitive_references"].values())
    assert evidence["broker_write_authority"] is False
    assert evidence["order_authority"] is False
    assert evidence["live_execution_authorized"] is False


def test_registry_required_feeds_match_canonical_cas_evidence(tmp_path):
    declaration = next(
        item for item in CANONICAL_STRATEGIES
        if item["strategy_id"] == "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1"
    )
    candidate = evaluate_causal_strategies(
        pulse=_pulse(),
        market_snapshot=None,
        feed_health_truth=_feed(),
        cas_primitive_store=_cas_store(tmp_path),
    ).candidates[0]

    assert declaration["required_feeds"] == ("SPOT",)
    # The evaluator's two verified NIFTY price primitives constitute SPOT
    # evidence; the CAS contract does not consume or claim a FUTURES feed.
    assert set(candidate.qualification_evidence["primitive_references"]) == {"0915", "1000"}
    assert candidate.qualification_evidence["registry_declaration"]["required_feeds"] == ("SPOT",)


def test_missing_prices_remain_unknown_and_do_not_create_candidate(tmp_path):
    store = _cas_store(tmp_path)
    store.rows["1000"]["price"] = None
    result = evaluate_causal_strategies(
        pulse=_pulse(),
        market_snapshot=None,
        feed_health_truth=_feed(),
        cas_primitive_store=store,
    )

    assert result.candidates == []
    assert result.observations[0].qualification_state is QualificationState.UNKNOWN
    assert result.observations[0].reason_code.startswith("CAS_PRIMITIVE_")


def test_fresh_feed_does_not_claim_execution_readiness(tmp_path):
    result = evaluate_causal_strategies(
        pulse=_pulse(),
        market_snapshot=None,
        feed_health_truth=_feed(age=0.5),
        cas_primitive_store=_cas_store(tmp_path),
    )
    candidate = result.candidates[0]

    assert candidate.execution_state is ExecutionState.ADVISORY_ONLY_FEED_FRESH
    assert candidate.execution_eligible is False
    assert result.to_dict()["executable_candidates"] == []
    assert result.to_dict()["allowed_for_live_execution"] is False


def test_2_5_second_freshness_boundary_is_preserved(tmp_path):
    at_limit = evaluate_causal_strategies(
        pulse=_pulse(),
        market_snapshot=None,
        feed_health_truth=_feed(age=2.5),
        cas_primitive_store=_cas_store(tmp_path / "at-limit"),
    )
    over_limit = evaluate_causal_strategies(
        pulse=_pulse(sequence=2),
        market_snapshot=None,
        feed_health_truth=_feed(age=2.500001),
        cas_primitive_store=_cas_store(tmp_path / "over-limit"),
    )

    assert at_limit.candidates[0].execution_state is ExecutionState.ADVISORY_ONLY_FEED_FRESH
    assert over_limit.candidates[0].execution_state is ExecutionState.ADVISORY_ONLY_FEED_STALE
    assert at_limit.executable_candidates == over_limit.executable_candidates == []


def test_cas_receipt_later_than_two_seconds_after_cutoff_fails_closed(tmp_path):
    pulse = _pulse()
    late_receipt = datetime(2026, 1, 5, 15, 14, 2, 1000, tzinfo=IST)
    pulse = replace(pulse, timestamp_ist=late_receipt.isoformat())
    result = evaluate_causal_strategies(
        pulse=pulse,
        market_snapshot=None,
        feed_health_truth=_feed(),
        cas_primitive_store=_cas_store(tmp_path),
    )

    assert result.candidates == []
    assert result.observations[0].qualification_state is QualificationState.UNKNOWN
    assert result.observations[0].reason_code == "CAS_EVALUATION_NOT_ADMISSIBLE"


def test_advisory_candidate_and_result_never_grant_broker_or_order_authority(tmp_path):
    result = evaluate_causal_strategies(
        pulse=_pulse(),
        market_snapshot=None,
        feed_health_truth=_feed(),
        cas_primitive_store=_cas_store(tmp_path),
    )
    payload = result.to_dict()
    candidate = payload["candidates"][0]

    assert payload["broker_write_authority"] is False
    assert payload["order_authority"] is False
    assert payload["allowed_for_live_execution"] is False
    assert payload["orders_placed"] == 0
    assert candidate["read_only"] is True
    assert candidate["is_order_action"] is False
    assert candidate["broker_api_called"] is False
    assert candidate["broker_write_authority"] is False
    assert candidate["order_authority"] is False
    assert candidate["allowed_for_live_execution"] is False


def test_telemetry_is_derived_from_observations_and_candidates(tmp_path):
    result = evaluate_causal_strategies(
        pulse=_pulse(),
        market_snapshot=None,
        feed_health_truth=_feed(),
        cas_primitive_store=_cas_store(tmp_path),
    )
    telemetry = result.telemetry_counters

    assert telemetry["strategy_observations"] == len(result.observations)
    assert telemetry["qualified_candidates"] == len(result.candidates)
    assert telemetry["execution_eligible_candidates"] == len(result.executable_candidates) == 0
