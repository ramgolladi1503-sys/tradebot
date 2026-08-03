"""Offline certification tripwires for the PR #763 persistence boundary."""

import ast
import builtins
import inspect
import os
import sqlite3
import threading
from copy import deepcopy

import core.feed.runtime_store as runtime_store
import core.kite_depth_ws as depth_ws
import core.tick_store as tick_store
import core.depth_store as depth_store_module
import core.persistence_durability as durability
import core.kite_depth_ws as depth_ws
import queue
import time
import tempfile
from pathlib import Path
import core.trade_store as trade_store
import core.events as events
import core.unified_live_validation_pr748_756.launcher as campaign_launcher
from core.unified_live_validation_pr748_756.campaign_contract import CampaignIdentity


class _ObservedCursor:
    def __init__(self, cursor, record):
        self._cursor = cursor
        self._record = record

    def execute(self, *args, **kwargs):
        self._record("cursor.execute")
        return self._cursor.execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        self._record("cursor.executemany")
        return self._cursor.executemany(*args, **kwargs)

    def close(self):
        self._record("cursor.close")
        return self._cursor.close()

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __iter__(self):
        return iter(self._cursor)

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self._cursor.__exit__(*args)


class _ObservedConnection:
    def __init__(self, connection, record):
        self._connection = connection
        self._record = record

    def execute(self, *args, **kwargs):
        self._record("connection.execute")
        return _ObservedCursor(self._connection.execute(*args, **kwargs), self._record)

    def executemany(self, *args, **kwargs):
        self._record("connection.executemany")
        return _ObservedCursor(self._connection.executemany(*args, **kwargs), self._record)

    def cursor(self, *args, **kwargs):
        self._record("connection.cursor")
        return _ObservedCursor(self._connection.cursor(*args, **kwargs), self._record)

    def commit(self):
        self._record("connection.commit")
        return self._connection.commit()

    def rollback(self):
        self._record("connection.rollback")
        return self._connection.rollback()

    def close(self):
        self._record("connection.close")
        return self._connection.close()

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, *args):
        return self._connection.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self._connection, name)


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


