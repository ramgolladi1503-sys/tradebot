from __future__ import annotations

from config import config as cfg
from config import feed_runtime_reliability as reliability_cfg
from core.runtime_snapshot_store import (
    build_snapshot_envelope,
    read_ranked_pipeline_snapshot,
    read_snapshot,
    write_snapshot_atomic,
)


def test_runtime_snapshot_store_writes_expected_envelope(tmp_path):
    path = tmp_path / "runtime" / "advisory_latest.json"
    payload = {"rows": [{"advisory_id": "ADV-1", "symbol": "NIFTY"}], "row_count": 1}

    written = write_snapshot_atomic(path, payload=payload, producer="unit_test")
    loaded = read_snapshot(path)

    assert written == path
    assert loaded["schema_version"] == 1
    assert loaded["producer"] == "unit_test"
    assert loaded["payload"] == payload


def test_runtime_snapshot_envelope_preserves_payload_roundtrip():
    payload = {"ok": True, "count": 2}

    wrapped = build_snapshot_envelope(payload=payload, producer="unit_test", generated_at="2026-03-10T12:00:00Z")

    assert wrapped == {
        "schema_version": 1,
        "generated_at": "2026-03-10T12:00:00Z",
        "producer": "unit_test",
        "payload": payload,
    }


def test_runtime_snapshot_atomic_writer_updates_sidecar_hash_on_content_change(tmp_path):
    path = tmp_path / "runtime" / "advisory_latest.json"
    first_written = write_snapshot_atomic(path, payload={"run": 1}, producer="unit_test")
    hash_path = path.with_name(f"{path.name}.sha256")
    first_hash = hash_path.read_text(encoding="utf-8")

    second_written = write_snapshot_atomic(path, payload={"run": 2}, producer="unit_test")
    second_hash = hash_path.read_text(encoding="utf-8")

    assert first_written == path
    assert second_written == path
    assert read_snapshot(path)["payload"] == {"run": 2}
    assert first_hash != second_hash


def test_runtime_snapshot_store_exposes_ranked_pipeline_reader(tmp_path, monkeypatch):
    path = tmp_path / "runtime" / "opportunities" / "ranked_pipeline_latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_snapshot_atomic(path, payload={"reports": []}, producer="unit_test")
    monkeypatch.setattr("core.runtime_snapshot_store.RANKED_PIPELINE_LATEST_PATH", path)

    loaded = read_ranked_pipeline_snapshot()

    assert loaded["payload"] == {"reports": []}


import pytest

import core.feed.runtime_store as feed_runtime_store


@pytest.fixture(autouse=True)
def _isolated_feed_snapshot_queue(monkeypatch):
    feed_runtime_store.reset_runtime_persistence_for_tests()
    monkeypatch.setattr(feed_runtime_store, "_ensure_runtime_worker", lambda: None)
    yield
    feed_runtime_store.reset_runtime_persistence_for_tests()


def _feed_snapshot(*, session="session-a", value=1, epoch=3, source="test", runtime_state="LIVE"):
    return {
        "feed_session_id": session,
        "run_id": session,
        "boot_epoch": 2,
        "feed_epoch": epoch,
        "source": source,
        "runtime_state": runtime_state,
        "state_value": value,
    }


def test_feed_runtime_same_identity_burst_coalesces_to_latest_state():
    assert feed_runtime_store.write_runtime_snapshot(_feed_snapshot(value=1)) is True
    assert feed_runtime_store.write_runtime_snapshot(_feed_snapshot(value=2)) is True
    assert feed_runtime_store.write_runtime_snapshot(_feed_snapshot(value=3)) is True

    state = feed_runtime_store.runtime_persistence_state()
    assert state["requested"] == 3
    assert state["enqueued"] == 1
    assert state["coalesced"] == 2
    assert state["rejected"] == 0
    assert state["accounting_invariant_ok"] is True
    pending = next(iter(feed_runtime_store._RUNTIME_PENDING.values()))
    only_payload = pending[0]
    assert only_payload["state_value"] == 3
    assert pending[1] >= pending[2]


