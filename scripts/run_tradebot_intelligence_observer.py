from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import os
import signal
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aixion_trade_intelligence.adapters.candidate_lineage import adapt_candidate_lineage_row
from aixion_trade_intelligence.contracts import CanonicalEvent
from aixion_trade_intelligence.publisher import FilePublisher
from aixion_trade_intelligence.tailer import JsonlTailer, TailerError


_STOP = False


def _stop_handler(signum, frame):
    del signum, frame
    global _STOP
    _STOP = True


def _utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _default_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"tradebot-live-{stamp}-p{os.getpid()}"


def _session_event(
    *,
    event_type: str,
    session_id: str,
    producer_sequence: int,
    payload: dict,
) -> CanonicalEvent:
    now = datetime.now(timezone.utc)
    return CanonicalEvent(
        event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:{event_type}:{producer_sequence}")),
        event_type=event_type,
        session_id=session_id,
        run_id=session_id,
        trace_id=session_id,
        producer_id="aixion-live-observer",
        producer_sequence=producer_sequence,
        source_component="scripts.run_tradebot_intelligence_observer",
        source_provider="TRADEBOT_RUNTIME",
        event_time=now,
        source_time=now,
        receive_time=now,
        available_time=now,
        parse_time=now,
        persist_time=now,
        data_quality_state="OBSERVER_CONTROL",
        authority_class="OBSERVER_CONTROL",
        payload=payload,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only TradeBot candidate-lineage observer")
    default_data_root = Path(os.getenv("DATA_ROOT", ROOT / ".runtime"))
    parser.add_argument(
        "--lineage",
        type=Path,
        default=default_data_root / "candidate_lineage" / f"candidate_funnel_{_utc_date()}.jsonl",
    )
    parser.add_argument("--session-id")
    parser.add_argument(
        "--session-contract",
        type=Path,
        help="JSON object declaring expected coverage and analytics dependencies for this session.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--poll-seconds", type=float, default=0.5)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-fsync", action="store_true")
    parser.add_argument(
        "--defer-finalization",
        action="store_true",
        help="Write OBSERVER_STOPPED instead of SESSION_ENDED so quote evidence can be appended before finalization.",
    )
    return parser.parse_args()


def _load_session_contract(path: Path | None) -> dict:
    if path is None:
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid session contract {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SystemExit("session contract must be a JSON object")
    forbidden = {"source_lineage_path", "observer_mode", "session_id", "expected_producer_counts"}
    overlap = sorted(forbidden.intersection(raw))
    if overlap:
        raise SystemExit(f"session contract contains observer-owned fields: {overlap}")
    return raw


def main() -> int:
    args = _parse_args()
    session_contract = _load_session_contract(args.session_contract)
    if not args.session_id:
        args.session_id = _default_session_id()
    if args.output is None:
        data_root = Path(os.getenv("DATA_ROOT", ROOT / ".runtime"))
        args.output = data_root / "trade_intelligence" / args.session_id / "events.jsonl"
    if args.output.exists() and args.output.stat().st_size > 0:
        raise SystemExit(f"refusing to append a new session to non-empty evidence file: {args.output}")
    if args.poll_seconds <= 0:
        raise SystemExit("--poll-seconds must be positive")
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be positive")
    checkpoint = args.checkpoint or args.output.with_suffix(".checkpoint.json")
    publisher = FilePublisher(args.output, fsync=not args.no_fsync)
    tailer = JsonlTailer(args.lineage, checkpoint)
    sequence = 1
    counts = {"aixion-live-observer": 0, "tradebot-candidate-lineage": 0}

    publisher.publish(
        _session_event(
            event_type="SESSION_STARTED",
            session_id=args.session_id,
            producer_sequence=sequence,
            payload={
                **session_contract,
                "source_lineage_path": str(args.lineage),
                "observer_mode": "READ_ONLY",
                "expected_event_types": session_contract.get("expected_event_types", []),
            },
        )
    )
    counts["aixion-live-observer"] += 1
    sequence += 1

    signal.signal(signal.SIGINT, _stop_handler)
    signal.signal(signal.SIGTERM, _stop_handler)
    exit_code = 0
    try:
        while not _STOP:
            try:
                records = tailer.read_available(limit=args.batch_size)
            except TailerError as exc:
                incident = _session_event(
                    event_type="INCIDENT_RAISED",
                    session_id=args.session_id,
                    producer_sequence=sequence,
                    payload={
                        "incident_code": "SOURCE_JSONL_INVALID",
                        "source_path": str(args.lineage),
                        "error": str(exc),
                    },
                )
                publisher.publish(incident)
                counts["aixion-live-observer"] += 1
                sequence += 1
                exit_code = 2
                break

            for record in records:
                event = adapt_candidate_lineage_row(
                    record.row,
                    session_id=args.session_id,
                    producer_sequence=counts["tradebot-candidate-lineage"] + 1,
                )
                payload = dict(event.payload)
                payload["source_line_number"] = record.line_number
                payload["source_line_sha256"] = record.line_sha256
                event = CanonicalEvent.from_dict(event.to_dict() | {"payload": payload, "payload_hash": ""})
                publisher.publish(event)
                counts["tradebot-candidate-lineage"] += 1
            if args.once:
                break
            if not records:
                time.sleep(args.poll_seconds)
    finally:
        terminal_type = "OBSERVER_STOPPED" if args.defer_finalization else "SESSION_ENDED"
        terminal_payload = {
            "observer_mode": "READ_ONLY",
            "source_lineage_path": str(args.lineage),
            "source_rows_observed": counts["tradebot-candidate-lineage"],
            "observer_exit_code": exit_code,
            "finalization_deferred": bool(args.defer_finalization),
        }
        if not args.defer_finalization:
            terminal_payload["expected_producer_counts"] = {
                "aixion-live-observer": counts["aixion-live-observer"] + 1,
                "tradebot-candidate-lineage": counts["tradebot-candidate-lineage"],
            }
        publisher.publish(
            _session_event(
                event_type=terminal_type,
                session_id=args.session_id,
                producer_sequence=sequence,
                payload=terminal_payload,
            )
        )
    print(json.dumps({
        "session_id": args.session_id,
        "output": str(args.output),
        "source_rows_observed": counts["tradebot-candidate-lineage"],
        "exit_code": exit_code,
    }, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