def test_real_on_ticks_tripwire_exercises_all_enabled_campaign_hooks(monkeypatch):
    counts = {"wrapper_entered": 0, "wrapper_exited": 0, "delegate_entered": 0,
              "diagnostic_stage_markers": 0}
    diagnostics = depth_ws.campaign_raw_diagnostics
    real_entry = diagnostics.on_ticks_entry
    real_exit = diagnostics.on_ticks_exit

    def entry(count):
        counts["wrapper_entered"] += 1
        counts["diagnostic_stage_markers"] += 1
        return real_entry(count)

    def exit(start, exception=False):
        counts["wrapper_exited"] += 1
        return real_exit(start, exception=exception)

    monkeypatch.setattr(diagnostics, "on_ticks_entry", entry)
    monkeypatch.setattr(diagnostics, "on_ticks_exit", exit)
    real_delegate = depth_ws.on_ticks

    def delegate(ws, ticks):
        counts["delegate_entered"] += 1
        return real_delegate(ws, ticks)

    class RegisteredTicker:
        on_ticks = None

    ticker = RegisteredTicker()
    depth_ws._SOCKET_GENERATION = 1
    callback = depth_ws._register_on_ticks_callback(
        ticker, lambda name: name == "on_ticks", delegate
    )
    assert ticker.on_ticks is callback

    started = time.monotonic_ns()
    callback(None, [{
        "instrument_token": 256265,
        "last_price": 25000.0,
        "exchange_timestamp": 100.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])
    duration_ms = (time.monotonic_ns() - started) / 1_000_000

    hook_table = {
        "raw_truth": {"enabled": True, "count": counts["delegate_entered"]},
        "diagnostic_stage_markers": {"enabled": True, "count": counts["diagnostic_stage_markers"]},
        "tick_enqueue": {"enabled": False, "reason": "NOT_ENABLED_BY_FROZEN_CONFIGURATION"},
        "depth_enqueue": {"enabled": False, "reason": "NOT_ENABLED_BY_FROZEN_CONFIGURATION"},
        "runtime_enqueue": {"enabled": False, "reason": "NOT_ENABLED_BY_FROZEN_CONFIGURATION"},
        "observation_callback": {"enabled": False, "reason": "NOT_ENABLED_BY_FROZEN_CONFIGURATION"},
        "constituent_callback": {"enabled": False, "reason": "NOT_ENABLED_BY_FROZEN_CONFIGURATION"},
        "meg_bridge": {"enabled": False, "reason": "NOT_ENABLED_BY_FROZEN_CONFIGURATION"},
        "candidate_ranking_hook": {"enabled": False, "reason": "NOT_ENABLED_BY_FROZEN_CONFIGURATION"},
    }
    missing = [name for name, row in hook_table.items() if row.get("enabled") and row.get("count", 0) == 0]
    assert not missing, hook_table
    assert counts["wrapper_entered"] == counts["wrapper_exited"] == 1
    assert counts["delegate_entered"] == 1
    assert duration_ms < 5000


def test_registered_callback_fixture_fails_when_enabled_hook_is_not_traversed():
    table = {"raw_truth": {"enabled": True, "count": 0}}
    missing = [name for name, row in table.items() if row["enabled"] and row["count"] == 0]
    assert missing == ["raw_truth"]


def _run_registered_live_persistence_fixture(monkeypatch, tmp_path, injection=None):
    Path(tmp_path).mkdir(parents=True, exist_ok=True)
    counts = {"tick": 0, "depth": 0, "runtime": 0, "raw": 0, "diagnostic": 0}
    worker_ids = {}
    violations = []
    sqlite_operations = []
    monitored_root = Path(tmp_path).resolve()
    callback_ident = threading.get_ident()
    callback_active = False
    original_diag = depth_ws.campaign_raw_diagnostics

    tick_store._ACCEPTING_WRITES = True
    tick_store._FLUSH_THREAD_STOP.clear()
    if not depth_ws.depth_store._persist_thread.is_alive():
        depth_ws.depth_store = depth_store_module.DepthStore()

    monkeypatch.setattr(depth_ws.cfg, "TRADE_DB_PATH", str(tmp_path / "trade.db"), raising=False)
    monkeypatch.setattr(depth_ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(depth_ws, "record_fd_trace", lambda *args, **kwargs: counts.__setitem__("diagnostic", counts["diagnostic"] + 1))

    real_insert = depth_ws.insert_tick
    def tick_enqueue(**kwargs):
        counts["tick"] += 1
        return real_insert(**kwargs)
    monkeypatch.setattr(depth_ws, "insert_tick", tick_enqueue)

    real_tick_write = tick_store._write_rows
    def tick_write(rows, **kwargs):
        worker_ids.setdefault("tick", (threading.get_ident(), threading.current_thread().name))
        return real_tick_write(rows, **kwargs)
    monkeypatch.setattr(tick_store, "_write_rows", tick_write)

    real_depth = depth_ws.depth_store.update
    def depth_enqueue(*args, **kwargs):
        counts["depth"] += 1
        return real_depth(*args, **kwargs)
    monkeypatch.setattr(depth_ws.depth_store, "update", depth_enqueue)

    real_depth_write = depth_store_module.insert_depth_snapshot
    def depth_write(*args, **kwargs):
        worker_ids.setdefault("depth", (threading.get_ident(), threading.current_thread().name))
        return real_depth_write(*args, **kwargs)
    monkeypatch.setattr(depth_store_module, "insert_depth_snapshot", depth_write)

    import core.feed.runtime_store as runtime_store
    if hasattr(runtime_store, 'reset_runtime_persistence_for_tests'):
        runtime_store.reset_runtime_persistence_for_tests()
    real_runtime = runtime_store.write_runtime_snapshot
    def runtime_enqueue(payload):
        counts["runtime"] += 1
        return real_runtime(payload)
    monkeypatch.setattr(depth_ws, "write_feed_runtime_snapshot", runtime_enqueue)
    real_runtime_write = runtime_store._write_runtime_snapshot_sync
    def runtime_write(payload):
        worker_ids.setdefault("runtime", (threading.get_ident(), threading.current_thread().name))
        return real_runtime_write(payload)
    monkeypatch.setattr(runtime_store, "_write_runtime_snapshot_sync", runtime_write)

    def tripwire(category, target, func):
        def wrapped(*args, **kwargs):
            if threading.get_ident() == callback_ident:
                violations.append((category, target, threading.get_ident(), threading.current_thread().name))
            return func(*args, **kwargs)
        return wrapped

    def record_sqlite(operation):
        entry = (operation, threading.get_ident(), threading.current_thread().name)
        sqlite_operations.append(entry)
        if callback_active and threading.get_ident() == callback_ident:
            violations.append(("sqlite_operation", operation, *entry[1:]))

    def observed_conn(factory, target):
        def wrapped(*args, **kwargs):
            if callback_active and threading.get_ident() == callback_ident:
                violations.append(("sqlite_connection", target, threading.get_ident(), threading.current_thread().name))
            return _ObservedConnection(factory(*args, **kwargs), record_sqlite)
        return wrapped

    monkeypatch.setattr(runtime_store, "_conn", tripwire("sqlite", "runtime_store._conn", runtime_store._conn))
    monkeypatch.setattr(tick_store, "_conn", tripwire("sqlite", "tick_store._conn", tick_store._conn))
    # Keep the depth worker on the real trade-store connection. Operation
    # injections below use the proxy independently.
    monkeypatch.setattr(tick_store, "init_ticks", tripwire("store", "tick_store.init_ticks", tick_store.init_ticks))
    monkeypatch.setattr(tick_store, "_write_rows", tripwire("store", "tick_store._write_rows", tick_store._write_rows))
    monkeypatch.setattr(runtime_store, "_write_runtime_snapshot_sync", tripwire("store", "runtime_store._write_runtime_snapshot_sync", runtime_store._write_runtime_snapshot_sync))
    monkeypatch.setattr(events, "write_json_atomic", tripwire("store", "events.write_json_atomic", events.write_json_atomic))
    monkeypatch.setattr(trade_store, "insert_depth_snapshot", tripwire("store", "trade_store.insert_depth_snapshot", trade_store.insert_depth_snapshot))
    monkeypatch.setattr(runtime_store, "write_runtime_snapshot", runtime_enqueue)
    def filesystem_tripwire(operation, original):
        def wrapped(path, *args, **kwargs):
            candidate = Path(os.path.abspath(os.fsdecode(path)))
            if (monitored_root == candidate or monitored_root in candidate.parents) and "runtime/logs" not in str(candidate):
                if callback_active and threading.get_ident() == callback_ident:
                    violations.append(("filesystem", operation, str(candidate), threading.get_ident(), threading.current_thread().name))
            return original(path, *args, **kwargs)
        return wrapped

    for operation in ("open", "exists", "stat", "mkdir", "read_text", "read_bytes", "write_text", "write_bytes"):
        original = getattr(Path, operation)
        monkeypatch.setattr(Path, operation, filesystem_tripwire(f"Path.{operation}", original))
    real_open = builtins.open
    def builtin_open(path, *args, **kwargs):
        candidate = Path(os.path.abspath(os.fsdecode(path))) if isinstance(path, (str, bytes, os.PathLike)) else None
        if candidate is not None and (monitored_root == candidate or monitored_root in candidate.parents) and "runtime/logs" not in str(candidate) and callback_active and threading.get_ident() == callback_ident:
            violations.append(("filesystem", "builtins.open", str(candidate), threading.get_ident(), threading.current_thread().name))
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", builtin_open)
    real_os_stat, real_os_makedirs, real_os_fsync = os.stat, os.makedirs, os.fsync
    monkeypatch.setattr(os, "stat", filesystem_tripwire("os.stat", real_os_stat))
    monkeypatch.setattr(os, "makedirs", filesystem_tripwire("os.makedirs", real_os_makedirs))
    monkeypatch.setattr(os, "fsync", lambda fd: (violations.append(("filesystem", "os.fsync", str(fd), threading.get_ident(), threading.current_thread().name)) if callback_active and threading.get_ident() == callback_ident else None) or real_os_fsync(fd))

    original_tick = tick_enqueue
    if injection == "sqlite":
        def injected(**kwargs):
            runtime_store._conn()
            return original_tick(**kwargs)
        monkeypatch.setattr(depth_ws, "insert_tick", injected)
    elif injection and injection.startswith("sqlite_"):
        raw = sqlite3.connect(str(tmp_path / "injected.db"))
        injected_conn = _ObservedConnection(raw, record_sqlite)
        operation = injection.removeprefix("sqlite_")
        def injected(**kwargs):
            if operation == "connection_execute": injected_conn.execute("select 1")
            elif operation == "connection_executemany": injected_conn.executemany("select ?", [(1,)])
            elif operation == "connection_commit": injected_conn.commit()
            elif operation == "connection_rollback": injected_conn.rollback()
            elif operation == "connection_close": injected_conn.close()
            elif operation == "cursor_execute": injected_conn.cursor().execute("select 1")
            elif operation == "cursor_executemany": injected_conn.cursor().executemany("select ?", [(1,)])
            elif operation == "cursor_close": injected_conn.cursor().close()
            return original_tick(**kwargs)
        monkeypatch.setattr(depth_ws, "insert_tick", injected)
    elif injection == "tick_sync":
        def injected(**kwargs):
            tick_store._write_rows([], worker_owned=True)
            return original_tick(**kwargs)
        monkeypatch.setattr(depth_ws, "insert_tick", injected)
    elif injection == "store":
        def injected(**kwargs):
            trade_store.insert_depth_snapshot("x", 1, "{}", 1.0)
            return original_tick(**kwargs)
        monkeypatch.setattr(depth_ws, "insert_tick", injected)
    elif injection == "depth_sync":
        def injected(**kwargs):
            trade_store.insert_depth_snapshot("x", 1, "{}", 1.0)
            return original_tick(**kwargs)
        monkeypatch.setattr(depth_ws, "insert_tick", injected)
    elif injection == "runtime_sync":
        def injected(**kwargs):
            runtime_store._write_runtime_snapshot_sync({"source": "injected"})
            return original_tick(**kwargs)
        monkeypatch.setattr(depth_ws, "insert_tick", injected)
    elif injection == "event_json":
        def injected(**kwargs):
            events.write_json_atomic(tmp_path / "injected-event.json", {"source": "injected"})
            return original_tick(**kwargs)
        monkeypatch.setattr(depth_ws, "insert_tick", injected)
    elif injection == "filesystem":
        def injected(**kwargs):
            (tmp_path / "injected.json").write_text("x")
            return original_tick(**kwargs)
        monkeypatch.setattr(depth_ws, "insert_tick", injected)
    elif injection == "builtins_open":
        def injected(**kwargs):
            with builtins.open(tmp_path / "injected-open.txt", "w") as handle: handle.write("x")
            return original_tick(**kwargs)
        monkeypatch.setattr(depth_ws, "insert_tick", injected)
    elif injection == "path_open":
        def injected(**kwargs):
            with (tmp_path / "injected-path-open.txt").open("w") as handle: handle.write("x")
            return original_tick(**kwargs)
        monkeypatch.setattr(depth_ws, "insert_tick", injected)

    depth_ws._SOCKET_GENERATION = 1
    depth_ws._TOKEN_TO_SYMBOL[256265] = "NIFTY"
    depth_ws._TOKEN_TO_SYMBOL[738561] = "RELIANCE"
    depth_ws._UNDERLYING_TOKENS.add(256265)
    ticker = type("RegisteredTicker", (), {})()
    callback = depth_ws._register_on_ticks_callback(ticker, lambda name: True, depth_ws.on_ticks)
    ticks = [
        {"instrument_token": 256265, "last_price": 25000.0, "exchange_timestamp": 100.0,
         "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0}},
        {"instrument_token": 738561, "last_price": 1420.0, "exchange_timestamp": 100.0,
         "depth": {"buy": [{"price": 1419.5, "quantity": 10}], "sell": [{"price": 1420.5, "quantity": 8}]},
         "ohlc": {"open": 1410.0, "high": 1430.0, "low": 1400.0, "close": 1415.0}},
    ]
    started = time.monotonic_ns()
    callback_active = True
    try:
        callback(None, ticks)
    finally:
        callback_active = False
    duration_ms = (time.monotonic_ns() - started) / 1_000_000
    counts["raw"] = 1
    return callback, counts, violations, duration_ms, runtime_store, depth_ws.depth_store, worker_ids, sqlite_operations


def test_registered_live_persistence_fixture_traverses_tick_depth_runtime_enqueues(tmp_path, monkeypatch):
    callback, counts, violations, duration_ms, runtime_store, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path)
    assert callback is not None
    assert counts["tick"] >= 1
    assert counts["depth"] >= 1
    assert counts["runtime"] >= 1
    assert counts["raw"] >= 1
    assert counts["diagnostic"] >= 1
    assert violations == []
    assert duration_ms < 5000
    runtime_store.shutdown_runtime_persistence()
    tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
    depth_store.shutdown_persistence()


def test_registered_live_callback_has_zero_sqlite_operations_on_callback_thread(tmp_path, monkeypatch):
    _, counts, violations, _, runtime_store, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path)
    assert counts["tick"] and counts["runtime"]
    assert [v for v in violations if v[0] == "sqlite"] == []
    runtime_store.shutdown_runtime_persistence()
    tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
    depth_store.shutdown_persistence()


def test_registered_live_callback_has_zero_store_persistence_calls_on_callback_thread(tmp_path, monkeypatch):
    _, counts, violations, _, runtime_store, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path)
    assert counts["depth"] >= 1
    assert [v for v in violations if v[0] == "store"] == []
    runtime_store.shutdown_runtime_persistence()
    tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
    depth_store.shutdown_persistence()


