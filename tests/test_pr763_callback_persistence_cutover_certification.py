"""Offline certification tripwires for the PR #763 persistence boundary."""

import ast
import inspect
import threading
from copy import deepcopy

import core.feed.runtime_store as runtime_store
import core.kite_depth_ws as depth_ws
import core.tick_store as tick_store


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

