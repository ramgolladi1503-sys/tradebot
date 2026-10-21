from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aixion_trade_intelligence.contracts import CanonicalEvent
from aixion_trade_intelligence.storage import write_events


def _event(
    *,
    session_id: str,
    event_type: str,
    sequence: int,
    at: datetime,
    payload: dict,
    instrument_key: str = "",
    candidate_id: str = "",
    strategy_id: str = "",
    strategy_version: str = "",
    order_id: str = "",
) -> CanonicalEvent:
    receive = at + timedelta(milliseconds=4)
    parse = receive + timedelta(milliseconds=2)
    persist = parse + timedelta(milliseconds=2)
    return CanonicalEvent(
        event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:{sequence}:{event_type}:{instrument_key}:{candidate_id}")),
        event_type=event_type,
        session_id=session_id,
        run_id=session_id,
        cycle_id=f"cycle-{sequence:04d}",
        trace_id=session_id,
        producer_id="offline-fixture",
        producer_sequence=sequence,
        source_component="offline_fixture",
        source_provider="OFFLINE_VALIDATION",
        event_time=at,
        source_time=at,
        receive_time=receive,
        available_time=receive,
        parse_time=parse,
        persist_time=persist,
        instrument_key=instrument_key,
        underlying="NIFTY",
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        candidate_id=candidate_id,
        order_id=order_id,
        data_quality_state="VALIDATED_FIXTURE",
        authority_class="TEST_EVIDENCE",
        payload=payload,
    )


def build_fixture() -> list[CanonicalEvent]:
    session_id = "offline-certification-2026-08-04"
    start = datetime(2026, 8, 4, 9, 15, tzinfo=timezone(timedelta(hours=5, minutes=30))).astimezone(timezone.utc)
    underlying = "NSE_INDEX|Nifty 50"
    option = "NSE_FO|OFFLINE_ATM_CE"
    candidate = "candidate-offline-001"
    strategy = "OFFLINE_CAUSAL_CONTRACT"
    version = "1.0.0"

    specs: list[tuple[str, int, dict, str, str, str, str, str]] = []
    specs.append((
        "SESSION_STARTED", 0,
        {
            "declared_start": start.isoformat(),
            "declared_end": (start + timedelta(minutes=5)).isoformat(),
            "expected_instruments": [underlying, option],
            "expected_event_types": [
                "MARKET_QUOTE", "STRATEGY_EVALUATED", "SIGNAL_GENERATED", "CANDIDATE_CREATED",
                "APPROVAL_REQUESTED", "APPROVAL_DECIDED", "ORDER_EVENT", "FILL_EVENT",
            ],
        }, "", "", "", "", ""
    ))
    quote_rows = [
        (0, 24500.0, 99.5, 100.5),
        (30, 24505.0, 101.0, 102.0),
        (60, 24512.0, 104.0, 105.0),
        (120, 24520.0, 108.0, 109.0),
        (180, 24518.0, 106.5, 107.5),
        (240, 24528.0, 112.0, 113.0),
        (300, 24535.0, 116.0, 117.0),
    ]
    sequence = 1
    for seconds, index_ltp, bid, ask in quote_rows:
        at = start + timedelta(seconds=seconds)
        specs.append(("MARKET_QUOTE", seconds, {"ltp": index_ltp}, underlying, "", "", "", ""))
        specs.append(("MARKET_QUOTE", seconds, {"bid": bid, "ask": ask, "ltp": (bid + ask) / 2}, option, "", "", "", ""))

    decision_time = start + timedelta(seconds=30)
    feature_time = (decision_time - timedelta(seconds=1)).isoformat()
    outcome_contract = {
        "horizons_seconds": [30, 90, 270],
        "entry_delay_seconds": [0, 15, 30],
        "underlying_instrument": underlying,
        "selected_option_instrument": option,
    }
    specs.extend([
        ("STRATEGY_EVALUATED", 30, {
            "direction": "BUY_CALL",
            "status": "SIGNAL",
            "feature_available_times": {"breadth": feature_time, "basis": feature_time},
            "outcome_contract": outcome_contract,
        }, underlying, candidate, strategy, version, ""),
        ("SIGNAL_GENERATED", 30, {
            "direction": "BUY_CALL",
            "underlying_instrument": underlying,
            "selected_option_instrument": option,
            "outcome_contract": outcome_contract,
        }, underlying, candidate, strategy, version, ""),
        ("CANDIDATE_CREATED", 30, {
            "direction": "BUY_CALL",
            "status": "EXECUTABLE",
            "underlying_instrument": underlying,
            "selected_option_instrument": option,
            "outcome_contract": outcome_contract,
        }, option, candidate, strategy, version, ""),
        ("APPROVAL_REQUESTED", 31, {"status": "PENDING"}, option, candidate, strategy, version, ""),
        ("APPROVAL_DECIDED", 35, {"decision": "APPROVED", "reason": "offline validation"}, option, candidate, strategy, version, ""),
        ("ORDER_EVENT", 36, {"status": "ACKNOWLEDGED", "quantity": 65}, option, candidate, strategy, version, "order-offline-001"),
        ("FILL_EVENT", 37, {"status": "FILLED", "filled_quantity": 65, "fill_price": 102.0}, option, candidate, strategy, version, "order-offline-001"),
    ])

    raw_events: list[CanonicalEvent] = []
    ordered_specs = sorted(enumerate(specs), key=lambda item: (item[1][1], item[0]))
    for producer_sequence, (_, spec) in enumerate(ordered_specs, start=1):
        event_type, seconds, payload, instrument, candidate_id, strategy_id, strategy_version, order_id = spec
        raw_events.append(_event(
            session_id=session_id,
            event_type=event_type,
            sequence=producer_sequence,
            at=start + timedelta(seconds=seconds),
            payload=payload,
            instrument_key=instrument,
            candidate_id=candidate_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            order_id=order_id,
        ))

    end_sequence = len(raw_events) + 1
    expected_count = end_sequence
    raw_events.append(_event(
        session_id=session_id,
        event_type="SESSION_ENDED",
        sequence=end_sequence,
        at=start + timedelta(minutes=5),
        payload={"expected_producer_counts": {"offline-fixture": expected_count}},
    ))
    return raw_events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_events(args.output, build_fixture())
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