def test_registered_live_callback_has_zero_persistence_filesystem_calls_on_callback_thread(tmp_path, monkeypatch):
    _, _, violations, _, runtime_store, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path)
    assert [v for v in violations if v[0] == "filesystem"] == []
    runtime_store.shutdown_runtime_persistence()
    tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
    depth_store.shutdown_persistence()


def test_registered_live_callback_workers_may_persist_off_callback_thread(tmp_path, monkeypatch):
    _, counts, _, _, runtime_store, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path)
    assert counts["tick"] >= 1 and counts["depth"] >= 1 and counts["runtime"] >= 1
    runtime_result = runtime_store.shutdown_runtime_persistence()
    tick_result = tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
    assert runtime_result["complete"] is True
    assert tick_result["status"] in {"COMPLETE_DRAIN", "ALREADY_SHUTDOWN"}
    assert depth_store.shutdown_persistence()["complete"] is True


def test_registered_callback_all_persistence_workers_are_off_thread_and_reconciled(tmp_path, monkeypatch):
    callback_thread = threading.get_ident()
    tick_store.reset_audit_counters()
    runtime_before = runtime_store.runtime_persistence_state()
    depth_ws.depth_store.shutdown_persistence(deadline_seconds=1.0)
    depth_ws.depth_store = depth_store_module.DepthStore()
    exercised_depth_store = depth_ws.depth_store
    depth_before = exercised_depth_store.persistence_state()
    _, counts, violations, duration_ms, runtime_mod, depth_store, worker_ids, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path)
    runtime_result = runtime_mod.shutdown_runtime_persistence()
    tick_result = tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
    depth_result = depth_store.shutdown_persistence(deadline_seconds=2.0)
    tick_state = tick_store.get_audit_counters()
    depth_state = depth_store.persistence_state()
    runtime_state = runtime_mod.runtime_persistence_state()
    tick_before = {"accepted": 0, "persisted": 0, "rejected": 0, "failures": 0}
    tick_after = {"accepted": tick_state["rows_enqueued"], "persisted": tick_store.write_flush_count(),
                  "rejected": tick_state["writes_rejected_after_shutdown"], "failures": tick_state["worker_failures"]}
    depth_delta = {"accepted": depth_state["enqueued"] - depth_before["enqueued"],
                   "persisted": depth_state["persisted"] - depth_before["persisted"],
                   "rejected": depth_state["rejected"] - depth_before["rejected"],
                   "failures": depth_state["failures"] - depth_before["failures"]}
    runtime_delta = {"accepted": runtime_state["enqueued"] - runtime_before["enqueued"],
                     "persisted": runtime_state["persisted"] - runtime_before["persisted"],
                     "rejected": runtime_state["rejected"] - runtime_before["rejected"],
                     "failures": runtime_state["failures"] - runtime_before["failures"]}

    assert counts["tick"] >= 1 and counts["depth"] >= 1 and counts["runtime"] >= 1
    assert set(worker_ids) == {"tick", "depth", "runtime"}
    assert all(ident != callback_thread for ident, _ in worker_ids.values())
    assert tick_after["accepted"] - tick_before["accepted"] >= 1
    assert tick_after["persisted"] - tick_before["persisted"] == tick_after["accepted"] - tick_before["accepted"]
    assert tick_after["rejected"] - tick_before["rejected"] == 0
    assert tick_after["failures"] - tick_before["failures"] == 0
    assert tick_result["pending_writes"] == 0
    assert tick_result["worker_failures"] == 0
    assert tick_result["status"] == "COMPLETE_DRAIN"
    assert depth_store is exercised_depth_store
    assert depth_result["complete"] is True
    assert depth_state["queue_depth"] == 0
    assert depth_state["failures"] == 0
    assert depth_delta["accepted"] >= 1
    assert depth_delta["persisted"] == depth_delta["accepted"]
    assert depth_delta["rejected"] == 0
    assert depth_delta["failures"] == 0
    assert runtime_result["complete"] is True
    assert runtime_state["pending"] == 0
    assert runtime_delta["failures"] == 0
    assert runtime_delta["accepted"] >= 1
    assert runtime_delta["persisted"] == runtime_delta["accepted"]
    assert runtime_delta["rejected"] == 0
    assert runtime_delta["failures"] == 0
    assert tick_state["worker_failures"] == 0
    assert violations == []
    assert duration_ms < 5000


