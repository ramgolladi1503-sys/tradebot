from core.feed.runtime_store import _canonical_runtime_artifact_payload
from core.runtime_truth_integrity import (
    build_truth_integrity_alerts,
    build_truth_integrity_payload,
    truth_hash_from_mapping,
)


_INTEGRITY_EXCLUDED = (
    "snapshot_hash",
    "snapshot_hash_version",
    "transport_heartbeat",
    "transport_heartbeat_epoch",
    "transport_heartbeat_age_sec",
    "transport_heartbeat_source",
    "transport_heartbeat_state",
    "transport_heartbeat_reason",
    "truth_integrity",
    "truth_integrity_alerts",
    "truth_integrity_alert_count",
    "truth_integrity_status",
)


def test_runtime_store_finalizes_semantic_fields_before_hashing():
    artifact = _canonical_runtime_artifact_payload(
        {
            "ts_epoch": 1786510000.0,
            "ws_connected": True,
            "market_open": True,
            "runtime_state": "LIVE",
            "last_tick_age_sec": 0.1,
            "source": "test",
        },
        ts_epoch=1786510000.0,
    )

    recomputed = truth_hash_from_mapping(artifact, exclude_keys=_INTEGRITY_EXCLUDED)
    assert artifact["snapshot_hash"] == recomputed
    assert artifact["truth_integrity_status"] == "OK"
    assert artifact["is_order_action"] is False
    assert artifact["broker_api_called"] is False


def test_runtime_store_rejects_stale_embedded_hash():
    artifact = _canonical_runtime_artifact_payload(
        {
            "ts_epoch": 1786510000.0,
            "ws_connected": True,
            "market_open": True,
            "runtime_state": "LIVE",
            "last_tick_age_sec": 0.1,
            "snapshot_hash": "stale-hash",
        },
        ts_epoch=1786510000.0,
    )

    assert artifact["truth_integrity_status"] == "ALERT"
    assert any(
        alert["code"] == "SNAPSHOT_HASH_MISMATCH"
        for alert in artifact["truth_integrity_alerts"]
    )


def test_semantic_mutation_is_detected_but_excluded_volatile_fields_are_not():
    payload = build_truth_integrity_payload(
        source_payload={"ts_epoch": 1.0, "feed_truth_state": "LIVE", "value": 7},
        transport_state="CONNECTED",
        feed_truth_state="LIVE",
        heartbeat_epoch=1.0,
    )
    semantic = {"ts_epoch": 1.0, "feed_truth_state": "LIVE", "value": 8}
    semantic.update(payload)
    expected = truth_hash_from_mapping(semantic, exclude_keys=_INTEGRITY_EXCLUDED)
    assert expected != payload["snapshot_hash"]

    volatile = {"ts_epoch": 1.0, "feed_truth_state": "LIVE", "value": 7}
    volatile.update(payload)
    volatile["transport_heartbeat_age_sec"] = 99.0
    recomputed = truth_hash_from_mapping(volatile, exclude_keys=_INTEGRITY_EXCLUDED)
    assert recomputed == payload["snapshot_hash"]


def test_missing_hash_remains_a_fail_closed_alert():
    alerts = build_truth_integrity_alerts(
        transport_state="CONNECTED",
        feed_truth_state="LIVE",
        snapshot_hash=None,
        expected_snapshot_hash=None,
    )
    assert alerts[0]["code"] == "SNAPSHOT_HASH_MISSING"