def test_feed_runtime_producer_gate_coalesces_only_same_tick_identity(monkeypatch):
    monkeypatch.setattr(reliability_cfg, "FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC", 0.5, raising=False)
    base_identity = ("session-a", 7, "RUNNING", True, False, "OK")

    assert feed_runtime_store.admit_runtime_snapshot_assembly(
        source="on_ticks", safety_identity=base_identity, now_monotonic=10.0
    ) is True
    assert feed_runtime_store.admit_runtime_snapshot_assembly(
        source="on_ticks", safety_identity=base_identity, now_monotonic=10.1
    ) is False
    # State, transport, auth, and verification transitions bypass cadence.
    for index, value in enumerate(("RECOVERY_BLOCKED", False, True, "FAILED"), start=2):
        changed = list(base_identity)
        changed[index] = value
        assert feed_runtime_store.admit_runtime_snapshot_assembly(
            source="on_ticks", safety_identity=tuple(changed), now_monotonic=10.2
        ) is True
    assert feed_runtime_store.admit_runtime_snapshot_assembly(
        source="on_ticks", safety_identity=tuple(changed), now_monotonic=10.7
    ) is True
    assert feed_runtime_store.admit_runtime_snapshot_assembly(
        source="websocket_disconnect", safety_identity=base_identity, now_monotonic=10.71
    ) is True

    state = feed_runtime_store.runtime_persistence_state()
    assert state["producer_requested"] == 8
    assert state["producer_coalesced"] == 1
    assert state["producer_admitted"] == 7
    assert state["producer_accounting_invariant_ok"] is True

    # Without a known session key, fail open on publication rather than
    # coalescing states that might belong to different feed sessions.
    assert feed_runtime_store.admit_runtime_snapshot_assembly(
        source="on_ticks", safety_identity=("", 0, "RUNNING"), now_monotonic=10.71
    ) is True


def test_runtime_snapshot_producer_gate_bounds_855_instrument_callback_burst(monkeypatch):
    monkeypatch.setattr(reliability_cfg, "FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC", 0.5, raising=False)
    safety_identity = ("session-855", "boot-1", "feed-1", 4, True, "RUNNING", False, "OK")

    admitted = [
        feed_runtime_store.admit_runtime_snapshot_assembly(
            source="on_ticks",
            safety_identity=safety_identity,
            now_monotonic=100.0 + index * 0.0005,
        )
        for index in range(855)
    ]
    assert sum(admitted) == 1
    assert feed_runtime_store.admit_runtime_snapshot_assembly(
        source="on_ticks", safety_identity=safety_identity, now_monotonic=100.5
    ) is True

    state = feed_runtime_store.runtime_persistence_state()
    assert state["producer_requested"] == 856
    assert state["producer_coalesced"] == 854
    assert state["producer_admitted"] == 2
    assert state["producer_accounting_invariant_ok"] is True
    # The producer gate does not represent queue rejects or claim sink writes.
    assert state["rejected"] == 0
    assert state["enqueued"] == 0


def test_feed_runtime_coalescing_preserves_epochs_sources_and_state_transitions():
    snapshots = (
        _feed_snapshot(epoch=3),
        _feed_snapshot(epoch=4),
        _feed_snapshot(source="watchdog"),
        _feed_snapshot(source="test", runtime_state="RECOVERY_BLOCKED"),
    )
    for snapshot in snapshots:
        assert feed_runtime_store.write_runtime_snapshot(snapshot) is True

    state = feed_runtime_store.runtime_persistence_state()
    assert state["enqueued"] == 4
    assert state["coalesced"] == 0
    assert state["queue_high_watermark"] == 4


def test_feed_runtime_queue_saturation_is_visible(monkeypatch):
    feed_runtime_store.reset_runtime_persistence_for_tests()
    monkeypatch.setattr(feed_runtime_store, "_RUNTIME_QUEUE_MAXSIZE", 1)
    feed_runtime_store.reset_runtime_persistence_for_tests()
    monkeypatch.setattr(feed_runtime_store, "_ensure_runtime_worker", lambda: None)

    assert feed_runtime_store.write_runtime_snapshot(_feed_snapshot(session="session-a")) is True
    assert feed_runtime_store.write_runtime_snapshot(_feed_snapshot(session="session-b")) is False
    state = feed_runtime_store.runtime_persistence_state()
    assert state["rejected"] == 1
    assert state["durability_degraded"] is True
    assert state["queue_high_watermark"] == 1


