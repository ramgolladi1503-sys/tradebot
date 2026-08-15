import json

from core.feed.artifact_loader import load_current_feed_runtime, load_current_feed_truth
from core.feed.artifact_provenance import stamp_feed_runtime_provenance, stamp_feed_truth_provenance
from core.feed.lineage import build_truth_lineage
from core.feed.feed_epoch import _reset_feed_epoch_for_tests
from core.runtime_truth_integrity import build_truth_integrity_payload


def setup_function():
    _reset_feed_epoch_for_tests()


def _write(path, payload, *, truth=False):
    stamped = stamp_feed_truth_provenance(payload) if truth else stamp_feed_runtime_provenance(payload)
    stamped.update(build_truth_integrity_payload(source_payload=stamped, transport_state="CONNECTED", feed_truth_state="LIVE", heartbeat_epoch=stamped["produced_at"]))
    path.write_text(json.dumps(stamped), encoding="utf-8")
    return stamped


def test_exact_lineage_is_accepted_and_idempotent(tmp_path):
    truth_path = tmp_path / "truth.json"
    truth = _write(truth_path, {"feed_fresh": True}, truth=True)
    runtime_path = tmp_path / "runtime.json"
    runtime = stamp_feed_runtime_provenance({"feed_ok": True}, truth_payload=truth)
    runtime.update(build_truth_integrity_payload(source_payload=runtime, transport_state="CONNECTED", feed_truth_state="LIVE", heartbeat_epoch=runtime["produced_at"]))
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
    first = load_current_feed_runtime(runtime_path, truth_path)
    second = load_current_feed_runtime(runtime_path, truth_path)
    assert first["valid"] is True and second == first


def test_missing_and_mutated_lineage_fail_closed(tmp_path):
    truth_path = tmp_path / "truth.json"
    truth = _write(truth_path, {"feed_fresh": True}, truth=True)
    runtime_path = tmp_path / "runtime.json"
    runtime = stamp_feed_runtime_provenance({"feed_ok": True}, truth_payload=truth)
    runtime.update(build_truth_integrity_payload(source_payload=runtime, transport_state="CONNECTED", feed_truth_state="LIVE", heartbeat_epoch=runtime["produced_at"]))
    runtime.pop("truth_lineage")
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
    assert load_current_feed_runtime(runtime_path, truth_path)["reason_code"] == "MISSING_REQUIRED_FIELD"
    runtime["truth_lineage"] = build_truth_lineage(truth)
    runtime["truth_lineage"]["truth_integrity"] = "forged"
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
    assert load_current_feed_runtime(runtime_path, truth_path)["reason_code"] == "INTEGRITY_MISMATCH"


def test_same_values_different_truth_rejected(tmp_path):
    truth_path = tmp_path / "truth.json"
    truth = _write(truth_path, {"feed_fresh": True}, truth=True)
    runtime_path = tmp_path / "runtime.json"
    runtime = stamp_feed_runtime_provenance({"feed_ok": True}, truth_payload=truth)
    runtime.update(build_truth_integrity_payload(source_payload=runtime, transport_state="CONNECTED", feed_truth_state="LIVE", heartbeat_epoch=runtime["produced_at"]))
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
    mutated_truth = dict(truth)
    mutated_truth["feed_fresh"] = False
    mutated_truth.update(build_truth_integrity_payload(source_payload=mutated_truth, transport_state="CONNECTED", feed_truth_state="DEGRADED", heartbeat_epoch=mutated_truth["produced_at"]))
    truth_path.write_text(json.dumps(mutated_truth), encoding="utf-8")
    assert load_current_feed_runtime(runtime_path, truth_path)["reason_code"] == "LINEAGE_INTEGRITY_MISMATCH"
