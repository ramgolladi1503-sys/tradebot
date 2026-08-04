#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from aixion_trade_intelligence.contracts import CanonicalEvent
from aixion_trade_intelligence.publisher import FileEventPublisher


def _event(
    event_id: str,
    event_type: str,
    *,
    base: datetime,
    second: int,
    sequence: int,
    candidate_id: str = "",
    payload: dict | None = None,
) -> CanonicalEvent:
    event_time = base + timedelta(seconds=second)
    source_time = event_time - timedelta(milliseconds=20)
    receive_time = event_time - timedelta(milliseconds=8)
    parse_time = event_time - timedelta(milliseconds=3)
    return CanonicalEvent(
        event_id=event_id,
        event_type=event_type,
        schema_version="1.0.0",
        session_id="OFFLINE-CERT-SESSION-001",
        run_id="OFFLINE-CERT-RUN-001",
        cycle_id=f"cycle-{second}",
        trace_id="offline-cert-trace",
        event_time=event_time,
        source_time=source_time,
        receive_time=receive_time,
        available_time=source_time,
        parse_time=parse_time,
        persist_time=event_time,
        source_provider="OFFLINE_FIXTURE",
        source_component="scripts.generate_aixion_trade_intelligence_fixture",
        authority_class="TEST_EVIDENCE",
        data_quality_state="VALID",
        instrument_key="NSE_INDEX|Nifty 50",
        strategy_id="offline_fixture" if candidate_id else "",
        strategy_version="1.0.0" if candidate_id else "",
        candidate_id=candidate_id,
        producer_sequence=sequence,
        payload=payload or {},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    base = datetime(2026, 8, 5, 3, 45, tzinfo=timezone.utc)
    events = [
        _event("cert-1", "SESSION_STARTED", base=base, second=0, sequence=1),
        _event("cert-2", "FEED_TRUTH_UPDATED", base=base, second=1, sequence=2, payload={"state": "FRESH"}),
        _event("cert-3", "STRATEGY_EVALUATED", base=base, second=2, sequence=3, candidate_id="candidate-cert-1"),
        _event("cert-4", "SIGNAL_GENERATED", base=base, second=3, sequence=4, candidate_id="candidate-cert-1"),
        _event("cert-5", "CANDIDATE_CREATED", base=base, second=4, sequence=5, candidate_id="candidate-cert-1"),
        _event("cert-6", "CANDIDATE_RANKED", base=base, second=5, sequence=6, candidate_id="candidate-cert-1"),
        _event("cert-7", "APPROVAL_REQUESTED", base=base, second=6, sequence=7, candidate_id="candidate-cert-1"),
        _event("cert-8", "APPROVAL_DECIDED", base=base, second=7, sequence=8, candidate_id="candidate-cert-1", payload={"decision": "REJECT"}),
        _event("cert-9", "OUTCOME_LABEL", base=base, second=30, sequence=9, candidate_id="candidate-cert-1", payload={"status": "RESOLVED", "horizon_seconds": 30}),
        _event("cert-10", "SESSION_ENDED", base=base, second=31, sequence=10),
    ]
    publisher = FileEventPublisher(args.output_root, fsync=True)
    persisted = sum(1 for event in events if publisher.publish(event))
    return 0 if persisted == len(events) else 2


if __name__ == "__main__":
    raise SystemExit(main())
