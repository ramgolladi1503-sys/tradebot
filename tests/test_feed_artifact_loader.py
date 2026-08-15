import json

import pytest

from core.feed.artifact_loader import load_current_feed_runtime, load_current_feed_truth
from core.feed.artifact_provenance import stamp_feed_runtime_provenance, stamp_feed_truth_provenance
from core.feed.feed_epoch import _reset_feed_epoch_for_tests
from core.runtime_truth_integrity import build_truth_integrity_payload


def setup_function():
    _reset_feed_epoch_for_tests()


def _write(path, payload, *, truth=False, truth_payload=None):
    stamped = stamp_feed_truth_provenance(payload) if truth else stamp_feed_runtime_provenance(payload)
    if truth_payload is not None:
        stamped = stamp_feed_runtime_provenance(payload, truth_payload=truth_payload)
    stamped.update(build_truth_integrity_payload(source_payload=stamped, transport_state="CONNECTED", feed_truth_state="LIVE", heartbeat_epoch=stamped["produced_at"]))
    path.write_text(json.dumps(stamped), encoding="utf-8")
    return stamped


def test_valid_truth_and_runtime_are_accepted(tmp_path):
    truth = tmp_path / "truth.json"; runtime = tmp_path / "runtime.json"
    truth_payload = _write(truth, {"feed_fresh": True}, truth=True); _write(runtime, {"feed_ok": False}, truth_payload=truth_payload)
    assert load_current_feed_truth(truth)["reason_code"] == "VALID_CURRENT_ARTIFACT"
    result = load_current_feed_runtime(runtime, truth)
    assert result["valid"] is True and result["payload"]["feed_ok"] is False


def test_missing_and_malformed_fail_closed(tmp_path):
    assert load_current_feed_truth(tmp_path / "missing")["reason_code"] == "MISSING_ARTIFACT"
    bad = tmp_path / "bad"; bad.write_text("[]", encoding="utf-8")
    assert load_current_feed_truth(bad)["reason_code"] == "MALFORMED_ARTIFACT"


@pytest.mark.parametrize("field", ["run_id", "boot_epoch", "feed_epoch", "writer", "schema_version", "produced_at"])
def test_missing_truth_field_fails_closed(tmp_path, field):
    path = tmp_path / "truth"; payload = _write(path, {"feed_fresh": True}, truth=True); payload.pop(field)
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_current_feed_truth(path)["reason_code"] == "MISSING_REQUIRED_FIELD"


def test_runtime_requires_feed_ok(tmp_path):
    path = tmp_path / "runtime.json"; payload = _write(path, {"runtime_state": "RUNNING", "feed_ok": False}); payload.pop("feed_ok")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_current_feed_runtime(path)["reason_code"] == "MISSING_REQUIRED_FIELD"


@pytest.mark.parametrize("field,value", [("writer", "bad"), ("schema_version", 99), ("run_id", "old"), ("boot_epoch", -1), ("feed_epoch", 1)])
def test_provenance_mismatch_fails_closed(tmp_path, field, value):
    path = tmp_path / "runtime.json"; payload = _write(path, {"feed_ok": True}); payload[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_current_feed_runtime(path)["valid"] is False


def test_wrong_epoch_type_and_integrity_mismatch_fail_closed(tmp_path):
    truth_path = tmp_path / "truth.json"; truth_payload = _write(truth_path, {"feed_fresh": True}, truth=True)
    path = tmp_path / "runtime.json"; payload = _write(path, {"feed_ok": True}, truth_payload=truth_payload); payload["feed_epoch"] = "0"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_current_feed_runtime(path, truth_path)["reason_code"] == "EPOCH_MISMATCH"
    payload["feed_epoch"] = 0; payload["feed_ok"] = False; path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_current_feed_runtime(path, truth_path)["reason_code"] == "INTEGRITY_MISMATCH"


def test_returned_payload_is_detached(tmp_path):
    truth_path = tmp_path / "truth.json"; truth_payload = _write(truth_path, {"feed_fresh": True}, truth=True)
    path = tmp_path / "runtime.json"; _write(path, {"feed_ok": True, "nested": {"x": 1}}, truth_payload=truth_payload)
    result = load_current_feed_runtime(path, truth_path); result["payload"]["nested"]["x"] = 9
    assert load_current_feed_runtime(path, truth_path)["payload"]["nested"]["x"] == 1
