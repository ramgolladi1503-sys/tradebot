from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from aixion_trade_intelligence.baseline_builder import build_ranking_baseline
from aixion_trade_intelligence.evidence_guardian import build_source_continuity_report
from aixion_trade_intelligence.source_checkpoint_builder import (
    SourceFileSpec,
    build_source_checkpoint_bundle,
    scan_source_file,
)


BASE = datetime(2026, 8, 5, 4, 30, tzinfo=timezone.utc)


def _lineage_row(candidate: str, cycle: str, score: float, *, stage: str, executable: bool = False):
    return {
        "candidate_id": candidate,
        "cycle_id": cycle,
        "score": score,
        "rankable": True,
        "executable": executable,
        "direction": "BUY_CE",
        "stage": stage,
    }


def test_ranking_baseline_is_deterministic_and_uses_latest_scored_candidate_state(tmp_path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first_rows = [
        _lineage_row("a", "cycle-1", 0.2, stage="tradebuilder"),
        _lineage_row("a", "cycle-1", 0.8, stage="ranking", executable=True),
        _lineage_row("b", "cycle-1", 0.4, stage="ranking"),
    ]
    second_rows = [
        _lineage_row("c", "cycle-2", 0.7, stage="ranking", executable=True),
        _lineage_row("d", "cycle-2", 0.3, stage="ranking"),
    ]
    first.write_text("".join(json.dumps(row) + "\n" for row in first_rows), encoding="utf-8")
    second.write_text("".join(json.dumps(row) + "\n" for row in second_rows), encoding="utf-8")
    baseline_a = build_ranking_baseline(
        [first, second],
        metric_names=("score_range", "executable_rate", "fallback_contamination_rate"),
    )
    baseline_b = build_ranking_baseline(
        [second, first],
        metric_names=("score_range", "executable_rate", "fallback_contamination_rate"),
    )
    assert baseline_a.baseline_id == baseline_b.baseline_id
    assert baseline_a.to_record() == baseline_b.to_record()
    assert baseline_a.ranking_metrics["score_range"] == pytest.approx((0.4, 0.4))
    assert baseline_a.ranking_metrics["executable_rate"] == pytest.approx((0.5, 0.5))
    assert baseline_a.sources[0].row_count == 3
    assert baseline_a.sources[0].sha256
    assert len(baseline_a.sources[0].sha256) == 64


def test_ranking_baseline_id_changes_when_source_evidence_changes(tmp_path):
    source = tmp_path / "lineage.jsonl"
    rows = [_lineage_row("a", "cycle", 0.7, stage="ranking"), _lineage_row("b", "cycle", 0.3, stage="ranking")]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    before = build_ranking_baseline([source], metric_names=("score_range",))
    rows[0]["score"] = 0.9
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    after = build_ranking_baseline([source], metric_names=("score_range",))
    assert before.baseline_id != after.baseline_id
    assert before.sources[0].sha256 != after.sources[0].sha256
    assert before.ranking_metrics["score_range"] != after.ranking_metrics["score_range"]


def _event(event_id: str, sequence: int, event_type: str, source_time: datetime, *, component: str = "feed"):
    receive = source_time + timedelta(milliseconds=10)
    persist = receive + timedelta(milliseconds=5)
    return {
        "event_id": event_id,
        "producer_sequence": sequence,
        "event_type": event_type,
        "source_component": component,
        "source_time": source_time.isoformat(),
        "receive_time": receive.isoformat(),
        "persist_time": persist.isoformat(),
    }


def test_source_checkpoint_builder_detects_gaps_duplicates_malformed_and_partial_line(tmp_path):
    source = tmp_path / "events.jsonl"
    rows = [
        _event("event-1", 1, "SESSION_STARTED", BASE),
        _event("event-2", 3, "FEED_TRUTH_UPDATED", BASE + timedelta(seconds=1)),
        _event("event-2", 3, "FEED_TRUTH_UPDATED", BASE + timedelta(seconds=1)),
    ]
    source.write_bytes(
        ("".join(json.dumps(row) + "\n" for row in rows) + "{bad-json}\n" + json.dumps(_event("partial", 4, "SESSION_ENDED", BASE + timedelta(seconds=2)))).encode("utf-8")
    )
    spec = SourceFileSpec(
        source_name="feed_truth",
        path=source,
        identity_fields=("event_id",),
        event_type_field="event_type",
        source_time_field="source_time",
        receive_time_field="receive_time",
        persist_time_field="persist_time",
        sequence_field="producer_sequence",
        required_event_types=("SESSION_STARTED", "FEED_TRUTH_UPDATED", "SESSION_ENDED"),
    )
    scan = scan_source_file(spec)
    assert scan.valid_row_count == 3
    assert scan.malformed_row_count == 1
    assert scan.duplicate_identity_count == 1
    assert scan.partial_final_line_ignored is True
    assert scan.checkpoint.sequence_gap_events == 1
    assert scan.checkpoint.observed_event_types == ("FEED_TRUTH_UPDATED", "SESSION_STARTED")
    report = build_source_continuity_report(scan.checkpoint, evaluation_time=BASE + timedelta(seconds=3))
    assert report.integrity_valid is False
    assert report.unique_observed_events == 2
    assert report.coverage_ratio == pytest.approx(2.0 / 3.0)
    assert report.sequence_loss_rate == pytest.approx(1.0 / 3.0)
    assert report.duplicate_rate == pytest.approx(1.0 / 3.0)
    assert report.missing_required_event_types == ("SESSION_ENDED",)


def test_source_checkpoint_filters_one_canonical_log_into_component_views(tmp_path):
    source = tmp_path / "events.jsonl"
    rows = [
        _event("feed-1", 1, "FEED_TRUTH_UPDATED", BASE, component="feed"),
        _event("risk-1", 2, "RISK_STATE_CHANGED", BASE + timedelta(seconds=1), component="risk"),
        _event("feed-2", 3, "FEED_TRUTH_UPDATED", BASE + timedelta(seconds=2), component="feed"),
    ]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    feed_spec = SourceFileSpec(
        source_name="feed_component",
        path=source,
        identity_fields=("event_id",),
        event_type_field="event_type",
        source_time_field="source_time",
        receive_time_field="receive_time",
        persist_time_field="persist_time",
        required_event_types=("FEED_TRUTH_UPDATED",),
        filters=(("source_component", ("feed",)),),
    )
    risk_spec = SourceFileSpec(
        source_name="risk_component",
        path=source,
        identity_fields=("event_id",),
        event_type_field="event_type",
        source_time_field="source_time",
        receive_time_field="receive_time",
        persist_time_field="persist_time",
        required_event_types=("RISK_STATE_CHANGED",),
        filters=(("source_component", ("risk",)),),
    )
    bundle = build_source_checkpoint_bundle([feed_spec, risk_spec])
    by_name = {row.checkpoint.source_name: row for row in bundle.sources}
    assert by_name["feed_component"].valid_row_count == 2
    assert by_name["feed_component"].filtered_out_row_count == 1
    assert by_name["feed_component"].checkpoint.observed_event_types == ("FEED_TRUTH_UPDATED",)
    assert by_name["risk_component"].valid_row_count == 1
    assert by_name["risk_component"].filtered_out_row_count == 2
    assert by_name["risk_component"].checkpoint.observed_event_types == ("RISK_STATE_CHANGED",)


def test_source_checkpoint_bundle_is_deterministic_and_provenance_hashed(tmp_path):
    source = tmp_path / "events.jsonl"
    source.write_text(json.dumps(_event("event-1", 1, "SESSION_STARTED", BASE)) + "\n", encoding="utf-8")
    spec = SourceFileSpec(
        source_name="session",
        path=source,
        identity_fields=("event_id",),
        event_type_field="event_type",
        source_time_field="source_time",
        receive_time_field="receive_time",
        persist_time_field="persist_time",
        sequence_field="producer_sequence",
        required_event_types=("SESSION_STARTED",),
    )
    first = build_source_checkpoint_bundle([spec])
    second = build_source_checkpoint_bundle([spec])
    assert first.bundle_id == second.bundle_id
    assert first.to_record() == second.to_record()
    assert first.sources[0].sha256
    assert first.sources[0].checkpoint.malformed_events == 0
    assert first.sources[0].checkpoint.sequence_gap_events == 0


def test_source_checkpoint_rejects_causally_invalid_timestamps(tmp_path):
    source = tmp_path / "events.jsonl"
    invalid = _event("event-1", 1, "SESSION_STARTED", BASE)
    invalid["receive_time"] = (BASE - timedelta(seconds=1)).isoformat()
    source.write_text(json.dumps(invalid) + "\n", encoding="utf-8")
    spec = SourceFileSpec(
        source_name="session",
        path=source,
        identity_fields=("event_id",),
        event_type_field="event_type",
        source_time_field="source_time",
        receive_time_field="receive_time",
        persist_time_field="persist_time",
        sequence_field="producer_sequence",
        required_event_types=("SESSION_STARTED",),
    )
    scan = scan_source_file(spec)
    assert scan.valid_row_count == 0
    assert scan.malformed_row_count == 1
    assert scan.checkpoint.observed_events == 0
    assert scan.checkpoint.latest_source_time is None