def test_feed_runtime_tick_snapshots_follow_configured_interval_but_transitions_are_immediate(monkeypatch):
    monkeypatch.setattr(reliability_cfg, "FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC", 60.0, raising=False)
    first = _feed_snapshot(source="on_ticks", value=1)
    second = _feed_snapshot(source="on_ticks", value=2)
    assert feed_runtime_store.write_runtime_snapshot(first) is True
    assert feed_runtime_store.write_runtime_snapshot(second) is True

    state = feed_runtime_store.runtime_persistence_state()
    assert state["requested"] == 2
    assert state["enqueued"] == 1
    assert state["coalesced"] == 1
    assert next(iter(feed_runtime_store._RUNTIME_PENDING.values()))[0]["state_value"] == 2

    # A lifecycle transition is retained even within the tick snapshot interval.
    assert feed_runtime_store.write_runtime_snapshot(
        _feed_snapshot(source="websocket_disconnect", runtime_state="DISCONNECTED")
    ) is True
    state = feed_runtime_store.runtime_persistence_state()
    assert state["enqueued"] == 2
    assert state["queue_high_watermark"] == 2


def test_producer_admission_token_prevents_second_queue_cadence_window(monkeypatch):
    monkeypatch.setattr(reliability_cfg, "FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC", 60.0, raising=False)
    snapshot = _feed_snapshot(source="on_ticks", value=1)
    assert feed_runtime_store.write_runtime_snapshot(snapshot) is True

    feed_runtime_store.mark_runtime_snapshot_producer_admitted()
    assert feed_runtime_store.write_runtime_snapshot(_feed_snapshot(source="on_ticks", value=2)) is True
    assert feed_runtime_store.consume_runtime_snapshot_write_outcome() == (True, True)

    state = feed_runtime_store.runtime_persistence_state()
    assert state["requested"] == 2
    assert state["enqueued"] == 1
    assert state["coalesced"] == 1
    assert next(iter(feed_runtime_store._RUNTIME_PENDING.values()))[0]["state_value"] == 2


def test_on_ticks_safety_state_transition_bypasses_same_identity_cadence(monkeypatch):
    monkeypatch.setattr(reliability_cfg, "FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC", 60.0, raising=False)
    assert feed_runtime_store.write_runtime_snapshot(
        _feed_snapshot(source="on_ticks", runtime_state="RUNNING", value=1)
    ) is True
    assert feed_runtime_store.write_runtime_snapshot(
        _feed_snapshot(source="on_ticks", runtime_state="RECOVERY_BLOCKED", value=2)
    ) is True

    state = feed_runtime_store.runtime_persistence_state()
    assert state["requested"] == 2
    assert state["enqueued"] == 2
    assert state["coalesced"] == 0
    assert {entry[0]["runtime_state"] for entry in feed_runtime_store._RUNTIME_PENDING.values()} == {
        "RUNNING",
        "RECOVERY_BLOCKED",
    }


def test_feed_runtime_queue_handles_855_distinct_identities_without_rejection(monkeypatch):
    feed_runtime_store.reset_runtime_persistence_for_tests()
    monkeypatch.setattr(feed_runtime_store, "_RUNTIME_QUEUE_MAXSIZE", 855)
    feed_runtime_store.reset_runtime_persistence_for_tests()
    monkeypatch.setattr(feed_runtime_store, "_ensure_runtime_worker", lambda: None)

    for identity in range(855):
        assert feed_runtime_store.write_runtime_snapshot(
            _feed_snapshot(session=f"stress-{identity}", value=1, source="stress")
        ) is True
    for identity in range(855):
        assert feed_runtime_store.write_runtime_snapshot(
            _feed_snapshot(session=f"stress-{identity}", value=2, source="stress")
        ) is True

    state = feed_runtime_store.runtime_persistence_state()
    assert state["requested"] == 1710
    assert state["enqueued"] == 855
    assert state["coalesced"] == 855
    assert state["rejected"] == 0
    assert state["queue_high_watermark"] == 855
    assert state["accounting_invariant_ok"] is True


