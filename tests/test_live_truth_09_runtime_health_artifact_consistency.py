from __future__ import annotations

import json

from core.live_truth_runtime_health_artifact_consistency import (
    CONSISTENCY_STATUS_BLOCKED,
    CONSISTENCY_STATUS_CONSISTENT,
    CONSISTENCY_STATUS_INCONSISTENT,
    CONSISTENCY_STATUS_REVIEW,
    INCONSISTENT_MARKET_OPEN_REASON,
    INCONSISTENT_RUNTIME_MODE_REASON,
    INVALID_ARTIFACT_REASON,
    INVALID_CONFIG_REASON,
    MISSING_IDENTITY_FIELD_REASON,
    MISSING_REQUIRED_ARTIFACT_REASON,
    NO_ARTIFACTS_REASON,
    RUNTIME_HEALTH_ARTIFACT_CONSISTENCY_SOURCE,
    build_runtime_health_artifact_consistency_report,
    write_runtime_health_artifact_consistency_evidence,
)


def test_reports_consistent_runtime_health_artifacts():
    payload = build_runtime_health_artifact_consistency_report(
        {
            "runtime_snapshot_latest": {
                "source": "runtime_snapshot",
                "runtime_mode": "LIVE",
                "market_open": True,
                "runtime_state": "RUNNING",
                "feed_ok": True,
                "ws_connected": True,
            },
            "feed_runtime_latest": {
                "source": "feed_runtime",
                "mode": "live",
                "is_market_open": "true",
                "state": "running",
                "feed_healthy": "healthy",
                "websocket_connected": "connected",
            },
        },
        required_artifacts=("runtime_snapshot_latest", "feed_runtime_latest"),
        required_fields=("runtime_mode", "market_open", "runtime_state", "feed_ok", "ws_connected"),
    ).to_payload()

    assert payload["status"] == CONSISTENCY_STATUS_CONSISTENT
    assert payload["valid_artifact_count"] == 2
    assert payload["missing_required_artifacts"] == []
    assert payload["inconsistent_fields"] == []
    assert payload["field_values"]["runtime_mode"] == ["live"]
    assert payload["field_values"]["market_open"] == [True]
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False


def test_blocks_when_required_artifact_is_missing():
    payload = build_runtime_health_artifact_consistency_report(
        {
            "runtime_snapshot_latest": {
                "runtime_mode": "LIVE",
                "market_open": True,
                "runtime_state": "RUNNING",
            },
        },
        required_artifacts=("runtime_snapshot_latest", "feed_runtime_latest"),
    ).to_payload()

    assert payload["status"] == CONSISTENCY_STATUS_BLOCKED
    assert payload["reason_code"] == MISSING_REQUIRED_ARTIFACT_REASON
    assert payload["missing_required_artifacts"] == ["feed_runtime_latest"]


def test_blocks_when_artifact_payload_is_invalid():
    payload = build_runtime_health_artifact_consistency_report(
        {
            "runtime_snapshot_latest": {
                "runtime_mode": "LIVE",
                "market_open": True,
                "runtime_state": "RUNNING",
            },
            "feed_runtime_latest": ["bad", "payload"],
        },
        required_artifacts=("runtime_snapshot_latest", "feed_runtime_latest"),
    ).to_payload()

    assert payload["status"] == CONSISTENCY_STATUS_BLOCKED
    assert INVALID_ARTIFACT_REASON in payload["reasons"]
    assert payload["valid_artifact_count"] == 1


def test_reports_inconsistent_runtime_mode():
    payload = build_runtime_health_artifact_consistency_report(
        {
            "runtime_snapshot_latest": {
                "runtime_mode": "LIVE",
                "market_open": True,
                "runtime_state": "RUNNING",
            },
            "feed_runtime_latest": {
                "runtime_mode": "PAPER",
                "market_open": True,
                "runtime_state": "RUNNING",
            },
        },
    ).to_payload()

    assert payload["status"] == CONSISTENCY_STATUS_INCONSISTENT
    assert payload["reason_code"] == INCONSISTENT_RUNTIME_MODE_REASON
    assert payload["inconsistent_fields"] == ["runtime_mode"]
    assert payload["field_values"]["runtime_mode"] == ["paper", "live"]


