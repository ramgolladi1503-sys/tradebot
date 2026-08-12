import json

import core.runtime_health as runtime_health
from core.runtime_truth_integrity import truth_hash_from_mapping


def test_runtime_health_prefers_persisted_snapshot_hash_over_stale_debug(monkeypatch, tmp_path):
    persisted = {
        "ts_epoch": 10.0,
        "ws_connected": True,
        "feed_truth_state": "LIVE",
        "transport_state": "CONNECTED",
        "value": "current",
    }
    excluded = (
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
    persisted.update(
        {
            "snapshot_hash": truth_hash_from_mapping(persisted, exclude_keys=excluded),
            "snapshot_hash_version": 1,
            "truth_integrity_status": "OK",
        }
    )
    path = tmp_path / "feed_runtime_latest.json"
    path.write_text(json.dumps(persisted))

    stale_debug = dict(persisted)
    stale_debug["snapshot_hash"] = "older-in-memory-hash"
    monkeypatch.setattr(runtime_health, "get_feed_debug", lambda now_epoch=None: stale_debug)
    monkeypatch.setattr(runtime_health, "runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(runtime_health, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(
        runtime_health,
        "get_freshness_status",
        lambda force=False: {"market_open": False, "mode": "LIVE", "state": "OK", "reasons": []},
    )

    result = runtime_health.get_runtime_health(now_epoch=10.0)
    assert result["feed"]["snapshot_hash"] == persisted["snapshot_hash"]
    assert result["feed"]["snapshot_hash_match"] is True
    assert result["feed"]["truth_integrity_status"] == "OK"
    assert result["feed"]["truth_integrity_alert_count"] == 0


def test_runtime_health_does_not_verify_in_memory_hash_against_empty_persisted_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_health, "runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(runtime_health, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(
        runtime_health,
        "get_freshness_status",
        lambda force=False: {"market_open": True, "mode": "LIVE", "state": "OK", "reasons": []},
    )
    monkeypatch.setattr(
        runtime_health,
        "get_feed_debug",
        lambda now_epoch=None: {
            "ws_connected": True,
            "feed_truth_state": "LIVE",
            "transport_state": "CONNECTED",
            "snapshot_hash": "in-memory-finalized-hash",
        },
    )
    (tmp_path / "feed_runtime_latest.json").write_text("{}")

    result = runtime_health.get_runtime_health(now_epoch=10.0)
    feed = result["feed"]
    assert feed["snapshot_hash"] is None
    assert feed["snapshot_hash_expected"] is None
    assert feed["snapshot_hash_match"] is False
    assert feed["truth_integrity_alerts"] == []


def test_runtime_health_still_fails_closed_for_persisted_missing_hash(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_health, "runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(runtime_health, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(
        runtime_health,
        "get_freshness_status",
        lambda force=False: {"market_open": True, "mode": "LIVE", "state": "OK", "reasons": []},
    )
    monkeypatch.setattr(
        runtime_health,
        "get_feed_debug",
        lambda now_epoch=None: {"ws_connected": True, "feed_truth_state": "LIVE", "transport_state": "CONNECTED"},
    )
    (tmp_path / "feed_runtime_latest.json").write_text(
        json.dumps({"ws_connected": True, "feed_truth_state": "LIVE", "transport_state": "CONNECTED"})
    )

    result = runtime_health.get_runtime_health(now_epoch=10.0)
    assert any(alert["code"] == "SNAPSHOT_HASH_MISSING" for alert in result["feed"]["truth_integrity_alerts"])
