from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aixion_trade_intelligence.contracts import CanonicalEvent
from aixion_trade_intelligence.live_snapshot import build_live_session_snapshot
from aixion_trade_intelligence.publisher import FileEventPublisher
from aixion_trade_intelligence.session import SessionAnalyzer


BASE = datetime(2026, 8, 5, 3, 45, tzinfo=timezone.utc)


def _event(
    event_id: str,
    event_type: str,
    *,
    second: int,
    component: str,
    sequence: int,
    quality: str = "VALID",
) -> CanonicalEvent:
    event_time = BASE + timedelta(seconds=second)
    source_time = event_time - timedelta(milliseconds=20)
    receive_time = event_time - timedelta(milliseconds=10)
    return CanonicalEvent(
        event_id=event_id,
        event_type=event_type,
        schema_version="1.0.0",
        session_id="LIVE-SNAPSHOT-SESSION",
        run_id="LIVE-SNAPSHOT-RUN",
        event_time=event_time,
        source_time=source_time,
        receive_time=receive_time,
        available_time=source_time,
        parse_time=receive_time,
        persist_time=event_time,
        source_provider="TRADEBOT",
        source_component=component,
        authority_class="TRADEBOT_RUNTIME_TRUTH",
        data_quality_state=quality,
        producer_sequence=sequence,
        payload={},
    )


def _verification(*, valid: bool = True):
    return {
        "event_count": 2,
        "session_count": 1,
        "sessions": ["LIVE-SNAPSHOT-SESSION"],
        "event_log_sha256": "hash",
        "valid": valid,
    }


def test_active_session_is_monitoring_healthy_but_not_finally_complete():
    events = [
        _event("start", "SESSION_STARTED", second=0, component="runtime", sequence=1),
        _event("feed", "FEED_TRUTH_UPDATED", second=1, component="feed", sequence=1),
    ]
    analysis = SessionAnalyzer().analyze(events)
    snapshot = build_live_session_snapshot(analysis, verification=_verification())
    assert analysis.manifest["verdict"] == "INCOMPLETE_SESSION"
    assert snapshot.monitoring_valid is True
    assert snapshot.monitoring_verdict == "LIVE_MONITORING_HEALTHY"
    assert snapshot.final_session_complete is False
    assert snapshot.final_session_valid is False
    assert snapshot.monitoring_only is True
    assert snapshot.blockers == ()


def test_completed_valid_session_is_final_complete():
    events = [
        _event("start", "SESSION_STARTED", second=0, component="runtime", sequence=1),
        _event("feed", "FEED_TRUTH_UPDATED", second=1, component="feed", sequence=1),
        _event("end", "SESSION_ENDED", second=2, component="runtime", sequence=2),
    ]
    analysis = SessionAnalyzer().analyze(events)
    verification = {**_verification(), "event_count": 3}
    snapshot = build_live_session_snapshot(analysis, verification=verification)
    assert analysis.manifest["valid"] is True
    assert snapshot.monitoring_valid is True
    assert snapshot.monitoring_verdict == "FINAL_SESSION_COMPLETE"
    assert snapshot.final_session_complete is True
    assert snapshot.final_session_valid is True
    assert snapshot.monitoring_only is False


def test_completed_invalid_session_is_blocked_and_not_monitoring_only():
    events = [
        _event("start", "SESSION_STARTED", second=0, component="runtime", sequence=1),
        _event("feed", "FEED_TRUTH_UPDATED", second=1, component="feed", sequence=1, quality="DEGRADED"),
        _event("end", "SESSION_ENDED", second=2, component="runtime", sequence=2),
    ]
    analysis = SessionAnalyzer().analyze(events)
    verification = {**_verification(), "event_count": 3}
    snapshot = build_live_session_snapshot(analysis, verification=verification)
    assert analysis.manifest["verdict"] == "PARTIAL_DATA_QUALITY"
    assert snapshot.monitoring_valid is False
    assert snapshot.monitoring_verdict == "LIVE_MONITORING_BLOCKED"
    assert snapshot.final_session_complete is True
    assert snapshot.final_session_valid is False
    assert snapshot.monitoring_only is False
    assert "PARTIAL_DATA_QUALITY" in snapshot.blockers
    assert "FINAL_SESSION_EVIDENCE_INVALID" in snapshot.blockers


def test_active_session_blocks_partial_quality_and_sequence_loss():
    events = [
        _event("start", "SESSION_STARTED", second=0, component="runtime", sequence=1),
        _event("feed", "FEED_TRUTH_UPDATED", second=1, component="feed", sequence=2, quality="DEGRADED"),
    ]
    analysis = SessionAnalyzer().analyze(events)
    snapshot = build_live_session_snapshot(analysis, verification=_verification())
    assert snapshot.monitoring_valid is False
    assert snapshot.monitoring_verdict == "LIVE_MONITORING_BLOCKED"
    assert "PRODUCER_SEQUENCE_GAP" in snapshot.blockers
    assert "PARTIAL_DATA_QUALITY" in snapshot.blockers


def test_active_session_blocks_missing_start_and_failed_verification():
    events = [_event("feed", "FEED_TRUTH_UPDATED", second=1, component="feed", sequence=1)]
    analysis = SessionAnalyzer().analyze(events)
    snapshot = build_live_session_snapshot(analysis, verification=_verification(valid=False))
    assert snapshot.monitoring_valid is False
    assert "EVENT_LOG_VERIFICATION_FAILED" in snapshot.blockers
    assert "SESSION_START_MISSING_OR_DUPLICATE" in snapshot.blockers
    assert any(reason.startswith("LIFECYCLE:SESSION_STARTED_COUNT=0") for reason in snapshot.blockers)


def test_live_snapshot_cli_writes_monitoring_artifact_for_active_session(tmp_path):
    repo_root = Path(__file__).parents[1]
    evidence_root = tmp_path / "evidence"
    output = tmp_path / "live_snapshot.json"
    publisher = FileEventPublisher(evidence_root)
    publisher.publish(_event("start", "SESSION_STARTED", second=0, component="runtime", sequence=1))
    publisher.publish(_event("feed", "FEED_TRUTH_UPDATED", second=1, component="feed", sequence=1))
    event_log = evidence_root / "LIVE-SNAPSHOT-SESSION" / "events.jsonl"
    run = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "build_aixion_live_snapshot.py"),
            "--event-log",
            str(event_log),
            "--output",
            str(output),
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["monitoring_verdict"] == "LIVE_MONITORING_HEALTHY"
    assert record["monitoring_valid"] is True
    assert record["final_session_complete"] is False
    assert record["final_session_valid"] is False
    assert record["session_analysis"]["manifest"]["verdict"] == "INCOMPLETE_SESSION"
