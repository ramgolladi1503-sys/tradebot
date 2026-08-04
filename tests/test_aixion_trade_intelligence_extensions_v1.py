from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from aixion_trade_intelligence.evidence_search import EvidenceIndex
from aixion_trade_intelligence.outcomes import (
    MarketObservation,
    OutcomeContract,
    build_causal_outcomes,
)
from aixion_trade_intelligence.tradebot_adapter import (
    candidate_lineage_to_event,
    truth_snapshot_to_event,
)


BASE = datetime(2026, 8, 5, 3, 45, tzinfo=timezone.utc)


def test_candidate_adapter_preserves_explicit_authority_and_identity():
    row = {
        "timestamp": BASE.isoformat(),
        "available_time": (BASE - timedelta(milliseconds=10)).isoformat(),
        "source_time": (BASE - timedelta(milliseconds=20)).isoformat(),
        "cycle_id": "cycle-1",
        "candidate_id": "candidate-1",
        "stage": "candidate_created",
        "instrument_id": "NSE_FO|123",
        "strategy_name": "MEG",
        "strategy_version": "1.2.3",
        "authority_class": "TRADEBOT_DERIVED",
        "data_quality_state": "VALID",
    }
    event = candidate_lineage_to_event(
        row,
        session_id="session-1",
        run_id="run-1",
        receive_time=BASE + timedelta(milliseconds=1),
        persist_time=BASE + timedelta(milliseconds=2),
        producer_sequence=1,
    )
    assert event.event_type == "CANDIDATE_CREATED"
    assert event.candidate_id == "candidate-1"
    assert event.instrument_key == "NSE_FO|123"
    assert event.strategy_id == "MEG"
    assert event.available_time <= event.event_time


def test_candidate_adapter_rejects_unknown_stage():
    with pytest.raises(ValueError, match="unsupported_stage"):
        candidate_lineage_to_event(
            {"timestamp": BASE.isoformat(), "stage": "magic_stage"},
            session_id="session-1",
            run_id="run-1",
            receive_time=BASE,
            persist_time=BASE,
            producer_sequence=1,
        )


def test_truth_adapter_rejects_non_truth_event():
    with pytest.raises(ValueError, match="unsupported_truth_event_type"):
        truth_snapshot_to_event(
            {},
            event_type="ORDER_EVENT",
            session_id="session-1",
            run_id="run-1",
            source_component="fixture",
            event_time=BASE,
            receive_time=BASE,
            persist_time=BASE,
            producer_sequence=1,
        )


def test_long_option_outcome_uses_next_ask_and_bid_exit():
    contract = OutcomeContract(
        candidate_id="c-1",
        instrument_key="NSE_FO|123",
        decision_time=BASE,
        direction="LONG",
        horizons=(timedelta(seconds=30), timedelta(minutes=1)),
        quantity=65,
    )
    observations = [
        MarketObservation(
            "NSE_FO|123",
            BASE + timedelta(seconds=1),
            BASE + timedelta(seconds=2),
            bid=99.0,
            ask=101.0,
            last=100.0,
        ),
        MarketObservation(
            "NSE_FO|123",
            BASE + timedelta(seconds=25),
            BASE + timedelta(seconds=26),
            bid=104.0,
            ask=105.0,
            last=104.5,
        ),
        MarketObservation(
            "NSE_FO|123",
            BASE + timedelta(seconds=55),
            BASE + timedelta(seconds=56),
            bid=102.0,
            ask=103.0,
            last=102.5,
        ),
    ]
    outcomes = build_causal_outcomes(contract, observations)
    assert outcomes[0]["entry_price"] == 101.0
    assert outcomes[0]["entry_side"] == "ASK"
    assert outcomes[0]["exit_price"] == 104.0
    assert outcomes[0]["exit_side"] == "BID"
    assert outcomes[0]["pnl"] == pytest.approx((104.0 - 101.0) * 65)
    assert outcomes[0]["mfe_return"] == pytest.approx(104.0 / 101.0 - 1.0)
    assert outcomes[1]["exit_price"] == 102.0


def test_short_outcome_uses_bid_entry_and_ask_exit():
    contract = OutcomeContract(
        candidate_id="c-2",
        instrument_key="NSE_FO|124",
        decision_time=BASE,
        direction="SHORT",
        horizons=(timedelta(seconds=30),),
    )
    observations = [
        MarketObservation(
            "NSE_FO|124",
            BASE + timedelta(seconds=1),
            BASE + timedelta(seconds=2),
            bid=100.0,
            ask=102.0,
        ),
        MarketObservation(
            "NSE_FO|124",
            BASE + timedelta(seconds=20),
            BASE + timedelta(seconds=21),
            bid=95.0,
            ask=96.0,
        ),
    ]
    outcome = build_causal_outcomes(contract, observations)[0]
    assert outcome["entry_price"] == 100.0
    assert outcome["exit_price"] == 96.0
    assert outcome["pnl"] == pytest.approx(4.0)


def test_outcome_fails_without_executable_quote_side():
    contract = OutcomeContract(
        candidate_id="c-3",
        instrument_key="NSE_FO|125",
        decision_time=BASE,
        direction="LONG",
        horizons=(timedelta(seconds=30),),
    )
    observations = [
        MarketObservation(
            "NSE_FO|125",
            BASE + timedelta(seconds=1),
            BASE + timedelta(seconds=2),
            bid=100.0,
            last=101.0,
        )
    ]
    with pytest.raises(ValueError, match="missing_causal_ask_entry"):
        build_causal_outcomes(contract, observations)


def test_evidence_index_retrieves_exact_artifact_and_filters(tmp_path):
    first = tmp_path / "session_analysis.json"
    first.write_text(
        json.dumps(
            {
                "study_id": "AIXION_V1",
                "session_id": "session-1",
                "verdict": "INVALID_DATA_QUALITY",
                "summary": "stale option depth blocked candidates",
            }
        ),
        encoding="utf-8",
    )
    second = tmp_path / "other.md"
    second.write_text("normal session with no incident", encoding="utf-8")
    index = EvidenceIndex.from_paths([first, second])
    results = index.search(
        "stale option depth",
        metadata_filters={"session_id": "session-1"},
    )
    assert results[0]["source_path"] == first.as_posix()
    assert results[0]["matched_terms"] == ["depth", "option", "stale"]
    assert results[1:] == []


def test_evidence_index_refuses_empty_query(tmp_path):
    path = tmp_path / "evidence.md"
    path.write_text("evidence", encoding="utf-8")
    index = EvidenceIndex.from_paths([path])
    with pytest.raises(ValueError, match="empty_query"):
        index.search("   ")
