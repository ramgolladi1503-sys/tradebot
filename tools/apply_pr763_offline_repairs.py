"""Idempotent source repair for PR #763 offline certification.

This temporary maintenance script is executed only by the branch-local offline
workflow.  It performs exact, guarded replacements and fails if the expected
source no longer matches.  Remove it with the temporary workflow after the PR is
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
        'pr_number=763',
        'pr_number=750',
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

    print("PR763_OFFLINE_REPAIRS_APPLIED" if changed else "PR763_OFFLINE_REPAIRS_ALREADY_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