def test_855_runtime_identities_coalesce_and_drain_to_sqlite_without_rejection(tmp_path, monkeypatch):
    import sqlite3
    import threading

    feed_runtime_store.reset_runtime_persistence_for_tests()
    monkeypatch.setattr(feed_runtime_store, "_RUNTIME_QUEUE_MAXSIZE", 855)
    feed_runtime_store.reset_runtime_persistence_for_tests()
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "runtime-stress.sqlite"), raising=False)
    monkeypatch.setattr(feed_runtime_store, "_ensure_current_feed_truth_payload", lambda payload: None)
    monkeypatch.setattr(feed_runtime_store, "_write_canonical_runtime_artifacts", lambda payload, ts_epoch: None)
    monkeypatch.setattr(feed_runtime_store, "record_feed_startup_event", lambda *args, **kwargs: None)

    for identity in range(855):
        base = _feed_snapshot(
            session=f"sqlite-stress-{identity}",
            epoch=identity + 1,
            source="stress",
        )
        assert feed_runtime_store.write_runtime_snapshot({**base, "state_value": 1}) is True
    for identity in range(855):
        base = _feed_snapshot(
            session=f"sqlite-stress-{identity}",
            epoch=identity + 1,
            source="stress",
        )
        assert feed_runtime_store.write_runtime_snapshot({**base, "state_value": 2}) is True

    worker = threading.Thread(target=feed_runtime_store._runtime_write_loop, daemon=True)
    feed_runtime_store._RUNTIME_WORKER = worker
    worker.start()
    try:
        feed_runtime_store._RUNTIME_WRITE_QUEUE.join()
    finally:
        feed_runtime_store._RUNTIME_STOP.set()
        worker.join(timeout=5.0)

    state = feed_runtime_store.runtime_persistence_state()
    with sqlite3.connect(str(tmp_path / "runtime-stress.sqlite")) as conn:
        persisted_rows = conn.execute("SELECT COUNT(*) FROM feed_runtime").fetchone()[0]

    assert persisted_rows == 855
    assert state["requested"] == 1710
    assert state["enqueued"] == 855
    assert state["coalesced"] == 855
    assert state["persisted"] == 855
    assert state["rejected"] == 0
    assert state["failures"] == 0
    assert state["queue_depth"] == 0
    assert state["in_flight"] == 0
    assert state["accounting_invariant_ok"] is True


def test_runtime_persistence_reports_oldest_pending_age_separately_from_service_wait(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(feed_runtime_store, "time", SimpleNamespace(monotonic=lambda: 110.0))
    feed_runtime_store._RUNTIME_ENQUEUED = 1
    feed_runtime_store._RUNTIME_PERSISTED = 0
    feed_runtime_store._RUNTIME_WRITER_LAG_MS = 25.0
    feed_runtime_store._RUNTIME_LAST_SERVICE_WAIT_MS = 25.0
    feed_runtime_store._RUNTIME_MAX_SERVICE_WAIT_MS = 40.0
    feed_runtime_store._RUNTIME_PENDING = {("pending",): ({}, 109.0, 100.0)}

    state = feed_runtime_store.runtime_persistence_state()

    assert state["writer_lag_ms"] == 25.0
    assert state["writer_lag_semantics"] == "last_service_wait_ms; compatibility alias"
    assert state["last_service_wait_ms"] == 25.0
    assert state["max_service_wait_ms"] == 40.0
    assert state["oldest_pending_age_ms"] == 10000.0
    assert state["pending"] == 1
    assert state["unaccounted_remainder"] == 0
    assert state["accounting_invariant_ok"] is True


def test_runtime_shutdown_result_includes_pending_and_accounting_fields():
    result = feed_runtime_store.shutdown_runtime_persistence(deadline_seconds=1.0)

    assert result["complete"] is True
    assert result["pending"] == 0
    assert result["in_flight"] == 0
    assert result["accounting_invariant_ok"] is True
    assert "oldest_pending_age_ms" in result
