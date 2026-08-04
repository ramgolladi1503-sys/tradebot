from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from aixion_trade_intelligence.contracts import EventValidationError
from aixion_trade_intelligence.market_adapters import market_tick_to_event, option_chain_snapshot_to_events
from aixion_trade_intelligence.runtime_tailer import RuntimeEvidenceTailer, RuntimeTailerConfig
from aixion_trade_intelligence.session import SessionAnalyzer
from aixion_trade_intelligence.storage import iter_events
from aixion_trade_intelligence.tradebot_adapter import candidate_lineage_to_event


UTC = timezone.utc
BASE = datetime(2026, 8, 5, 3, 45, tzinfo=UTC)


def test_market_tick_and_option_chain_adapters_preserve_truth() -> None:
    event = market_tick_to_event(
        {
            "instrument_key": "NSE_FO|123",
            "exchange_timestamp": BASE.isoformat(),
            "available_time": (BASE + timedelta(milliseconds=1)).isoformat(),
            "bid": 99,
            "ask": 101,
            "last": 100,
            "volume": 1000,
            "oi": 500,
            "bid_depth": [{"price": 99, "quantity": 65}],
            "ask_depth": [{"price": 101, "quantity": 130}],
        },
        session_id="s",
        run_id="r",
        receive_time=BASE + timedelta(milliseconds=1),
        persist_time=BASE + timedelta(milliseconds=2),
        producer_sequence=1,
        source_provider="UPSTOX",
        source_component="fixture",
    )
    assert event.payload["bid_depth"][0]["quantity"] == 65
    assert event.event_time <= event.available_time <= event.persist_time
    events = option_chain_snapshot_to_events(
        {
            "snapshot_id": "chain-1",
            "event_time": BASE.isoformat(),
            "contracts": [
                {"instrument_key": "NSE_FO|CE", "bid": 100, "ask": 101, "strike": 25000, "option_type": "CE"},
                {"instrument_key": "NSE_FO|PE", "bid": 90, "ask": 91, "strike": 25000, "option_type": "PE"},
            ],
        },
        session_id="s",
        run_id="r",
        receive_time=BASE + timedelta(milliseconds=1),
        persist_time=BASE + timedelta(milliseconds=2),
        starting_sequence=10,
        source_provider="KITE",
        source_component="fixture",
    )
    assert [item.instrument_key for item in events] == ["NSE_FO|CE", "NSE_FO|PE"]
    assert all(item.event_time <= item.available_time for item in events)


def test_market_tick_rejects_impossible_pre_event_availability() -> None:
    with pytest.raises(EventValidationError, match="observation_available_before_event_time"):
        market_tick_to_event(
            {
                "instrument_key": "NSE_FO|123",
                "exchange_timestamp": BASE.isoformat(),
                "available_time": (BASE - timedelta(milliseconds=1)).isoformat(),
                "bid": 99,
                "ask": 101,
            },
            session_id="s",
            run_id="r",
            receive_time=BASE + timedelta(milliseconds=1),
            persist_time=BASE + timedelta(milliseconds=2),
            producer_sequence=1,
            source_provider="UPSTOX",
            source_component="fixture",
        )


def test_raw_candidate_stage_is_normalized() -> None:
    event = candidate_lineage_to_event(
        {
            "timestamp": BASE.isoformat(),
            "cycle_id": "cycle-1",
            "candidate_id": "c-1",
            "stage": "tradebuilder",
            "stage_status": "passed",
            "instrument_id": "NSE_FO|123",
        },
        session_id="s",
        run_id="r",
        receive_time=BASE + timedelta(milliseconds=1),
        persist_time=BASE + timedelta(milliseconds=2),
        producer_sequence=1,
    )
    assert event.event_type == "CANDIDATE_CREATED"
    assert event.available_time <= event.event_time


def test_runtime_tailer_reads_only_current_session_truth(tmp_path) -> None:
    runtime_events = tmp_path / "events.jsonl"
    candidate_events = tmp_path / "candidate.jsonl"
    market_snapshot = tmp_path / "market.json"
    runtime_events.write_text("", encoding="utf-8")
    candidate_events.write_text("", encoding="utf-8")
    market_snapshot.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": (BASE - timedelta(seconds=10)).isoformat(),
                "source": "engine",
                "market_open": True,
                "symbols": {},
                "warnings": [],
                "producer_meta": {"compute_ms": 1, "loop_id": "old"},
            }
        ),
        encoding="utf-8",
    )
    config = RuntimeTailerConfig(
        enabled=True,
        observation_mode="SHADOW",
        output_root=tmp_path / "out",
        poll_seconds=0.01,
        start_at_end=True,
        fsync=False,
        session_id="session-1",
        run_id="run-1",
    )
    current = [BASE]
    tailer = RuntimeEvidenceTailer(
        config=config,
        runtime_events_path=runtime_events,
        candidate_lineage_path=candidate_events,
        market_snapshot_path=market_snapshot,
        clock=lambda: current[0],
    )
    tailer._publish_lifecycle("SESSION_STARTED")
    runtime_events.write_text(
        json.dumps(
            {
                "ts": (BASE + timedelta(seconds=1)).isoformat(),
                "type": "feed_truth_updated",
                "event_id": "runtime-1",
                "payload": {"data_quality_state": "VALID"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    candidate_events.write_text(
        json.dumps(
            {
                "timestamp": (BASE + timedelta(seconds=2)).isoformat(),
                "cycle_id": "cycle-1",
                "candidate_id": "candidate-1",
                "stage": "tradebuilder",
                "stage_status": "passed",
                "instrument_id": "NSE_FO|123",
                "data_quality_state": "VALID",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    market_snapshot.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": (BASE + timedelta(seconds=3)).isoformat(),
                "source": "engine",
                "market_open": True,
                "symbols": {},
                "warnings": [],
                "producer_meta": {"compute_ms": 1, "loop_id": "current"},
            }
        ),
        encoding="utf-8",
    )
    current[0] = BASE + timedelta(seconds=4)
    tailer.poll_once()
    current[0] = BASE + timedelta(seconds=5)
    tailer._publish_lifecycle("SESSION_ENDED")
    output = config.output_root / config.session_id / "events.jsonl"
    events = list(iter_events(output))
    event_types = [event.event_type for event in events]
    assert {
        "SESSION_STARTED",
        "FEED_TRUTH_UPDATED",
        "CANDIDATE_CREATED",
        "MARKET_SNAPSHOT",
        "SESSION_ENDED",
    }.issubset(event_types)
    assert all(event.event_time >= BASE for event in events)
    analysis = SessionAnalyzer().analyze(events)
    assert analysis.manifest["lifecycle_order_valid"] is True
    assert analysis.manifest["valid"] is True
    status = json.loads(tailer.status_path.read_text(encoding="utf-8"))
    assert status["broker_authority"] is False
    assert status["read_only"] is True