def test_reports_inconsistent_market_open():
    payload = build_runtime_health_artifact_consistency_report(
        {
            "runtime_snapshot_latest": {
                "runtime_mode": "LIVE",
                "market_open": True,
                "runtime_state": "RUNNING",
            },
            "top_opportunities_latest": {
                "runtime_mode": "LIVE",
                "market_open": False,
                "runtime_state": "RUNNING",
            },
        },
    ).to_payload()

    assert payload["status"] == CONSISTENCY_STATUS_INCONSISTENT
    assert payload["reason_code"] == INCONSISTENT_MARKET_OPEN_REASON
    assert payload["inconsistent_fields"] == ["market_open"]


def test_reports_review_when_required_identity_field_is_missing():
    payload = build_runtime_health_artifact_consistency_report(
        {
            "runtime_snapshot_latest": {
                "runtime_mode": "LIVE",
                "market_open": True,
                "runtime_state": "RUNNING",
            },
            "feed_runtime_latest": {
                "runtime_mode": "LIVE",
                "market_open": True,
            },
        },
        required_fields=("runtime_mode", "market_open", "runtime_state"),
    ).to_payload()

    assert payload["status"] == CONSISTENCY_STATUS_REVIEW
    assert payload["reason_code"] == MISSING_IDENTITY_FIELD_REASON
    assert payload["metadata"]["missing_required_fields"] == ["feed_runtime_latest:runtime_state"]


def test_blocks_when_no_artifacts_are_available():
    payload = build_runtime_health_artifact_consistency_report({}).to_payload()

    assert payload["status"] == CONSISTENCY_STATUS_BLOCKED
    assert payload["reason_code"] == NO_ARTIFACTS_REASON
    assert payload["artifact_count"] == 0


def test_blocks_invalid_config():
    payload = build_runtime_health_artifact_consistency_report(
        {
            "runtime_snapshot_latest": {
                "runtime_mode": "LIVE",
                "market_open": True,
                "runtime_state": "RUNNING",
            },
        },
        required_fields=("not_a_real_field",),
    ).to_payload()

    assert payload["status"] == CONSISTENCY_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_CONFIG_REASON


def test_extracts_artifacts_from_nested_container():
    payload = build_runtime_health_artifact_consistency_report(
        {
            "artifacts": {
                "runtime_snapshot_latest": {
                    "runtime_mode": "LIVE",
                    "market_open": True,
                    "runtime_state": "RUNNING",
                },
                "top_opportunities_latest": {
                    "mode": "live",
                    "is_market_open": "yes",
                    "status": "running",
                },
            }
        }
    ).to_payload()

    assert payload["status"] == CONSISTENCY_STATUS_CONSISTENT
    assert payload["artifact_count"] == 2


def test_writes_read_only_evidence_file(tmp_path):
    target = tmp_path / "runtime_health_artifact_consistency_latest.json"
    report = build_runtime_health_artifact_consistency_report(
        {
            "runtime_snapshot_latest": {
                "runtime_mode": "LIVE",
                "market_open": True,
                "runtime_state": "RUNNING",
            },
            "top_opportunities_latest": {
                "runtime_mode": "LIVE",
                "market_open": True,
                "runtime_state": "RUNNING",
            },
        }
    )

    out = write_runtime_health_artifact_consistency_evidence(report, target)

    assert out == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["source"] == RUNTIME_HEALTH_ARTIFACT_CONSISTENCY_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False


def test_payload_is_json_serializable():
    payload = build_runtime_health_artifact_consistency_report(
        {
            "runtime_snapshot_latest": {
                "runtime_mode": "LIVE",
                "market_open": True,
                "runtime_state": "RUNNING",
            },
            "top_opportunities_latest": {
                "runtime_mode": "LIVE",
                "market_open": True,
                "runtime_state": "RUNNING",
            },
        }
    ).to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["source"] == RUNTIME_HEALTH_ARTIFACT_CONSISTENCY_SOURCE
    assert decoded["read_only"] is True
    assert decoded["append"] is False
