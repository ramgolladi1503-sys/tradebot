from __future__ import annotations

import json

import pytest

from core.latest_artifact_freshness_guard import FRESH_STATUS, INVALID_STATUS, MISSING_STATUS, STALE_STATUS, UNKNOWN_STATUS
from core.runtime_snapshot_store import build_snapshot_envelope, read_snapshot, read_snapshot_with_freshness


def test_read_snapshot_with_freshness_marks_fresh_snapshot(tmp_path):
    path = tmp_path / "advisory_latest.json"
    path.write_text(
        json.dumps(
            build_snapshot_envelope(
                payload={"rows": []},
                producer="test",
                generated_at="1970-01-01T00:16:40Z",
            )
        ),
        encoding="utf-8",
    )

    result = read_snapshot_with_freshness(
        path,
        artifact_name="advisory_latest",
        now_epoch=1_030.0,
        max_age_seconds=60.0,
    )

    assert result["fresh"] is True
    assert result["freshness"]["status"] == FRESH_STATUS
    assert result["freshness"]["timestamp_source"] == "generated_epoch"
    assert result["snapshot"]["payload"] == {"rows": []}
    assert result["is_order_action"] is False
    assert result["broker_api_called"] is False
    assert result["live_order_action"] is False
    assert result["broker_order_action"] is False


def test_read_snapshot_with_freshness_marks_stale_snapshot(tmp_path):
    path = tmp_path / "feed_runtime_latest.json"
    path.write_text(
        json.dumps(
            build_snapshot_envelope(
                payload={"status": "ok"},
                producer="test",
                generated_at="1970-01-01T00:16:40Z",
            )
        ),
        encoding="utf-8",
    )

    result = read_snapshot_with_freshness(
        path,
        artifact_name="feed_runtime_latest",
        now_epoch=1_181.0,
        max_age_seconds=180.0,
    )

    assert result["fresh"] is False
    assert result["freshness"]["status"] == STALE_STATUS
    assert result["blockers"] == ["artifact_age_exceeds_max_age"]


def test_read_snapshot_with_freshness_fails_closed_when_file_is_missing(tmp_path):
    path = tmp_path / "missing_latest.json"

    result = read_snapshot_with_freshness(
        path,
        artifact_name="missing_latest",
        now_epoch=1_000.0,
    )

    assert result["snapshot"] is None
    assert result["fresh"] is False
    assert result["freshness"]["status"] == MISSING_STATUS
    assert result["blockers"] == ["artifact_path_missing"]


def test_read_snapshot_with_freshness_fails_closed_when_snapshot_is_invalid_json(tmp_path):
    path = tmp_path / "bad_latest.json"
    path.write_text("not-json", encoding="utf-8")

    result = read_snapshot_with_freshness(path, artifact_name="bad_latest", now_epoch=1_000.0)

    assert result["snapshot"] is None
    assert result["fresh"] is False
    assert result["freshness"]["status"] == INVALID_STATUS
    assert result["blockers"] == ["artifact_payload_invalid_json"]


def test_read_snapshot_with_freshness_marks_unknown_when_generated_at_missing(tmp_path):
    path = tmp_path / "unknown_latest.json"
    path.write_text(json.dumps({"schema_version": 1, "producer": "test", "payload": {}}), encoding="utf-8")

    result = read_snapshot_with_freshness(path, artifact_name="unknown_latest", now_epoch=1_000.0)

    assert result["snapshot"]["producer"] == "test"
    assert result["fresh"] is False
    assert result["freshness"]["status"] == UNKNOWN_STATUS
    assert result["blockers"] == ["artifact_timestamp_missing"]


def test_existing_read_snapshot_contract_still_returns_raw_envelope(tmp_path):
    path = tmp_path / "snapshot.json"
    envelope = build_snapshot_envelope(
        payload={"value": 1},
        producer="legacy-reader",
        generated_at="1970-01-01T00:16:40Z",
    )
    path.write_text(json.dumps(envelope), encoding="utf-8")

    assert read_snapshot(path) == envelope


def test_existing_read_snapshot_still_raises_for_non_object_json(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="snapshot_envelope_not_object"):
        read_snapshot(path)