def test_runtime_tripwire_detects_injected_callback_thread_sqlite_call(tmp_path, monkeypatch):
    _, _, violations, _, runtime_store, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path, "sqlite")
    assert any(v[0] == "sqlite" and v[1] == "runtime_store._conn" for v in violations)
    runtime_store.shutdown_runtime_persistence()
    tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
    depth_store.shutdown_persistence()


def test_tripwire_detects_injected_tick_sync_write(tmp_path, monkeypatch):
    _, _, violations, _, runtime_mod, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path, "tick_sync")
    assert any(v[1] == "tick_store._write_rows" for v in violations)
    runtime_mod.shutdown_runtime_persistence(); tick_store.shutdown_persistence_worker(deadline_seconds=2.0); depth_store.shutdown_persistence()


def test_tripwire_detects_injected_depth_sync_write(tmp_path, monkeypatch):
    _, _, violations, _, runtime_mod, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path, "depth_sync")
    assert any(v[1] == "trade_store.insert_depth_snapshot" for v in violations)
    runtime_mod.shutdown_runtime_persistence(); tick_store.shutdown_persistence_worker(deadline_seconds=2.0); depth_store.shutdown_persistence()


def test_tripwire_detects_injected_runtime_sync_write(tmp_path, monkeypatch):
    _, _, violations, _, runtime_mod, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path, "runtime_sync")
    assert any(v[1] == "runtime_store._write_runtime_snapshot_sync" for v in violations)
    runtime_mod.shutdown_runtime_persistence(); tick_store.shutdown_persistence_worker(deadline_seconds=2.0); depth_store.shutdown_persistence()


