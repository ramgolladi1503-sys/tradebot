import os
import time
from pathlib import Path

from core.runtime_boot_identity import (
    ENV_BOOT_EPOCH,
    ENV_RUN_ID,
    RuntimeBootIdentity,
    classify_runtime_payload_freshness,
    get_runtime_boot_identity,
    stamp_runtime_payload,
)


def test_boot_identity_is_stable_inside_process(monkeypatch):
    monkeypatch.delenv(ENV_RUN_ID, raising=False)
    monkeypatch.delenv(ENV_BOOT_EPOCH, raising=False)

    first = get_runtime_boot_identity()
    second = get_runtime_boot_identity()

    assert first.run_id == second.run_id
    assert first.boot_epoch == second.boot_epoch
    assert first.pid == os.getpid()


def test_stamp_runtime_payload_adds_boot_metadata(monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-test")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "1000.0")

    payload = stamp_runtime_payload({"feed_ok": False}, writer="unit.test")

    assert payload["feed_ok"] is False
    assert payload["run_id"] == "run-test"
    assert payload["boot_epoch"] == 1000.0
    assert payload["pid"] == os.getpid()
    assert payload["writer"] == "unit.test"
    assert payload["schema_version"] == 1
    assert "ts_epoch" in payload


def test_missing_runtime_identity_is_stale(monkeypatch):
    current = RuntimeBootIdentity(run_id="run-current", boot_epoch=2000.0, pid=123)

    result = classify_runtime_payload_freshness(
        {"feed_ok": True},
        current=current,
    )

    assert result["is_current_run"] is False
    assert "missing_run_id" in result["freshness_reasons"]
    assert "missing_or_invalid_boot_epoch" in result["freshness_reasons"]
    assert "missing_writer" in result["freshness_reasons"]


def test_old_boot_epoch_is_stale():
    current = RuntimeBootIdentity(run_id="run-current", boot_epoch=2000.0, pid=123)

    result = classify_runtime_payload_freshness(
        {
            "run_id": "run-current",
            "boot_epoch": 1000.0,
            "writer": "unit.test",
            "schema_version": 1,
        },
        current=current,
    )

    assert result["is_current_run"] is False
    assert "older_than_current_boot" in result["freshness_reasons"]


def test_mtime_older_than_current_boot_is_stale(tmp_path: Path):
    current = RuntimeBootIdentity(run_id="run-current", boot_epoch=time.time() + 10, pid=123)
    target = tmp_path / "feed_runtime_latest.json"
    target.write_text("{}", encoding="utf-8")

    result = classify_runtime_payload_freshness(
        {
            "run_id": "run-current",
            "boot_epoch": current.boot_epoch,
            "writer": "unit.test",
            "schema_version": 1,
        },
        path=target,
        current=current,
    )

    assert result["is_current_run"] is False
    assert "mtime_older_than_current_boot" in result["freshness_reasons"]
