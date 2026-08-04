from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aixion_trade_intelligence.contracts import CanonicalEvent
from aixion_trade_intelligence.publisher import FileEventPublisher
from aixion_trade_intelligence.safe_publish import NonBlockingPublisher


BASE = datetime(2026, 8, 5, 3, 45, tzinfo=timezone.utc)


def sample_event() -> CanonicalEvent:
    return CanonicalEvent(
        event_id="safe-1",
        event_type="SESSION_STARTED",
        schema_version="1.0.0",
        session_id="safe-session",
        run_id="safe-run",
        event_time=BASE,
        source_time=BASE - timedelta(milliseconds=10),
        receive_time=BASE,
        available_time=BASE - timedelta(milliseconds=10),
        parse_time=BASE,
        persist_time=BASE,
        source_provider="TEST",
        source_component="fixture",
        authority_class="TEST_EVIDENCE",
        data_quality_state="VALID",
        producer_sequence=1,
        payload={},
    )


def test_nonblocking_publisher_isolates_failure():
    class FailingPublisher:
        def publish(self, event: CanonicalEvent) -> bool:
            del event
            raise OSError("disk unavailable")

    publisher = NonBlockingPublisher(FailingPublisher())
    assert publisher.publish(sample_event()) is False
    stats = publisher.stats()
    assert stats.attempted == 1
    assert stats.persisted == 0
    assert stats.failures == 1
    assert "disk unavailable" in stats.last_error
    assert publisher.evidence_complete is False


def test_nonblocking_publisher_reports_duplicates(tmp_path):
    publisher = NonBlockingPublisher(FileEventPublisher(tmp_path, fsync=False))
    item = sample_event()
    assert publisher.publish(item) is True
    assert publisher.publish(item) is False
    stats = publisher.stats()
    assert stats.attempted == 2
    assert stats.persisted == 1
    assert stats.duplicates == 1
    assert stats.failures == 0
    assert publisher.evidence_complete is True


def test_end_to_end_fixture_cli(tmp_path):
    repository_root = Path(__file__).parents[1]
    evidence_root = tmp_path / "evidence"
    report_root = tmp_path / "report"
    generate = subprocess.run(
        [
            sys.executable,
            str(repository_root / "scripts" / "generate_aixion_trade_intelligence_fixture.py"),
            "--output-root",
            str(evidence_root),
        ],
        cwd=repository_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert generate.returncode == 0, generate.stderr
    event_log = evidence_root / "OFFLINE-CERT-SESSION-001" / "events.jsonl"
    analyze = subprocess.run(
        [
            sys.executable,
            str(repository_root / "scripts" / "run_aixion_trade_intelligence_offline.py"),
            "--event-log",
            str(event_log),
            "--output-dir",
            str(report_root),
        ],
        cwd=repository_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert analyze.returncode == 0, analyze.stderr
    assert (report_root / "session_analysis.json").exists()
    report = (report_root / "session_report.md").read_text(encoding="utf-8")
    assert "VALID_OFFLINE_SESSION_EVIDENCE" in report
    assert "Ready for profitability claim: `False`" in report
