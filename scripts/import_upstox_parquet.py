from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aixion_trade_intelligence.adapters.upstox import adapt_upstox_quote_row
from aixion_trade_intelligence.contracts import CanonicalEvent
from aixion_trade_intelligence.lineage import build_candidate_lineage
from aixion_trade_intelligence.storage import append_events, load_events, write_events


def _control_event(
    event_type: str,
    session_id: str,
    sequence: int,
    payload: dict,
    at: datetime,
) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:{event_type}:{sequence}")),
        event_type=event_type,
        session_id=session_id,
        run_id=session_id,
        trace_id=session_id,
        producer_id="upstox-parquet-importer",
        producer_sequence=sequence,
        source_component="scripts.import_upstox_parquet",
        source_provider="UPSTOX_CAPTURE",
        event_time=at,
        source_time=at,
        receive_time=at,
        available_time=at,
        parse_time=at,
        persist_time=at,
        data_quality_state="IMPORT_CONTROL",
        authority_class="IMPORT_CONTROL",
        payload=payload,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import Upstox capture Parquet into canonical JSONL evidence"
    )
    parser.add_argument("--input", type=Path, action="append", required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--output", type=Path)
    target.add_argument(
        "--append-to",
        type=Path,
        help="Append quotes to an existing unfinalized session evidence file.",
    )
    parser.add_argument("--session-id")
    parser.add_argument("--instrument", action="append", default=[])
    parser.add_argument(
        "--all-instruments",
        action="store_true",
        help="Explicitly import every instrument. Without this flag an exact instrument set is required or derived.",
    )
    parser.add_argument("--batch-size", type=int, default=65_536)
    parser.add_argument("--no-fsync", action="store_true")
    return parser.parse_args()


def _derive_exact_instruments(events: list[CanonicalEvent]) -> set[str]:
    instruments: set[str] = set()
    for row in build_candidate_lineage(events):
        if row.underlying_instrument:
            instruments.add(row.underlying_instrument)
        if row.selected_option_instrument:
            instruments.add(row.selected_option_instrument)
    starts = [event for event in events if event.event_type == "SESSION_STARTED"]
    if len(starts) == 1:
        payload = starts[0].payload
        for value in payload.get("expected_instruments", []):
            text = str(value or "").strip()
            if text:
                instruments.add(text)
        analytics = payload.get("analytics_contract")
        if isinstance(analytics, dict):
            for key in ("index_instrument", "futures_instrument"):
                text = str(analytics.get(key) or "").strip()
                if text:
                    instruments.add(text)
            constituents = analytics.get("constituents")
            if isinstance(constituents, list):
                for row in constituents:
                    if isinstance(row, dict):
                        text = str(row.get("instrument_key") or "").strip()
                        if text:
                            instruments.add(text)
    return instruments


def _derive_candidate_instruments(events: list[CanonicalEvent]) -> set[str]:
    """Backward-compatible helper name used by focused tests."""
    return _derive_exact_instruments(events)


def main() -> int:
    args = _parse_args()
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be positive")

    existing: list[CanonicalEvent] = []
    starting_quote_sequence = 0
    if args.append_to:
        existing = load_events(args.append_to)
        if not existing:
            raise SystemExit("--append-to evidence file is empty")
        sessions = {event.session_id for event in existing}
        if len(sessions) != 1:
            raise SystemExit("existing evidence contains multiple sessions")
        existing_session = next(iter(sessions))
        if args.session_id and args.session_id != existing_session:
            raise SystemExit("--session-id does not match existing evidence")
        args.session_id = existing_session
        if any(event.event_type == "SESSION_ENDED" for event in existing):
            raise SystemExit("cannot append market evidence after SESSION_ENDED")
        starting_quote_sequence = max(
            (
                event.producer_sequence
                for event in existing
                if event.producer_id == "upstox-market-data"
            ),
            default=0,
        )
    elif not args.session_id:
        raise SystemExit("--session-id is required with --output")

    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SystemExit("pyarrow is required; install repository requirements") from exc

    instrument_filter = {value.strip() for value in args.instrument if value.strip()}
    if args.append_to:
        instrument_filter.update(_derive_exact_instruments(existing))
    if not instrument_filter and not args.all_instruments:
        raise SystemExit(
            "no exact instruments resolved; pass --instrument, append evidence containing candidate contracts, "
            "or explicitly authorize --all-instruments"
        )

    quote_events: list[CanonicalEvent] = []
    quote_sequence = starting_quote_sequence
    for input_path in args.input:
        parquet = pq.ParquetFile(input_path)
        for batch in parquet.iter_batches(batch_size=args.batch_size):
            for row in batch.to_pylist():
                instrument = str(row.get("instrument_key") or "")
                if instrument_filter and instrument not in instrument_filter:
                    continue
                event = adapt_upstox_quote_row(
                    row,
                    session_id=args.session_id,
                    producer_sequence=quote_sequence + 1,
                )
                if event is not None:
                    quote_sequence += 1
                    quote_events.append(event)

    if not quote_events:
        raise SystemExit("no importable quote events were found")

    if args.append_to:
        append_events(args.append_to, quote_events, fsync=not args.no_fsync)
        print(args.append_to)
        return 0

    observed_instruments = sorted({event.instrument_key for event in quote_events if event.instrument_key})
    event_start = min(event.event_time for event in quote_events)
    event_end = max(event.event_time for event in quote_events)
    start_event = _control_event(
        "SESSION_STARTED",
        args.session_id,
        1,
        {
            "declared_start": event_start.isoformat(),
            "declared_end": event_end.isoformat(),
            "expected_instruments": sorted(instrument_filter) if instrument_filter else observed_instruments,
            "expected_event_types": ["MARKET_QUOTE"],
            "source_files": [str(path) for path in args.input],
            "instrument_filter": sorted(instrument_filter),
            "import_mode": "READ_ONLY_DERIVED_EVIDENCE",
        },
        event_start,
    )
    end_event = _control_event(
        "SESSION_ENDED",
        args.session_id,
        2,
        {
            "expected_producer_counts": {
                "upstox-parquet-importer": 2,
                "upstox-market-data": quote_sequence,
            },
            "imported_quote_rows": quote_sequence,
            "observed_instruments": observed_instruments,
        },
        event_end,
    )
    write_events(args.output, [start_event, *quote_events, end_event])
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
