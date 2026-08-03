"""Idempotent source repair for PR #763 offline certification.

This temporary maintenance script is executed only by the branch-local offline
workflow. It performs exact, guarded replacements and fails if the expected
source no longer matches. Remove it with the temporary workflow after the PR is
ready for live verification.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> bool:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if new in text:
        return False
    if old not in text:
        raise RuntimeError(f"PR763_PATCH_CONTEXT_MISSING:{path}:{old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def replace_all(path: str, old: str, new: str) -> bool:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        if new in text:
            return False
        raise RuntimeError(f"PR763_PATCH_CONTEXT_MISSING:{path}:{old[:80]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")
    return True


def append_once(path: str, marker: str, content: str) -> bool:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if marker in text:
        return False
    target.write_text(text.rstrip() + "\n\n" + content.strip() + "\n", encoding="utf-8")
    return True


def main() -> int:
    changed = False

    # Filesystem tripwires must not resolve paths through the Path.stat method
    # they have just monkeypatched; lexical absolute normalization is sufficient
    # for the temporary-root scope check and cannot recurse.
    changed |= replace_all(
        "tests/test_pr763_callback_persistence_cutover_certification.py",
        "candidate = Path(path).resolve()",
        "candidate = Path(os.path.abspath(os.fsdecode(path)))",
    )
    changed |= replace_once(
        "tests/test_pr763_callback_persistence_cutover_certification.py",
        "candidate = Path(path).resolve() if isinstance(path, (str, bytes, os.PathLike)) else None",
        "candidate = Path(os.path.abspath(os.fsdecode(path))) if isinstance(path, (str, bytes, os.PathLike)) else None",
    )

    # Every invocation of the live-shaped fixture needs a fresh runtime worker
    # lifecycle now that post-shutdown writes fail closed.
    changed |= replace_once(
        "tests/test_pr763_callback_persistence_cutover_certification.py",
        "    import core.feed.runtime_store as runtime_store\n    real_runtime = runtime_store.write_runtime_snapshot\n",
        "    import core.feed.runtime_store as runtime_store\n    if hasattr(runtime_store, 'reset_runtime_persistence_for_tests'):\n        runtime_store.reset_runtime_persistence_for_tests()\n    real_runtime = runtime_store.write_runtime_snapshot\n",
    )

    # Preserve real tick commit accounting while observing FIFO order.
    changed |= replace_once(
        "tests/test_pr763_offline_remaining_gates.py",
        "    tick_rows = []\n\n    def capture_tick_rows(rows, *, worker_owned=False):\n        tick_rows.extend(list(rows))\n        return True\n",
        "    tick_rows = []\n    real_tick_writer = tick_store._write_rows\n\n    def capture_tick_rows(rows, *, worker_owned=False):\n        tick_rows.extend(list(rows))\n        return real_tick_writer(rows, worker_owned=worker_owned)\n",
    )
    changed |= replace_all(
        "tests/test_pr763_offline_remaining_gates.py",
        "pr_number=763",
        "pr_number=750",
    )
    changed |= replace_once(
        "tests/test_pr763_offline_remaining_gates.py",
        "    runtime_store._RUNTIME_PERSISTED = 0\n",
        "    runtime_store._RUNTIME_PERSISTED = 0\n    if hasattr(runtime_store, '_RUNTIME_SHUTDOWN'):\n        runtime_store._RUNTIME_SHUTDOWN = False\n",
    )

    # Runtime persistence has a terminal shutdown boundary just like tick/depth.
    changed |= replace_once(
        "core/feed/runtime_store.py",
        "_RUNTIME_PERSISTED = 0\n",
        "_RUNTIME_PERSISTED = 0\n_RUNTIME_SHUTDOWN = False\n",
    )
    changed |= replace_once(
        "core/feed/runtime_store.py",
        "def write_runtime_snapshot(payload: dict[str, Any]) -> bool:\n    global _RUNTIME_ENQUEUED, _RUNTIME_REJECTED, _RUNTIME_DEGRADED\n    if not isinstance(payload, dict):\n        return False\n    _ensure_runtime_worker()\n",
        "def write_runtime_snapshot(payload: dict[str, Any]) -> bool:\n    global _RUNTIME_ENQUEUED, _RUNTIME_REJECTED, _RUNTIME_DEGRADED, _RUNTIME_SHUTDOWN\n    if not isinstance(payload, dict):\n        return False\n    with _RUNTIME_LOCK:\n        if _RUNTIME_SHUTDOWN:\n            _RUNTIME_REJECTED += 1\n            _RUNTIME_DEGRADED = True\n            record_degradation('runtime', 'RUNTIME_PERSISTENCE_SHUTDOWN')\n            return False\n    _ensure_runtime_worker()\n",
    )
    changed |= replace_once(
        "core/feed/runtime_store.py",
        "def shutdown_runtime_persistence(deadline_seconds: float = 2.0) -> dict:\n    deadline = time.monotonic() + max(0.0, float(deadline_seconds))\n",
        "def shutdown_runtime_persistence(deadline_seconds: float = 2.0) -> dict:\n    global _RUNTIME_SHUTDOWN\n    with _RUNTIME_LOCK:\n        _RUNTIME_SHUTDOWN = True\n    deadline = time.monotonic() + max(0.0, float(deadline_seconds))\n",
    )
    changed |= replace_once(
        "core/feed/runtime_store.py",
        "\ndef runtime_persistence_state() -> dict:\n",
        "\ndef reset_runtime_persistence_for_tests() -> None:\n    \"\"\"Reset the terminal runtime persistence lifecycle between tests only.\"\"\"\n    global _RUNTIME_WRITE_QUEUE, _RUNTIME_WORKER, _RUNTIME_ENQUEUED\n    global _RUNTIME_REJECTED, _RUNTIME_FAILURES, _RUNTIME_DEGRADED\n    global _RUNTIME_PERSISTED, _RUNTIME_SHUTDOWN\n    result = shutdown_runtime_persistence(deadline_seconds=1.0)\n    if result.get('worker_alive'):\n        raise RuntimeError('runtime persistence worker did not stop for test reset')\n    with _RUNTIME_LOCK:\n        _RUNTIME_WRITE_QUEUE = queue.Queue(maxsize=2048)\n        _RUNTIME_STOP.clear()\n        _RUNTIME_WORKER = None\n        _RUNTIME_ENQUEUED = 0\n        _RUNTIME_REJECTED = 0\n        _RUNTIME_FAILURES = 0\n        _RUNTIME_DEGRADED = False\n        _RUNTIME_PERSISTED = 0\n        _RUNTIME_SHUTDOWN = False\n\n\ndef runtime_persistence_state() -> dict:\n",
    )
    changed |= replace_once(
        "core/feed/runtime_store.py",
        '            "worker_ident": _RUNTIME_WORKER.ident if _RUNTIME_WORKER else None,\n',
        '            "worker_ident": _RUNTIME_WORKER.ident if _RUNTIME_WORKER else None,\n            "shutdown": bool(_RUNTIME_SHUTDOWN),\n',
    )

    # The structured collector must start from the explicit test reset rather
    # than calling terminal shutdown immediately before enqueue.
    changed |= replace_once(
        "tools/pr763_gate1_structured_evidence.py",
        "        runtime_mod.shutdown_runtime_persistence(deadline_seconds=1.0)\n        cert.depth_ws.depth_store.shutdown_persistence(deadline_seconds=1.0)\n",
        "        if hasattr(runtime_mod, 'reset_runtime_persistence_for_tests'):\n            runtime_mod.reset_runtime_persistence_for_tests()\n        else:\n            runtime_mod.shutdown_runtime_persistence(deadline_seconds=1.0)\n        cert.depth_ws.depth_store.shutdown_persistence(deadline_seconds=1.0)\n",
    )

    # Gate 4 requires deterministic connection closure on the same owning worker.
    changed |= replace_once(
        "core/tick_store.py",
        "from dataclasses import dataclass, asdict\n",
        "from dataclasses import dataclass, asdict\nfrom contextlib import contextmanager\n",
    )
    changed |= replace_once(
        "core/tick_store.py",
        "def _conn():\n    db_path = ensure_parent_dir(Path(str(cfg.TRADE_DB_PATH)))\n    conn = sqlite3.connect(str(db_path), timeout=30.0)\n    try:\n        conn.execute(\"PRAGMA busy_timeout=30000\")\n        conn.execute(\"PRAGMA journal_mode=WAL\")\n        conn.execute(\"PRAGMA synchronous=NORMAL\")\n    except Exception:\n        pass\n    return conn\n",
        "@contextmanager\ndef _conn():\n    db_path = ensure_parent_dir(Path(str(cfg.TRADE_DB_PATH)))\n    conn = sqlite3.connect(str(db_path), timeout=30.0)\n    try:\n        try:\n            conn.execute(\"PRAGMA busy_timeout=30000\")\n            conn.execute(\"PRAGMA journal_mode=WAL\")\n            conn.execute(\"PRAGMA synchronous=NORMAL\")\n        except Exception:\n            pass\n        with conn:\n            yield conn\n    finally:\n        conn.close()\n",
    )
    changed |= replace_once(
        "core/feed/runtime_store.py",
        "from copy import deepcopy\n",
        "from copy import deepcopy\nfrom contextlib import contextmanager\n",
    )
    changed |= replace_once(
        "core/feed/runtime_store.py",
        "def _conn() -> sqlite3.Connection:\n    conn = sqlite3.connect(str(_db_path()), timeout=30.0)\n    try:\n        conn.execute(\"PRAGMA busy_timeout=30000\")\n        conn.execute(\"PRAGMA journal_mode=WAL\")\n        conn.execute(\"PRAGMA synchronous=NORMAL\")\n    except Exception:\n        pass\n    return conn\n",
        "@contextmanager\ndef _conn():\n    conn = sqlite3.connect(str(_db_path()), timeout=30.0)\n    try:\n        try:\n            conn.execute(\"PRAGMA busy_timeout=30000\")\n            conn.execute(\"PRAGMA journal_mode=WAL\")\n            conn.execute(\"PRAGMA synchronous=NORMAL\")\n        except Exception:\n            pass\n        with conn:\n            yield conn\n    finally:\n        conn.close()\n",
    )

    changed |= append_once(
        "tests/test_pr763_offline_remaining_gates.py",
        "def test_gate4_sqlite_connection_lifecycle_is_worker_owned",
        r'''
def test_gate4_sqlite_connection_lifecycle_is_worker_owned(tmp_path, monkeypatch):
    """Create/execute/commit/close stay on each authority's persistence worker."""

    import sqlite3 as stdlib_sqlite

    callback_thread = threading.get_ident()
    real_connect = stdlib_sqlite.connect

    class ObservedConnection:
        def __init__(self, raw, events, authority):
            self._raw = raw
            self._events = events
            self._authority = authority

        def _record(self, operation):
            self._events.append((self._authority, operation, threading.get_ident(), threading.current_thread().name))

        def execute(self, *args, **kwargs):
            self._record("execute")
            return self._raw.execute(*args, **kwargs)

        def executemany(self, *args, **kwargs):
            self._record("executemany")
            return self._raw.executemany(*args, **kwargs)

        def commit(self):
            self._record("commit")
            return self._raw.commit()

        def rollback(self):
            self._record("rollback")
            return self._raw.rollback()

        def close(self):
            self._record("close")
            return self._raw.close()

        def cursor(self, *args, **kwargs):
            return self._raw.cursor(*args, **kwargs)

        def __enter__(self):
            self._raw.__enter__()
            return self

        def __exit__(self, exc_type, exc, tb):
            self._record("rollback" if exc_type else "commit")
            return self._raw.__exit__(exc_type, exc, tb)

        def __getattr__(self, name):
            return getattr(self._raw, name)

    def run_authority(authority, module, exercise, drain):
        events = []
        local_mp = pytest.MonkeyPatch()

        def connect(*args, **kwargs):
            events.append((authority, "create", threading.get_ident(), threading.current_thread().name))
            return ObservedConnection(real_connect(*args, **kwargs), events, authority)

        try:
            local_mp.setattr(module.sqlite3, "connect", connect)
            exercise()
            result = drain()
            assert result
        finally:
            local_mp.undo()
        assert events
        operations = {row[1] for row in events}
        assert "create" in operations
        assert "execute" in operations or "executemany" in operations
        assert "commit" in operations
        assert "close" in operations
        owner_ids = {row[2] for row in events}
        assert len(owner_ids) == 1
        owner_id = next(iter(owner_ids))
        assert owner_id != callback_thread
        return events

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "gate4.db"), raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)
    trade_store._DB_SCHEMA_INIT_PATH = None

    tick_store.reset_runtime_state_for_tests()
    tick_events = run_authority(
        "tick",
        tick_store,
        lambda: tick_store.insert_tick(ts="2026-08-03T10:30:00Z", token=94_001, last_price=101.0),
        lambda: tick_store.shutdown_persistence_worker(deadline_seconds=2.0),
    )

    runtime_store.reset_runtime_persistence_for_tests()
    file_writer_threads = []
    real_json_writer = runtime_store.write_json_atomic

    def observed_json_writer(*args, **kwargs):
        file_writer_threads.append((threading.get_ident(), threading.current_thread().name))
        return real_json_writer(*args, **kwargs)

    monkeypatch.setattr(runtime_store, "write_json_atomic", observed_json_writer)
    runtime_events = run_authority(
        "runtime",
        runtime_store,
        lambda: runtime_store.write_runtime_snapshot({"source": "gate4", "runtime_state": "RUNNING"}),
        lambda: runtime_store.shutdown_runtime_persistence(deadline_seconds=2.0),
    )
    assert file_writer_threads
    assert {row[0] for row in file_writer_threads} == {runtime_events[0][2]}

    store = DepthStore()
    depth_events = run_authority(
        "depth",
        trade_store,
        lambda: store.update(94_002, {"buy": [{"quantity": 2}], "sell": [{"quantity": 1}]}),
        lambda: store.shutdown_persistence(deadline_seconds=2.0),
    )

    assert {row[2] for row in tick_events} != {callback_thread}
    assert {row[2] for row in runtime_events} != {callback_thread}
    assert {row[2] for row in depth_events} != {callback_thread}
''',
    )

    print("PR763_OFFLINE_REPAIRS_APPLIED" if changed else "PR763_OFFLINE_REPAIRS_ALREADY_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