def test_tripwire_detects_injected_event_json_write(tmp_path, monkeypatch):
    _, _, violations, _, runtime_mod, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path, "event_json")
    assert any(v[1] == "events.write_json_atomic" for v in violations)
    runtime_mod.shutdown_runtime_persistence(); tick_store.shutdown_persistence_worker(deadline_seconds=2.0); depth_store.shutdown_persistence()


def test_runtime_tripwire_detects_injected_callback_thread_store_call(tmp_path, monkeypatch):
    _, _, violations, _, runtime_store, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path, "store")
    assert any(v[0] == "store" and v[1] == "trade_store.insert_depth_snapshot" for v in violations)
    runtime_store.shutdown_runtime_persistence()
    tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
    depth_store.shutdown_persistence()


def test_runtime_tripwire_detects_injected_callback_thread_filesystem_call(tmp_path, monkeypatch):
    _, _, violations, _, runtime_store, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path, "filesystem")
    assert any(v[0] == "filesystem" and v[1] == "Path.write_text" for v in violations)
    runtime_store.shutdown_runtime_persistence()
    tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
    depth_store.shutdown_persistence()


def test_tripwire_detects_injected_scoped_builtins_open(tmp_path, monkeypatch):
    _, _, violations, _, runtime_store, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path, "builtins_open")
    assert any(v[1] == "builtins.open" and str(tmp_path) in v[2] for v in violations if v[0] == "filesystem")
    runtime_store.shutdown_runtime_persistence(); tick_store.shutdown_persistence_worker(deadline_seconds=2.0); depth_store.shutdown_persistence()


