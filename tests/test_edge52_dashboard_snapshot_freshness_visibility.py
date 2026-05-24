from __future__ import annotations

import json

from dashboard.readers.snapshot_reader import read_snapshot_payload
from core.runtime_snapshot_store import build_snapshot_envelope


def test_dashboard_snapshot_reader_exposes_freshness_for_fresh_snapshot(tmp_path):
    path = tmp_path / "advisory_latest.json"
    path.write_text(
        json.dumps(
            build_snapshot_envelope(
                payload={"rows": []},
                producer="test",
                generated_at="2999-01-01T00:00:00Z",
            )
        ),
        encoding="utf-8",
    )

    result = read_snapshot_payload(path)

    assert result["state"] == "ok"
    assert result["payload"] == {"rows": []}
    assert result["fresh"] is True
    assert result["freshness_status"] == "fresh"
    assert result["freshness_timestamp_source"] == "generated_epoch"
    assert result["freshness_blockers"] == []
    assert isinstance(result["freshness"], dict)


def test_dashboard_snapshot_reader_exposes_stale_status(tmp_path):
    path = tmp_path / "feed_runtime_latest.json"
    path.write_text(
        json.dumps(
            build_snapshot_envelope(
                payload={"status": "ok"},
                producer="test",
                generated_at="1970-01-01T00:00:00Z",
            )
        ),
        encoding="utf-8",
    )

    result = read_snapshot_payload(path)

    assert result["state"] == "ok"
    assert result["fresh"] is False
    assert result["freshness_status"] == "stale"
    assert "artifact_age_exceeds_max_age" in result["freshness_blockers"]


def test_dashboard_snapshot_reader_exposes_missing_freshness_for_missing_file(tmp_path):
    path = tmp_path / "missing_latest.json"

    result = read_snapshot_payload(path)

    assert result["state"] == "missing"
    assert result["payload"] == {}
    assert result["fresh"] is False
    assert result["freshness_status"] == "missing"
    assert result["freshness_blockers"] == ["artifact_path_missing"]


def test_dashboard_snapshot_reader_exposes_invalid_freshness_for_invalid_json(tmp_path):
    path = tmp_path / "bad_latest.json"
    path.write_text("not-json", encoding="utf-8")

    result = read_snapshot_payload(path)

    assert result["state"] == "invalid"
    assert result["payload"] == {}
    assert result["fresh"] is False
    assert result["freshness_status"] == "invalid"
    assert result["freshness_blockers"] == ["artifact_payload_invalid_json"]


def test_dashboard_snapshot_reader_keeps_existing_success_fields(tmp_path):
    path = tmp_path / "top_opportunities_latest.json"
    path.write_text(
        json.dumps(
            build_snapshot_envelope(
                payload={"rows": [{"symbol": "NIFTY"}]},
                producer="runtime_snapshot_producer",
                generated_at="2999-01-01T00:00:00Z",
                schema_version=7,
            )
        ),
        encoding="utf-8",
    )

    result = read_snapshot_payload(path)

    assert result["state"] == "ok"
    assert result["errors"] == []
    assert result["payload"] == {"rows": [{"symbol": "NIFTY"}]}
    assert result["producer"] == "runtime_snapshot_producer"
    assert result["schema_version"] == 7
    assert "freshness" in result
    assert "freshness_status" in result
