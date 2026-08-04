from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from aixion_trade_intelligence.evidence_guardian import build_source_continuity_report
from aixion_trade_intelligence.source_checkpoint_builder import (
    SourceFileSpec,
    build_source_checkpoint_bundle,
    scan_source_file,
)


BASE = datetime(2026, 8, 5, 4, 30, tzinfo=timezone.utc)


def _event(
    event_id: str,
    sequence: int,
    event_type: str,
    source_time: datetime,
    *,
    component: str = "feed",
):
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


def test_duplicate_rows_do_not_inflate_unique_sequence_coverage(tmp_path):
    source = tmp_path / "events.jsonl"
    rows = [
        _event("event-1", 1, "SESSION_STARTED", BASE),
        _event("event-2", 3, "FEED_TRUTH_UPDATED", BASE + timedelta(seconds=1)),
        _event("event-2", 3, "FEED_TRUTH_UPDATED", BASE + timedelta(seconds=1)),
    ]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    spec = SourceFileSpec(
        source_name="feed_truth",
        path=source,
        identity_fields=("event_id",),
        event_type_field="event_type",
        source_time_field="source_time",
        receive_time_field="receive_time",
        persist_time_field="persist_time",
        sequence_field="producer_sequence",
        required_event_types=("SESSION_STARTED", "FEED_TRUTH_UPDATED"),
    )
    scan = scan_source_file(spec)
    report = build_source_continuity_report(
        scan.checkpoint,
        evaluation_time=BASE + timedelta(seconds=3),
    )
    assert report.unique_observed_events == 2
    assert report.coverage_ratio == pytest.approx(2.0 / 3.0)
    assert report.sequence_loss_rate == pytest.approx(1.0 / 3.0)
    assert report.duplicate_rate == pytest.approx(1.0 / 3.0)
    assert report.integrity_valid is False


def test_component_filters_split_one_canonical_log_into_independent_views(tmp_path):
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


def test_filter_configuration_accepts_sequence_values_from_mapping(tmp_path):
    source = tmp_path / "events.jsonl"
    source.write_text(
        json.dumps(_event("feed-1", 1, "FEED_TRUTH_UPDATED", BASE, component="feed")) + "\n",
        encoding="utf-8",
    )
    spec = SourceFileSpec.from_mapping(
        {
            "source_name": "feed_component",
            "path": source.as_posix(),
            "identity_fields": ["event_id"],
            "event_type_field": "event_type",
            "source_time_field": "source_time",
            "receive_time_field": "receive_time",
            "persist_time_field": "persist_time",
            "required_event_types": ["FEED_TRUTH_UPDATED"],
            "filters": {"source_component": ["feed", "market_feed"]},
        }
    )
    assert spec.filters == (("source_component", ("feed", "market_feed")),)
    scan = scan_source_file(spec)
    assert scan.valid_row_count == 1
    assert scan.filtered_out_row_count == 0
