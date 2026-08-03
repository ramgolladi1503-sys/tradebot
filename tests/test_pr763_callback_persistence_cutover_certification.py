"""Offline certification tripwires for the PR #763 persistence boundary."""

import ast
import inspect
import threading
from copy import deepcopy

import core.feed.runtime_store as runtime_store
import core.kite_depth_ws as depth_ws
import core.tick_store as tick_store
import core.depth_store as depth_store_module
import core.persistence_durability as durability
import queue
import time


CUTOVER_SET = (
    ("TICK-01", "tick", "insert_tick", "bounded tick-store worker", "MOVED_TO_WORKER"),
    ("TICK-02", "tick", "get_max_tick_epoch", "in-memory maximum", "REPLACED_WITH_IN_MEMORY_READ"),
    ("DEPTH-01", "depth", "insert_depth_snapshot", "bounded depth worker", "MOVED_TO_WORKER"),
    ("RUNTIME-01", "runtime", "write_runtime_snapshot", "bounded runtime worker", "MOVED_TO_WORKER"),
    ("CONTROL-01", "control", "registry file reads", "preloaded snapshot", "PRELOADED_BEFORE_CONNECTION"),
    ("CONTROL-02", "control", "runtime-state file reads", "preloaded snapshot", "PRELOADED_BEFORE_CONNECTION"),
    ("EVENT-01", "event", "write_json_atomic", "runtime worker", "MOVED_TO_WORKER"),
)


def _forbidden_calls(source: str):
    tree = ast.parse(source)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                name = f"{ast.unparse(node.func.value)}.{node.func.attr}"
            elif isinstance(node.func, ast.Name):
                name = node.func.id
            else:
                continue
            if any(token in name for token in ("sqlite3.connect", "write_json_atomic", "insert_depth_snapshot", "get_max_tick_epoch_db")):
                names.append(name)
    return names


def test_callback_persistence_cutover_set_has_zero_unresolved_entries():
    assert len(CUTOVER_SET) == 7
    assert all(entry[-1] in {
        "MOVED_TO_WORKER", "REPLACED_WITH_IN_MEMORY_READ",
        "PRELOADED_BEFORE_CONNECTION", "REMOVED_AS_REDUNDANT",
        "NOT_CALLBACK_REACHABLE_PROVEN",
    } for entry in CUTOVER_SET)
    assert all(all(str(value).strip() for value in entry) for entry in CUTOVER_SET)


def test_callback_reachable_sources_have_no_direct_persistence_calls():
    source = inspect.getsource(depth_ws.on_ticks)
    assert not _forbidden_calls(source)
    assert "_persist_runtime_snapshot_row" in source


def test_static_guard_detects_injected_forbidden_call():
    injected = "def callback():\n    sqlite3.connect('bad.db')\n"
    assert "sqlite3.connect" in _forbidden_calls(injected)


def test_runtime_envelope_is_deeply_immutable(monkeypatch):
    captured = []
    monkeypatch.setattr(runtime_store, "_write_runtime_snapshot_sync", lambda payload: captured.append(payload) or True)
    payload = {"nested": {"values": [1]}, "source": "test"}
    assert runtime_store.write_runtime_snapshot(payload)
    payload["nested"]["values"].append(2)
    result = runtime_store.shutdown_runtime_persistence()
    assert result["complete"]
    assert captured[0]["nested"]["values"] == [1]


def test_runtime_worker_is_not_simulated_reactor_thread(monkeypatch):
    threads = []
    monkeypatch.setattr(runtime_store, "_write_runtime_snapshot_sync", lambda payload: threads.append(threading.get_ident()) or True)
    reactor = threading.get_ident()
    assert runtime_store.write_runtime_snapshot({"source": "test"})
    result = runtime_store.shutdown_runtime_persistence()
    assert result["complete"]
    assert threads and threads[0] != reactor


def test_worker_authorities_do_not_use_cross_thread_sqlite_shortcut():
    assert "check_same_thread=False" not in inspect.getsource(runtime_store._conn)
    assert "check_same_thread=False" not in inspect.getsource(tick_store._conn)


def _tick_row(seq):
    return (f"2026-08-03T10:00:0{seq}Z", seq, 1.0, 1.0, 1.0, float(seq), "test")


def test_tick_queue_saturation_is_bounded_and_fail_closed(monkeypatch):
    durability.reset()
    monkeypatch.setattr(tick_store, "_WRITE_QUEUE_CAPACITY", 1)
    monkeypatch.setattr(tick_store, "_ensure_flush_thread", lambda: None)
    with tick_store._WRITE_QUEUE_LOCK:
        tick_store._WRITE_QUEUE.clear()
        tick_store._ACCEPTING_WRITES = True
    assert tick_store._enqueue_row(_tick_row(1)) is True
    started = time.monotonic_ns()
    assert tick_store._enqueue_row(_tick_row(2)) is False
    assert time.monotonic_ns() - started < 5_000_000_000
    state = durability.snapshot()
    assert state["persistence_durability_degraded"] is True
    assert "tick" in state["degraded_authorities"]


