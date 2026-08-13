from __future__ import annotations

import json

import pytest

import core.orchestrator as orchestrator
from core.feed.artifact_loader import FEED_RUNTIME_CANONICAL_WRITER, FEED_RUNTIME_SCHEMA_VERSION
from core.feed.artifact_provenance import stamp_feed_runtime_provenance, stamp_feed_truth_provenance
from core.runtime_truth_integrity import build_truth_integrity_payload
from core.feed.feed_epoch import current_feed_epoch
from core.runtime_boot_identity import get_runtime_boot_identity
from core.runtime_truth_integrity import truth_hash_from_mapping


def _runtime_artifact(runtime_state: str) -> dict:
    identity = get_runtime_boot_identity()
    payload = {
        "run_id": identity.run_id,
        "boot_epoch": identity.boot_epoch,
        "feed_epoch": current_feed_epoch(),
        "writer": FEED_RUNTIME_CANONICAL_WRITER,
        "schema_version": FEED_RUNTIME_SCHEMA_VERSION,
        "produced_at": 1_000_000_000.0,
        "feed_ok": False,
        "runtime_state": runtime_state,
        "source": "unit_test",
        "ws_connected": False,
    }
    payload["snapshot_hash"] = truth_hash_from_mapping(payload)
    return payload


def _truth_artifact() -> dict:
    payload = stamp_feed_truth_provenance({"feed_fresh": False})
    payload.update(build_truth_integrity_payload(source_payload=payload, transport_state="DISCONNECTED", feed_truth_state="DEAD", heartbeat_epoch=payload["produced_at"]))
    return payload


@pytest.mark.parametrize("runtime_state", ["SUBSCRIBE_FAILED", "AUTH_BLOCKED", "IMPORT_MISSING"])
def test_valid_current_startup_failure_state_is_returned(monkeypatch, tmp_path, runtime_state):
    path = tmp_path / "feed_runtime_latest.json"
    truth = _truth_artifact()
    runtime = stamp_feed_runtime_provenance(_runtime_artifact(runtime_state), truth_payload=truth)
    runtime.update(build_truth_integrity_payload(source_payload=runtime, transport_state="DISCONNECTED", feed_truth_state="DEAD", heartbeat_epoch=runtime["produced_at"]))
    path.write_text(json.dumps(runtime), encoding="utf-8")
    (tmp_path / "feed_truth_latest.json").write_text(json.dumps(truth), encoding="utf-8")
    monkeypatch.setattr(orchestrator, "logs_dir", lambda: tmp_path)

    snapshot, age = orchestrator._validated_depth_ws_startup_snapshot()

    assert snapshot["runtime_state"] == runtime_state
    assert age is not None


@pytest.mark.parametrize(
    "reason_code",
    [
        "MISSING_ARTIFACT",
        "MALFORMED_ARTIFACT",
        "SESSION_MISMATCH",
        "EPOCH_MISMATCH",
        "WRITER_MISMATCH",
        "SCHEMA_MISMATCH",
        "INTEGRITY_MISMATCH",
    ],
)
def test_invalid_artifact_fails_closed(monkeypatch, tmp_path, reason_code):
    path = tmp_path / "feed_runtime_latest.json"
    path.write_text(json.dumps({"feed_ok": True, "runtime_state": "READY"}), encoding="utf-8")
    monkeypatch.setattr(orchestrator, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(
        orchestrator,
        "load_current_feed_runtime",
        lambda _path: {"valid": False, "reason_code": reason_code, "payload": {}},
    )

    with pytest.raises(RuntimeError, match=rf"feed_runtime={reason_code}"):
        orchestrator._validated_depth_ws_startup_snapshot()


def test_startup_helper_has_no_legacy_snapshot_fallback():
    source = orchestrator._validated_depth_ws_startup_snapshot.__code__
    assert "read_latest_runtime_snapshot" not in source.co_names
