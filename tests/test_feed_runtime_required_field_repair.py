import json

from core.feed.artifact_loader import load_current_feed_runtime
from core.feed.runtime_store import _canonical_runtime_artifact_payload
from core.runtime_boot_identity import get_runtime_boot_identity


def test_first_runtime_write_bootstraps_truth_lineage_and_is_loadable(tmp_path, monkeypatch):
    monkeypatch.setattr("core.feed.runtime_store.repo_root", lambda: tmp_path)
    monkeypatch.setattr("core.feed.runtime_store._db_path", lambda: tmp_path / "runtime.sqlite")
    monkeypatch.setattr("core.feed.artifact_loader.logs_dir", lambda: tmp_path)
    monkeypatch.setattr("core.paths.logs_dir", lambda: tmp_path)
    monkeypatch.setattr("core.runtime_feed_truth_snapshot.repo_logs_dir", lambda: tmp_path)
    monkeypatch.setattr("core.runtime_feed_truth_snapshot.runtime_dir", lambda: tmp_path)
    monkeypatch.setattr("core.runtime_feed_truth_snapshot.logs_dir", lambda: tmp_path)

    artifact = _canonical_runtime_artifact_payload(
        {"ws_connected": None, "runtime_state": "STARTING", "market_open": True},
        ts_epoch=100.0,
    )
    runtime_path = tmp_path / "feed_runtime_latest.json"
    truth_path = tmp_path / "feed_truth_latest.json"
    runtime_path.write_text(json.dumps(artifact), encoding="utf-8")

    result = load_current_feed_runtime(runtime_path, truth_path)

    assert truth_path.exists()
    assert result["valid"] is True
    assert result["payload"]["truth_lineage"]["truth_run_id"] == get_runtime_boot_identity().run_id


def test_missing_truth_lineage_remains_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr("core.feed.artifact_loader.logs_dir", lambda: tmp_path)
    runtime = {"run_id": "x", "boot_epoch": 1.0, "feed_epoch": 0, "writer": "feed_runtime.canonical", "schema_version": 1, "produced_at": 1.0, "feed_ok": False}
    (tmp_path / "feed_runtime_latest.json").write_text(json.dumps(runtime), encoding="utf-8")
    result = load_current_feed_runtime(tmp_path / "feed_runtime_latest.json")
    assert result["reason_code"] == "MISSING_REQUIRED_FIELD"
    assert "truth_lineage" in result["reasons"]