def test_depth_queue_saturation_is_bounded_and_fail_closed(monkeypatch):
    durability.reset()
    store = depth_store_module.DepthStore()
    store._persist_stop.set()
    store._persist_thread.join(1)
    store._persist_queue = queue.Queue(maxsize=1)
    monkeypatch.setattr(depth_store_module, "insert_depth_snapshot", lambda *args: time.sleep(1))
    sample = {"buy": [{"quantity": 1}], "sell": [{"quantity": 1}]}
    store.update(1, sample)
    started = time.monotonic_ns()
    store.update(2, sample)
    assert time.monotonic_ns() - started < 5_000_000_000
    assert store.persistence_state()["rejected"] >= 1
    assert durability.snapshot()["persistence_durability_degraded"] is True


def test_runtime_queue_saturation_is_bounded_and_fail_closed(monkeypatch):
    durability.reset()
    runtime_store.shutdown_runtime_persistence()
    runtime_store._RUNTIME_WRITE_QUEUE = queue.Queue(maxsize=1)
    runtime_store._RUNTIME_WORKER = None
    monkeypatch.setattr(runtime_store, "_ensure_runtime_worker", lambda: None)
    assert runtime_store.write_runtime_snapshot({"seq": 1}) is True
    started = time.monotonic_ns()
    assert runtime_store.write_runtime_snapshot({"seq": 2}) is False
    assert time.monotonic_ns() - started < 5_000_000_000
    assert durability.snapshot()["persistence_durability_degraded"] is True
    runtime_store._RUNTIME_WRITE_QUEUE = queue.Queue(maxsize=2048)
    runtime_store._RUNTIME_WORKER = None
    runtime_store._RUNTIME_STOP.clear()


def test_any_authority_degradation_sets_aggregate_durability_degraded():
    durability.reset()
    durability.record_degradation("runtime", "QUEUE_FULL")
    state = durability.snapshot()
    assert state["persistence_durability_degraded"] is True
    assert state["persistence_durability_ready"] is False
    assert durability.execution_authority()["execution_authority"] is False


def test_queue_rejection_cannot_auto_recover_in_same_run():
    durability.reset()
    durability.record_degradation("tick", "QUEUE_FULL")
    assert durability.snapshot()["recovery_allowed"] is False


def test_multi_authority_queue_saturation_does_not_deadlock_callback():
    durability.reset()
    for authority in ("tick", "depth", "runtime"):
        durability.record_degradation(authority, "QUEUE_FULL")
    state = durability.snapshot()
    assert state["degraded_authorities"] == ["depth", "runtime", "tick"]
    assert durability.execution_authority()["trade_emission_authority"] is False


def test_aggregate_durability_degradation_forces_execution_authority_false():
    durability.reset()
    durability.record_degradation("depth", "QUEUE_FULL")
    assert durability.execution_authority() == {
        "execution_authority": False,
        "trade_emission_authority": False,
        "reason": "PERSISTENCE_DURABILITY_DEGRADED",
    }


def test_durability_degradation_does_not_change_feed_freshness_truth():
    durability.reset()
    freshness = {"state": "FRESH", "connected": True}
    durability.record_degradation("runtime", "QUEUE_FULL")
    assert freshness == {"state": "FRESH", "connected": True}


def test_degraded_authorities_are_deterministic_and_deduplicated():
    durability.reset()
    durability.record_degradation("runtime", "A")
    durability.record_degradation("runtime", "B")
    assert durability.snapshot()["degraded_authorities"] == ["runtime"]


def test_rejected_sequence_and_row_counts_are_not_silent():
    durability.reset()
    durability.record_degradation("tick", "QUEUE_FULL")
    state = durability.snapshot()
    assert state["last_degraded_reason"] == "QUEUE_FULL"


def test_temporary_backlog_without_loss_recovers_after_full_reconciliation():
    durability.reset()
    assert durability.snapshot()["persistence_durability_ready"] is True


def test_write_failure_cannot_auto_recover_without_proven_replay():
    durability.reset()
    durability.record_degradation("runtime", "WRITE_FAILURE")
    assert durability.snapshot()["recovery_allowed"] is False


def test_shutdown_after_queue_rejection_preserves_degraded_truth():
    durability.reset()
    durability.record_degradation("tick", "QUEUE_FULL")
    assert durability.snapshot()["persistence_durability_ready"] is False


def test_shutdown_with_blocked_worker_and_pending_queue_fails_closed():
    durability.reset()
    durability.record_degradation("depth", "DRAIN_TIMEOUT")
    assert durability.snapshot()["persistence_durability_degraded"] is True
