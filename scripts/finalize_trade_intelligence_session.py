from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aixion_trade_intelligence.certification import analyze_session, certify_analysis
from aixion_trade_intelligence.contracts import CanonicalEvent
from aixion_trade_intelligence.publisher import FilePublisher
from aixion_trade_intelligence.report import build_report_payload, write_report
from aixion_trade_intelligence.storage import atomic_write_json, load_events


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize and certify a deferred intelligence session")
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    events = load_events(args.events)
    if not events:
        raise SystemExit("evidence file is empty")
    session_ids = {event.session_id for event in events}
    if len(session_ids) != 1:
        raise SystemExit("evidence contains multiple session IDs")
    session_id = next(iter(session_ids))
    if sum(event.event_type == "SESSION_STARTED" for event in events) != 1:
        raise SystemExit("evidence must contain exactly one SESSION_STARTED")
    end_count = sum(event.event_type == "SESSION_ENDED" for event in events)
    if end_count > 1:
        raise SystemExit("evidence contains multiple SESSION_ENDED events")

    if end_count == 0:
        unique = {event.event_id: event for event in events}
        counts = Counter(event.producer_id or event.source_component for event in unique.values())
        finalizer_producer = "aixion-session-finalizer"
        finalizer_sequence = 1
        counts[finalizer_producer] += 1
        observational = [
            event
            for event in unique.values()
            if event.event_type not in {"SESSION_STARTED", "OBSERVER_STOPPED", "INCIDENT_RAISED"}
        ]
        now = datetime.now(timezone.utc)
        end_time = max((event.event_time for event in observational), default=now)
        if end_time > now:
            raise SystemExit("observational evidence contains a future event_time")
        end_event = CanonicalEvent(
            event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:SESSION_ENDED:finalizer-v1")),
            event_type="SESSION_ENDED",
            session_id=session_id,
            run_id=session_id,
            trace_id=session_id,
            producer_id=finalizer_producer,
            producer_sequence=finalizer_sequence,
            source_component="scripts.finalize_trade_intelligence_session",
            source_provider="TRADEBOT_RUNTIME",
            event_time=end_time,
            source_time=end_time,
            receive_time=now,
            available_time=now,
            parse_time=now,
            persist_time=now,
            data_quality_state="FINALIZATION_CONTROL",
            authority_class="FINALIZATION_CONTROL",
            payload={
                "expected_producer_counts": dict(sorted(counts.items())),
                "unique_pre_finalization_events": len(unique),
                "finalization_mode": "DERIVED_EXACT_RECONCILIATION",
            },
        )
        FilePublisher(args.events, fsync=True).publish(end_event)

    finalized = load_events(args.events)
    analysis = analyze_session(finalized)
    certification = certify_analysis(analysis)
    payload = build_report_payload(
        certification=certification,
        lineage=analysis.lineage,
        outcomes=analysis.outcomes,
        analytics=analysis.analytics,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.output_dir / "certification.json", certification.to_dict())
    write_report(args.output_dir, payload)
    print(json.dumps({
        "session_id": session_id,
        "verdict": certification.verdict,
        "pipeline_certified": certification.pipeline_certified,
        "manifest_verdict": certification.manifest.verdict,
        "lineage_count": certification.lineage_count,
        "outcome_count": certification.outcome_count,
        "output_dir": str(args.output_dir),
    }, sort_keys=True))
    return 0 if certification.pipeline_certified else 3


if __name__ == "__main__":
    raise SystemExit(main())
