import json

import pytest

from core.feed.artifact_loader import load_current_feed_runtime
from tests.fixtures.canonical_feed_factory import make_valid_canonical_feed_pair


@pytest.mark.parametrize(
    "mutation",
    [
        "run_id",
        "boot_epoch",
        "feed_epoch",
        "writer",
        "schema_version",
        "snapshot_hash",
        "truth_lineage",
    ],
)
def test_factory_negative_controls_reject_runtime_mutation(tmp_path, mutation):
    _, runtime_path = make_valid_canonical_feed_pair(tmp_path)
    payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    if mutation == "truth_lineage":
        payload.pop("truth_lineage", None)
    elif mutation == "snapshot_hash":
        payload[mutation] = "forged"
    elif mutation == "run_id":
        payload[mutation] = "other-session"
    elif mutation == "boot_epoch":
        payload[mutation] = float(payload[mutation]) + 1.0
    elif mutation == "feed_epoch":
        payload[mutation] = int(payload[mutation]) + 1
    elif mutation == "writer":
        payload[mutation] = "legacy.writer"
    else:
        payload[mutation] = int(payload[mutation]) + 1
    runtime_path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_current_feed_runtime(runtime_path)
    assert loaded["valid"] is False


def test_factory_rejects_missing_and_malformed_truth(tmp_path):
    _, runtime_path = make_valid_canonical_feed_pair(tmp_path)
    truth_path = tmp_path / "feed_truth_latest.json"
    truth_path.write_text("{}", encoding="utf-8")
    assert load_current_feed_runtime(runtime_path)["valid"] is False
    truth_path.write_text("not-json", encoding="utf-8")
    assert load_current_feed_runtime(runtime_path)["valid"] is False


def test_factory_rejects_same_identity_different_truth(tmp_path):
    truth_path, runtime_path = make_valid_canonical_feed_pair(tmp_path)
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    truth["feed_truth_state"] = "MUTATED"
    truth_path.write_text(json.dumps(truth), encoding="utf-8")
    assert load_current_feed_runtime(runtime_path)["valid"] is False
