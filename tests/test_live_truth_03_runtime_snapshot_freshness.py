from __future__ import annotations

import json

from core.live_truth_runtime_snapshot_freshness import (
    FRESHNESS_STATUS_BLOCKED,
    FRESHNESS_STATUS_FRESH,
    FRESHNESS_STATUS_STALE,
    FUTURE_TIMESTAMP_REASON,
    INVALID_FRESHNESS_CONFIG_REASON,
    INVALID_SNAPSHOT_REASON,
    MISSING_TIMESTAMP_REASON,
    NO_SNAPSHOTS_REASON,
    RUNTIME_SNAPSHOT_FRESHNESS_SOURCE,
    STALE_TIMESTAMP_REASON,
    build_runtime_snapshot_freshness_report,
    write_runtime_snapshot_freshness_evidence,
)


def test_reports_fresh_when_all_snapshots_are_within_age_limit():
    payload = build_runtime_snapshot_freshness_report(
        {
            "feed_runtime": {"source": "feed_runtime", "generated_epoch": 100.0, "market_open": True},
            "market_snapshot": {"source": "market_snapshot", "updated_epoch": 98.0, "market_open": True},
        },
        now_epoch=110.0,
        default_max_age_sec=30.0,
    ).to_payload()

    assert payload["status"] == FRESHNESS_STATUS_FRESH
    assert payload["reason_code"] == "ok"
    assert payload["fresh_count"] == 2
    assert payload["stale_count"] == 0
    assert payload["blocked_count"] == 0
    assert payload["artifacts"][0]["age_sec"] <= 30.0


def test_reports_stale_when_any_snapshot_exceeds_age_limit():
    payload = build_runtime_snapshot_freshness_report(
        {
            "feed_runtime": {"generated_epoch": 100.0},
            "market_snapshot": {"generated_epoch": 30.0},
        },
        now_epoch=110.0,
        default_max_age_sec=30.0,
    ).to_payload()

    assert payload["status"] == FRESHNESS_STATUS_STALE
    assert payload["reason_code"] == STALE_TIMESTAMP_REASON
    assert payload["fresh_count"] == 1
    assert payload["stale_count"] == 1
    stale = [item for item in payload["artifacts"] if item["freshness_state"] == FRESHNESS_STATUS_STALE]
    assert stale[0]["artifact_name"] == "market_snapshot"


def test_blocks_when_snapshot_has_no_timestamp():
    payload = build_runtime_snapshot_freshness_report(
        {"runtime_health": {"source": "runtime_health", "market_open": True}},
        now_epoch=110.0,
    ).to_payload()

    assert payload["status"] == FRESHNESS_STATUS_BLOCKED
    assert payload["reason_code"] == MISSING_TIMESTAMP_REASON
    assert payload["blocked_count"] == 1
    assert payload["artifacts"][0]["valid"] is False


def test_blocks_invalid_snapshot_payload():
    payload = build_runtime_snapshot_freshness_report(
        {"feed_runtime": ["not", "a", "mapping"]},
        now_epoch=110.0,
    ).to_payload()

    assert payload["status"] == FRESHNESS_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_SNAPSHOT_REASON
    assert payload["artifacts"][0]["reason_code"] == INVALID_SNAPSHOT_REASON


def test_blocks_future_timestamp_beyond_tolerance():
    payload = build_runtime_snapshot_freshness_report(
        {"feed_runtime": {"generated_epoch": 200.0}},
        now_epoch=100.0,
        future_skew_tolerance_sec=5.0,
    ).to_payload()

    assert payload["status"] == FRESHNESS_STATUS_BLOCKED
    assert payload["reason_code"] == FUTURE_TIMESTAMP_REASON
    assert payload["artifacts"][0]["age_sec"] < 0


def test_accepts_iso_timestamp_values():
    payload = build_runtime_snapshot_freshness_report(
        {"market_snapshot": {"generated_at": "2026-05-27T10:00:00Z"}},
        now_epoch=1779876030.0,
        default_max_age_sec=60.0,
    ).to_payload()

    assert payload["status"] == FRESHNESS_STATUS_FRESH
    assert payload["artifacts"][0]["timestamp_key"] == "generated_at"
    assert payload["artifacts"][0]["age_sec"] == 30.0


def test_supports_per_artifact_max_age_override():
    payload = build_runtime_snapshot_freshness_report(
        {
            "feed_runtime": {"generated_epoch": 100.0},
            "top_opportunities": {"generated_epoch": 80.0},
        },
        now_epoch=110.0,
        default_max_age_sec=20.0,
        max_age_by_artifact={"top_opportunities": 40.0},
    ).to_payload()

    assert payload["status"] == FRESHNESS_STATUS_FRESH
    by_name = {item["artifact_name"]: item for item in payload["artifacts"]}
    assert by_name["top_opportunities"]["max_age_sec"] == 40.0
    assert by_name["top_opportunities"]["freshness_state"] == FRESHNESS_STATUS_FRESH


def test_blocks_empty_snapshot_input():
    payload = build_runtime_snapshot_freshness_report({}, now_epoch=100.0).to_payload()

    assert payload["status"] == FRESHNESS_STATUS_BLOCKED
    assert payload["reason_code"] == NO_SNAPSHOTS_REASON
    assert payload["artifact_count"] == 0


def test_blocks_invalid_freshness_config():
    payload = build_runtime_snapshot_freshness_report(
        {"feed_runtime": {"generated_epoch": 100.0}},
        now_epoch=100.0,
        default_max_age_sec=0,
    ).to_payload()

    assert payload["status"] == FRESHNESS_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_FRESHNESS_CONFIG_REASON


def test_writes_read_only_evidence_file(tmp_path):
    target = tmp_path / "runtime_snapshot_freshness_latest.json"
    report = build_runtime_snapshot_freshness_report(
        {"feed_runtime": {"generated_epoch": 100.0}},
        now_epoch=101.0,
    )

    out = write_runtime_snapshot_freshness_evidence(report, target)

    assert out == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["source"] == RUNTIME_SNAPSHOT_FRESHNESS_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False


def test_payload_is_json_serializable_and_non_action():
    payload = build_runtime_snapshot_freshness_report(
        {"feed_runtime": {"generated_epoch": 100.0}},
        now_epoch=101.0,
    ).to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["source"] == RUNTIME_SNAPSHOT_FRESHNESS_SOURCE
    assert decoded["read_only"] is True
    assert decoded["append"] is False
    assert decoded["is_order_action"] is False
    assert decoded["broker_api_called"] is False
    assert decoded["live_order_action"] is False
    assert decoded["broker_order_action"] is False
