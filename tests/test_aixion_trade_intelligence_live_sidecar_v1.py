from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from aixion_trade_intelligence.live_sidecar import JsonlSource, LiveSidecar, SidecarConfig
from aixion_trade_intelligence.publisher import FileEventPublisher
from aixion_trade_intelligence.safe_publish import NonBlockingPublisher
from aixion_trade_intelligence.session import SessionAnalyzer
from aixion_trade_intelligence.storage import iter_events


BASE = datetime(2026, 8, 5, 3, 45, tzinfo=timezone.utc)


def test_sidecar_rejects_live_mode(tmp_path):
    with pytest.raises(ValueError, match="paper_or_shadow"):
        SidecarConfig(
            session_id="s",
            run_id="r",
            mode="LIVE",
            sources=(JsonlSource(tmp_path / "x.jsonl", "candidate_lineage", "fixture"),),
            poll_interval_seconds=1.0,
        )


def test_sidecar_json_requires_explicit_source_offset_policy(tmp_path):
    config_path = tmp_path / "sidecar.json"
    config_path.write_text(
        json.dumps(
            {
                "session_id": "s",
                "run_id": "r",
                "mode": "SHADOW",
                "poll_interval_seconds": 1.0,
                "sources": [
                    {
                        "path": str(tmp_path / "source.jsonl"),
                        "source_type": "candidate_lineage",
                        "source_component": "fixture",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="requires_start_at_end"):
        SidecarConfig.from_json(config_path)


def test_sidecar_tails_only_new_complete_lines_and_builds_valid_session(tmp_path):
    source_path = tmp_path / "candidate.jsonl"
    row = {
        "timestamp": BASE.isoformat(),
        "available_time": (BASE - timedelta(milliseconds=1)).isoformat(),
        "candidate_id": "c-1",
        "stage": "candidate_created",
        "instrument_id": "NSE_FO|1",
        "strategy_name": "fixture",
        "strategy_version": "1",
    }
    rendered = json.dumps(row)
    source_path.write_text(rendered[:20], encoding="utf-8")
    config = SidecarConfig(
        session_id="session-1",
        run_id="run-1",
        mode="SHADOW",
        sources=(JsonlSource(source_path, "candidate_lineage", "fixture"),),
        poll_interval_seconds=0.01,
        start_at_end=False,
        session_start_time=BASE - timedelta(seconds=1),
        session_end_time=BASE + timedelta(seconds=2),
    )
    evidence_root = tmp_path / "evidence"
    sidecar = LiveSidecar(
        config,
        NonBlockingPublisher(FileEventPublisher(evidence_root, fsync=False)),
        clock=lambda: BASE + timedelta(seconds=3),
    )
    first = sidecar.poll_once()
    assert first == {"attempted": 0, "persisted": 0, "failed": 0}
    with source_path.open("a", encoding="utf-8") as handle:
        handle.write(rendered[20:] + "\n")
    second = sidecar.poll_once()
    assert second == {"attempted": 1, "persisted": 1, "failed": 0}
    third = sidecar.poll_once()
    assert third == {"attempted": 0, "persisted": 0, "failed": 0}
    sidecar.stop()
    events = list(iter_events(evidence_root / "session-1" / "events.jsonl"))
    assert [event.event_type for event in events] == [
        "SESSION_STARTED",
        "CANDIDATE_CREATED",
        "SESSION_ENDED",
    ]
    analysis = SessionAnalyzer().analyze(events)
    assert analysis.manifest["valid"] is True
    assert analysis.manifest["producer_sequence_gap_total"] == 0
    assert analysis.manifest["lifecycle_order_valid"] is True


def test_sidecar_counts_invalid_rows_without_crashing(tmp_path):
    source_path = tmp_path / "candidate.jsonl"
    source_path.write_text(
        json.dumps({"timestamp": BASE.isoformat(), "stage": "unknown"}) + "\n",
        encoding="utf-8",
    )
    config = SidecarConfig(
        session_id="session-2",
        run_id="run-2",
        mode="PAPER",
        sources=(JsonlSource(source_path, "candidate_lineage", "fixture"),),
        poll_interval_seconds=0.01,
    )
    sidecar = LiveSidecar(
        config,
        NonBlockingPublisher(FileEventPublisher(tmp_path / "evidence", fsync=False)),
        clock=lambda: BASE + timedelta(seconds=1),
    )
    result = sidecar.poll_once()
    assert result == {"attempted": 1, "persisted": 0, "failed": 1}
    sidecar.stop()