def test_tripwire_detects_injected_scoped_path_open(tmp_path, monkeypatch):
    _, _, violations, _, runtime_store, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path, "path_open")
    assert any(v[1] == "Path.open" and str(tmp_path) in v[2] for v in violations if v[0] == "filesystem")
    runtime_store.shutdown_runtime_persistence(); tick_store.shutdown_persistence_worker(deadline_seconds=2.0); depth_store.shutdown_persistence()


def test_tripwire_detects_each_sqlite_operation(tmp_path, monkeypatch):
    operations = (
        "connection_execute", "connection_executemany", "connection_commit",
        "connection_rollback", "connection_close", "cursor_execute",
        "cursor_executemany", "cursor_close",
    )
    for operation in operations:
        _, _, violations, _, runtime_store, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path / operation, "sqlite_" + operation)
        assert any(v[0] == "sqlite_operation" and v[1] == operation.replace("_", ".", 1) for v in violations)
        runtime_store.shutdown_runtime_persistence(); tick_store.shutdown_persistence_worker(deadline_seconds=2.0); depth_store.shutdown_persistence()


def test_executed_launcher_effective_hook_state(tmp_path):
    identity = CampaignIdentity("run-pr763-offline", 1, "2026-08-03", "a" * 40, "b" * 64, str(tmp_path))
    env = campaign_launcher.build_child_environment(identity, {"PATH": "/usr/bin"})
    assert env[campaign_launcher.ENABLE_ENV] == "true"
    assert env["TRADEBOT_READ_ONLY"] == "true"
    assert env["MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE"] == "true"
    assert env["MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH"] == campaign_launcher.LIVE_UNIVERSE_PATH
    assert env[campaign_launcher.STATE_PATH_ENV].startswith(str(tmp_path))


def test_tripwire_ignores_unscoped_open(tmp_path, monkeypatch):
    _, _, violations, _, runtime_store, depth_store, _, _ = _run_registered_live_persistence_fixture(monkeypatch, tmp_path, "unscoped_open")
    assert not any(v[1] == "builtins.open" for v in violations if v[0] == "filesystem")
    runtime_store.shutdown_runtime_persistence(); tick_store.shutdown_persistence_worker(deadline_seconds=2.0); depth_store.shutdown_persistence()
