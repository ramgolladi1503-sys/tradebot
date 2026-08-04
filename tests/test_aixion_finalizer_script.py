from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import subprocess
import sys
import uuid

from aixion_trade_intelligence.contracts import CanonicalEvent
from aixion_trade_intelligence.storage import append_events, load_events, write_events


def _event(
    *, event_type: str, sequence: int, at: datetime, producer_id: str, session_id: str,
    payload: dict, instrument_key: str = "", candidate_id: str = "",
    strategy_id: str = "", strategy_version: str = "",
) -> CanonicalEvent:
    available = at + timedelta(milliseconds=5)
    return CanonicalEvent(
        event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:{producer_id}:{sequence}:{event_type}")),
        event_type=event_type, session_id=session_id, run_id=session_id, trace_id=session_id,
        producer_id=producer_id, producer_sequence=sequence, source_component="test.finalizer",
        source_provider="OFFLINE_TEST", event_time=at, source_time=at, receive_time=available,
        available_time=available, parse_time=available, persist_time=available,
        instrument_key=instrument_key, underlying="NIFTY", candidate_id=candidate_id,
        strategy_id=strategy_id, strategy_version=strategy_version,
        data_quality_state="VALIDATED_TEST", authority_class="TEST_EVIDENCE", payload=payload,
    )


def test_deferred_session_can_be_augmented_and_finalized(tmp_path: Path):
    session_id = "deferred-finalizer-test"; start = datetime.now(timezone.utc) - timedelta(minutes=10)
    decision = start + timedelta(minutes=1); underlying = "NSE_INDEX|Nifty 50"; option = "NSE_FO|TEST_CE"; candidate = "candidate-1"
    contract = {"horizons_seconds": [30], "entry_delay_seconds": [0], "underlying_instrument": underlying, "selected_option_instrument": option}
    initial = [
        _event(event_type="SESSION_STARTED", sequence=1, at=start, producer_id="observer", session_id=session_id, payload={"expected_event_types": []}),
        _event(event_type="CANDIDATE_CREATED", sequence=1, at=decision, producer_id="candidate-lineage", session_id=session_id, candidate_id=candidate, strategy_id="TEST_STRATEGY", strategy_version="1.0.0", instrument_key=option, payload={"direction": "BUY_CALL", "underlying_instrument": underlying, "selected_option_instrument": option, "outcome_contract": contract}),
        _event(event_type="OBSERVER_STOPPED", sequence=2, at=decision + timedelta(seconds=1), producer_id="observer", session_id=session_id, payload={"finalization_deferred": True}),
    ]
    evidence = tmp_path / "events.jsonl"; write_events(evidence, initial)
    quotes = [
        _event(event_type="MARKET_QUOTE", sequence=1, at=decision, producer_id="upstox-market-data", session_id=session_id, instrument_key=underlying, payload={"ltp": 24500.0}),
        _event(event_type="MARKET_QUOTE", sequence=2, at=decision, producer_id="upstox-market-data", session_id=session_id, instrument_key=option, payload={"bid": 99.0, "ask": 100.0, "ltp": 99.5}),
        _event(event_type="MARKET_QUOTE", sequence=3, at=decision + timedelta(seconds=30), producer_id="upstox-market-data", session_id=session_id, instrument_key=underlying, payload={"ltp": 24510.0}),
        _event(event_type="MARKET_QUOTE", sequence=4, at=decision + timedelta(seconds=30), producer_id="upstox-market-data", session_id=session_id, instrument_key=option, payload={"bid": 104.0, "ask": 105.0, "ltp": 104.5}),
    ]
    append_events(evidence, quotes); output_dir = tmp_path / "report"
    result = subprocess.run([sys.executable, "scripts/finalize_trade_intelligence_session.py", "--events", str(evidence), "--output-dir", str(output_dir)], cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=True)
    payload = json.loads(result.stdout); assert payload["pipeline_certified"] is True; assert payload["outcome_count"] == 1
    events = load_events(evidence); assert sum(event.event_type == "SESSION_ENDED" for event in events) == 1
    certification = json.loads((output_dir / "certification.json").read_text(encoding="utf-8")); assert certification["verdict"] == "PIPELINE_OFFLINE_CERTIFIED"
    report = json.loads((output_dir / "session_report.json").read_text(encoding="utf-8")); assert report["outcomes"][0]["classification"] == "FULL_TRADE_CORRECT"


def test_finalizer_is_idempotent_for_already_finalized_session(tmp_path: Path):
    session_id = "already-finalized"; start = datetime.now(timezone.utc) - timedelta(minutes=1); evidence = tmp_path / "events.jsonl"
    write_events(evidence, [
        _event(event_type="SESSION_STARTED", sequence=1, at=start, producer_id="p", session_id=session_id, payload={}),
        _event(event_type="MARKET_QUOTE", sequence=2, at=start + timedelta(seconds=1), producer_id="p", session_id=session_id, instrument_key="NSE_INDEX|Nifty 50", payload={"ltp": 24500.0}),
        _event(event_type="SESSION_ENDED", sequence=3, at=start + timedelta(seconds=1), producer_id="p", session_id=session_id, payload={"expected_producer_counts": {"p": 3}}),
    ])
    output_dir = tmp_path / "report"; cmd = [sys.executable, "scripts/finalize_trade_intelligence_session.py", "--events", str(evidence), "--output-dir", str(output_dir)]
    first = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=True)
    second = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=True)
    assert json.loads(first.stdout)["pipeline_certified"] is True; assert json.loads(second.stdout)["pipeline_certified"] is True
    assert sum(event.event_type == "SESSION_ENDED" for event in load_events(evidence)) == 1
