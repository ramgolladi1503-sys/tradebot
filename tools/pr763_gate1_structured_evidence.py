"""Structured offline evidence collector for PR #763 Gate 1.

This module deliberately reuses the registered-callback certification fixture.  It
never starts Kite, a WebSocket, a broker session, a child runtime, or order logic.
Each negative control is executed in a fresh Python process so process-wide worker
singletons cannot leak authority between controls.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TEST_MODULE = ROOT / "tests" / "test_pr763_callback_persistence_cutover_certification.py"
CALLBACK_PATH = "_register_on_ticks_callback -> kws.on_ticks -> core.kite_depth_ws.on_ticks"
FROZEN_CALLBACK_SLA_MS = 5_000.0

SQLITE_OPERATION_CASES = {
    "sqlite_connection_execute": "connection.execute",
    "sqlite_connection_executemany": "connection.executemany",
    "sqlite_connection_commit": "connection.commit",
    "sqlite_connection_rollback": "connection.rollback",
    "sqlite_connection_close": "connection.close",
    "sqlite_cursor_execute": "cursor.execute",
    "sqlite_cursor_executemany": "cursor.executemany",
    "sqlite_cursor_close": "cursor.close",
}
STORE_CASES = {
    "tick_sync": "tick_store._write_rows",
    "depth_sync": "trade_store.insert_depth_snapshot",
    "runtime_sync": "runtime_store._write_runtime_snapshot_sync",
    "event_json": "events.write_json_atomic",
}
FILESYSTEM_CASES = {
    "builtins_open": "builtins.open",
    "path_open": "Path.open",
}


def _load_test_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_pr763_gate1_tests", TEST_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError("PR763_CERTIFICATION_TEST_MODULE_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _thread_payload(value: tuple[int, str] | None) -> dict[str, Any]:
    if not value:
        return {"thread_id": None, "thread_name": None}
    return {"thread_id": int(value[0]), "thread_name": str(value[1])}


def _cleanup(cert: ModuleType, runtime_mod: Any, depth_store: Any) -> None:
    try:
        runtime_mod.shutdown_runtime_persistence(deadline_seconds=2.0)
    except Exception:
        pass
    try:
        cert.tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
    except Exception:
        pass
    try:
        depth_store.shutdown_persistence(deadline_seconds=2.0)
    except Exception:
        pass


def _instrument_registration(cert: ModuleType, monkeypatch: Any, metrics: dict[str, Any]) -> None:
    original_register = cert.depth_ws._register_on_ticks_callback

    def instrumented_register(ticker: Any, generation_predicate: Any, delegate: Any):
        def observed_delegate(ws: Any, ticks: Any):
            metrics["delegate_entries"] += 1
            try:
                return delegate(ws, ticks)
            except Exception:
                metrics["delegate_exceptions"] += 1
                raise
            finally:
                metrics["delegate_exits"] += 1

        registered = original_register(ticker, generation_predicate, observed_delegate)

        def observed_callback(ws: Any, ticks: Any):
            metrics["wrapper_entries"] += 1
            metrics["callback_thread_id"] = threading.get_ident()
            metrics["callback_thread_name"] = threading.current_thread().name
            started = time.monotonic_ns()
            try:
                return registered(ws, ticks)
            except Exception:
                metrics["callback_exceptions"] += 1
                raise
            finally:
                duration_ms = (time.monotonic_ns() - started) / 1_000_000.0
                metrics["durations_ms"].append(float(duration_ms))
                metrics["wrapper_exits"] += 1

        setattr(ticker, "on_ticks", observed_callback)
        return observed_callback

    monkeypatch.setattr(cert.depth_ws, "_register_on_ticks_callback", instrumented_register)


def _positive_case(root: Path) -> dict[str, Any]:
    import pytest

    cert = _load_test_module()
    metrics: dict[str, Any] = {
        "wrapper_entries": 0,
        "wrapper_exits": 0,
        "delegate_entries": 0,
        "delegate_exits": 0,
        "delegate_exceptions": 0,
        "callback_exceptions": 0,
        "callback_thread_id": None,
        "callback_thread_name": None,
        "durations_ms": [],
    }
    monkeypatch = pytest.MonkeyPatch()
    runtime_mod = cert.runtime_store
    depth_store = cert.depth_ws.depth_store
    try:
        if hasattr(cert.tick_store, "reset_runtime_state_for_tests"):
            cert.tick_store.reset_runtime_state_for_tests()
        else:
            cert.tick_store.reset_audit_counters()
        runtime_mod.shutdown_runtime_persistence(deadline_seconds=1.0)
        cert.depth_ws.depth_store.shutdown_persistence(deadline_seconds=1.0)
        cert.depth_ws.depth_store = cert.depth_store_module.DepthStore()
        depth_store = cert.depth_ws.depth_store

        tick_before = cert.tick_store.get_audit_counters()
        tick_before_persisted = cert.tick_store.write_flush_count()
        runtime_before = runtime_mod.runtime_persistence_state()
        depth_before = depth_store.persistence_state()

        _instrument_registration(cert, monkeypatch, metrics)
        (
            callback,
            counts,
            violations,
            helper_duration_ms,
            runtime_mod,
            exercised_depth_store,
            worker_ids,
            sqlite_operations,
        ) = cert._run_registered_live_persistence_fixture(monkeypatch, root)

        runtime_drain = runtime_mod.shutdown_runtime_persistence(deadline_seconds=2.0)
        tick_drain = cert.tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
        depth_drain = exercised_depth_store.shutdown_persistence(deadline_seconds=2.0)

        tick_after = cert.tick_store.get_audit_counters()
        tick_after_persisted = cert.tick_store.write_flush_count()
        runtime_after = runtime_mod.runtime_persistence_state()
        depth_after = exercised_depth_store.persistence_state()

        tick_rejected_before = int(tick_before.get("writes_rejected_after_shutdown", 0)) + int(
            tick_before.get("writes_rejected_queue_full", 0)
        )
        tick_rejected_after = int(tick_after.get("writes_rejected_after_shutdown", 0)) + int(
            tick_after.get("writes_rejected_queue_full", 0)
        )

        authorities = {
            "tick": {
                "accepted_delta": int(tick_after.get("rows_enqueued", 0)) - int(tick_before.get("rows_enqueued", 0)),
                "persisted_delta": int(tick_after_persisted) - int(tick_before_persisted),
                "pending_after_drain": int(tick_drain.get("pending_writes", 0)),
                "rejected_delta": tick_rejected_after - tick_rejected_before,
                "failure_delta": int(tick_after.get("worker_failures", 0)) - int(tick_before.get("worker_failures", 0)),
                "drain_complete": tick_drain.get("status") == "COMPLETE_DRAIN",
                "worker_alive_after_drain": bool(tick_drain.get("worker_alive", False)),
                "drain": dict(tick_drain),
            },
            "depth": {
                "same_instance": exercised_depth_store is depth_store,
                "accepted_delta": int(depth_after.get("enqueued", 0)) - int(depth_before.get("enqueued", 0)),
                "persisted_delta": int(depth_after.get("persisted", 0)) - int(depth_before.get("persisted", 0)),
                "pending_after_drain": int(depth_after.get("queue_depth", 0)),
                "rejected_delta": int(depth_after.get("rejected", 0)) - int(depth_before.get("rejected", 0)),
                "failure_delta": int(depth_after.get("failures", 0)) - int(depth_before.get("failures", 0)),
                "drain_complete": bool(depth_drain.get("complete")),
                "worker_alive_after_drain": bool(depth_drain.get("worker_alive", False)),
                "drain": dict(depth_drain),
            },
            "runtime": {
                "accepted_delta": int(runtime_after.get("enqueued", 0)) - int(runtime_before.get("enqueued", 0)),
                "persisted_delta": int(runtime_after.get("persisted", 0)) - int(runtime_before.get("persisted", 0)),
                "pending_after_drain": int(runtime_after.get("pending", 0)),
                "rejected_delta": int(runtime_after.get("rejected", 0)) - int(runtime_before.get("rejected", 0)),
                "failure_delta": int(runtime_after.get("failures", 0)) - int(runtime_before.get("failures", 0)),
                "drain_complete": bool(runtime_drain.get("complete")),
                "worker_alive_after_drain": bool(runtime_drain.get("worker_alive", False)),
                "drain": dict(runtime_drain),
            },
        }
        maximum_duration_ms = max(metrics["durations_ms"] or [float(helper_duration_ms)])
        callback_thread = {
            "thread_id": metrics["callback_thread_id"],
            "thread_name": metrics["callback_thread_name"],
            "wrapper_entries": metrics["wrapper_entries"],
            "wrapper_exits": metrics["wrapper_exits"],
            "delegate_entries": metrics["delegate_entries"],
            "delegate_exits": metrics["delegate_exits"],
            "exceptions": metrics["callback_exceptions"] + metrics["delegate_exceptions"],
            "duration_ms": float(metrics["durations_ms"][0] if metrics["durations_ms"] else helper_duration_ms),
            "maximum_duration_ms": float(maximum_duration_ms),
            "frozen_sla_ms": FROZEN_CALLBACK_SLA_MS,
        }
        workers = {name: _thread_payload(worker_ids.get(name)) for name in ("tick", "depth", "runtime")}
        normal_sqlite = [list(row) for row in violations if str(row[0]).startswith("sqlite")]
        normal_store = [list(row) for row in violations if row[0] == "store"]
        normal_filesystem = [list(row) for row in violations if row[0] == "filesystem"]
        return {
            "callback": callback_thread,
            "workers": workers,
            "authorities": authorities,
            "enqueue_counts": dict(counts),
            "registered_callback_present": callback is not None,
            "sqlite": {
                "normal_violations": normal_sqlite,
                "worker_operations": [list(row) for row in sqlite_operations],
            },
            "synchronous_stores": {"normal_violations": normal_store},
            "filesystem": {"normal_violations": normal_filesystem, "monitored_roots": [str(root.resolve())]},
        }
    finally:
        _cleanup(cert, runtime_mod, depth_store)
        monkeypatch.undo()


def _negative_case(root: Path, injection: str) -> dict[str, Any]:
    import pytest

    cert = _load_test_module()
    monkeypatch = pytest.MonkeyPatch()
    runtime_mod = cert.runtime_store
    depth_store = cert.depth_ws.depth_store
    unscoped_path = Path(tempfile.gettempdir()) / f"pr763-unscoped-{os.getpid()}.txt"
    try:
        if injection == "unscoped_open":
            original_entry = cert.depth_ws.campaign_raw_diagnostics.on_ticks_entry

            def entry_with_unscoped_open(count: int):
                with open(unscoped_path, "w", encoding="utf-8") as handle:
                    handle.write("outside monitored persistence root")
                return original_entry(count)

            monkeypatch.setattr(cert.depth_ws.campaign_raw_diagnostics, "on_ticks_entry", entry_with_unscoped_open)
            helper_injection = None
        else:
            helper_injection = injection
        (
            _,
            _,
            violations,
            duration_ms,
            runtime_mod,
            depth_store,
            worker_ids,
            sqlite_operations,
        ) = cert._run_registered_live_persistence_fixture(monkeypatch, root, helper_injection)
        return {
            "injection": injection,
            "violations": [list(row) for row in violations],
            "sqlite_operations": [list(row) for row in sqlite_operations],
            "duration_ms": float(duration_ms),
            "worker_ids": {name: _thread_payload(worker_ids.get(name)) for name in worker_ids},
            "unscoped_file_created": bool(unscoped_path.exists()) if injection == "unscoped_open" else None,
        }
    finally:
        _cleanup(cert, runtime_mod, depth_store)
        monkeypatch.undo()
        try:
            unscoped_path.unlink(missing_ok=True)
        except Exception:
            pass


def _launcher_case(root: Path) -> dict[str, Any]:
    from core.unified_live_validation_pr748_756 import launcher, runtime_observer
    from core.unified_live_validation_pr748_756.campaign_contract import CampaignIdentity

    session_date = "2026-08-03"
    identity = CampaignIdentity(
        run_id="pr763-20260803-offline",
        schema_version=1,
        session_date=session_date,
        campaign_commit_sha="a" * 40,
        composition_manifest_sha="b" * 64,
        evidence_root=str(root),
    )
    env = launcher.build_child_environment(identity, {"PATH": "/usr/bin"})
    observer_enabled = runtime_observer.enabled(env)
    observer = runtime_observer.UnifiedLiveRuntimeObserver.from_env(env)
    observer_effective = observer.identity.run_id == identity.run_id and observer.identity.evidence_root == identity.evidence_root
    observer.shutdown(seal=False, state="OFFLINE_CERTIFICATION")
    return {
        "live_source": {
            "configuration_source": "launcher.build_child_environment",
            "launcher_environment_key": "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE",
            "launcher_value": env.get("MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE"),
            "configured_state": str(env.get("MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", "")).lower() == "true",
            "effective_state": str(env.get("MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", "")).lower() == "true",
            "configuration_consumer": "core.kite_depth_ws launch-plan activation",
            "traversal_required": False,
            "observed_traversal_count": 0,
            "disabled_reason": None,
        },
        "observer": {
            "configuration_source": "launcher.build_child_environment",
            "launcher_environment_key": str(launcher.ENABLE_ENV),
            "launcher_value": env.get(launcher.ENABLE_ENV),
            "configured_state": bool(observer_enabled),
            "effective_state": bool(observer_effective),
            "configuration_consumer": "runtime_observer.enabled/from_env",
            "traversal_required": True,
            "observed_traversal_count": 1 if observer_effective else 0,
            "disabled_reason": None,
        },
        "constituent": {
            "configuration_source": "launcher.build_child_environment",
            "launcher_environment_key": "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH",
            "launcher_value": env.get("MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH"),
            "configured_state": bool(env.get("MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH")),
            "effective_state": False,
            "configuration_consumer": "launch plan / constituent source",
            "traversal_required": False,
            "observed_traversal_count": 0,
            "disabled_reason": "NOT_APPLICABLE_TO_GATE1_PERSISTENCE_FIXTURE",
        },
        "meg": {
            "configuration_source": "launcher.build_child_environment",
            "launcher_environment_key": "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE",
            "launcher_value": env.get("MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE"),
            "configured_state": str(env.get("MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", "")).lower() == "true",
            "effective_state": False,
            "configuration_consumer": "market-event-graph runtime bridge",
            "traversal_required": False,
            "observed_traversal_count": 0,
            "disabled_reason": "NOT_APPLICABLE_TO_GATE1_PERSISTENCE_FIXTURE",
        },
    }


def _run_case(case: str, root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    if case == "positive":
        return _positive_case(root)
    if case == "launcher":
        return _launcher_case(root)
    return _negative_case(root, case)


def _invoke_case(case: str, root: Path) -> dict[str, Any]:
    output = root / "case.json"
    command = [
        sys.executable,
        "-m",
        "tools.pr763_gate1_structured_evidence",
        "--case",
        case,
        "--root",
        str(root),
        "--output",
        str(output),
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**os.environ, "TRADEBOT_READ_ONLY": "true", "PYTHONPATH": str(ROOT)},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"PR763_STRUCTURED_CASE_FAILED case={case} returncode={result.returncode} "
            f"stdout={result.stdout[-2000:]} stderr={result.stderr[-4000:]}"
        )
    return json.loads(output.read_text(encoding="utf-8"))


def _find_violation(case_result: dict[str, Any], category: str, target: str) -> bool:
    for row in case_result.get("violations", []):
        if len(row) >= 2 and str(row[0]) == category and str(row[1]) == target:
            return True
    return False


def collect_structured_evidence(base_root: Path | None = None) -> dict[str, Any]:
    owned_tmp = None
    if base_root is None:
        owned_tmp = tempfile.TemporaryDirectory(prefix="pr763-gate1-")
        base_root = Path(owned_tmp.name)
    assert base_root is not None
    try:
        positive = _invoke_case("positive", base_root / "positive")
        launcher = _invoke_case("launcher", base_root / "launcher")
        negative_results: dict[str, Any] = {}
        for case in [*STORE_CASES, *SQLITE_OPERATION_CASES, *FILESYSTEM_CASES, "unscoped_open"]:
            negative_results[case] = _invoke_case(case, base_root / case)

        sqlite_controls = {}
        for case, target in SQLITE_OPERATION_CASES.items():
            result = negative_results[case]
            sqlite_controls[target] = {
                "detected": _find_violation(result, "sqlite_operation", target),
                "detected_target": target,
                "violations": result.get("violations", []),
            }
        store_controls = {}
        for case, target in STORE_CASES.items():
            result = negative_results[case]
            store_controls[target] = {
                "detected": any(len(row) >= 2 and str(row[1]) == target for row in result.get("violations", [])),
                "detected_target": target,
                "violations": result.get("violations", []),
            }
        filesystem_controls = {}
        for case, target in FILESYSTEM_CASES.items():
            result = negative_results[case]
            filesystem_controls[target] = {
                "detected": _find_violation(result, "filesystem", target),
                "detected_target": target,
                "violations": result.get("violations", []),
            }
        unscoped = negative_results["unscoped_open"]
        unscoped_detected = any(
            len(row) >= 2 and row[0] == "filesystem" and row[1] in {"builtins.open", "Path.open"}
            for row in unscoped.get("violations", [])
        )

        evidence = {
            "schema_version": 2,
            "registered_callback_path": CALLBACK_PATH,
            "live_started": False,
            "callback": positive["callback"],
            "workers": positive["workers"],
            "authorities": positive["authorities"],
            "enqueue_counts": positive["enqueue_counts"],
            "sqlite": {
                "connection_inventory": ["runtime_store._conn", "tick_store._conn", "trade_store._conn"],
                "operation_inventory": list(SQLITE_OPERATION_CASES.values()),
                "normal_violations": positive["sqlite"]["normal_violations"],
                "worker_operations": positive["sqlite"]["worker_operations"],
                "negative_controls": sqlite_controls,
            },
            "synchronous_stores": {
                "target_inventory": list(STORE_CASES.values()),
                "normal_violations": positive["synchronous_stores"]["normal_violations"],
                "negative_controls": store_controls,
            },
            "filesystem": {
                "target_inventory": [
                    "builtins.open",
                    "Path.open",
                    "Path.exists",
                    "Path.stat",
                    "Path.mkdir",
                    "Path.read_text",
                    "Path.read_bytes",
                    "Path.write_text",
                    "Path.write_bytes",
                    "os.stat",
                    "os.makedirs",
                    "os.fsync",
                ],
                "monitored_roots": positive["filesystem"]["monitored_roots"],
                "normal_violations": positive["filesystem"]["normal_violations"],
                "negative_controls": filesystem_controls,
                "unscoped_control": {
                    "file_created": bool(unscoped.get("unscoped_file_created")),
                    "detected_as_scoped": bool(unscoped_detected),
                    "violations": unscoped.get("violations", []),
                },
                "fsync_scope_authority": "CALLBACK_THREAD_ONLY; descriptor ownership is not asserted without a path-resolvable descriptor",
            },
            "launcher_hooks": launcher,
        }
        evidence["missing_controls"] = validate_structured_evidence(evidence)
        evidence["verdict"] = (
            "REAL_CALLBACK_PERSISTENCE_GATE_CLOSED"
            if not evidence["missing_controls"]
            else "REAL_CALLBACK_PERSISTENCE_GATE_FAILED"
        )
        return evidence
    finally:
        if owned_tmp is not None:
            owned_tmp.cleanup()


def validate_structured_evidence(evidence: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    callback = evidence.get("callback", {})
    if callback.get("thread_id") is None or not callback.get("thread_name"):
        missing.append("callback_identity")
    if not (
        callback.get("wrapper_entries") == callback.get("wrapper_exits") == 1
        and callback.get("delegate_entries") == callback.get("delegate_exits") == 1
        and callback.get("exceptions") == 0
    ):
        missing.append("callback_traversal_reconciliation")
    if not (
        isinstance(callback.get("maximum_duration_ms"), (int, float))
        and float(callback["maximum_duration_ms"]) < float(callback.get("frozen_sla_ms", 0))
        and float(callback["maximum_duration_ms"]) < FROZEN_CALLBACK_SLA_MS
    ):
        missing.append("callback_numeric_sla")

    callback_id = callback.get("thread_id")
    for authority in ("tick", "depth", "runtime"):
        worker = evidence.get("workers", {}).get(authority, {})
        row = evidence.get("authorities", {}).get(authority, {})
        if worker.get("thread_id") is None or worker.get("thread_id") == callback_id:
            missing.append(f"{authority}_worker_identity")
        if not (
            int(row.get("accepted_delta", 0)) >= 1
            and int(row.get("persisted_delta", -1)) == int(row.get("accepted_delta", 0))
            and int(row.get("pending_after_drain", -1)) == 0
            and int(row.get("rejected_delta", -1)) == 0
            and int(row.get("failure_delta", -1)) == 0
            and bool(row.get("drain_complete"))
            and not bool(row.get("worker_alive_after_drain"))
        ):
            missing.append(f"{authority}_exact_reconciliation")
    if not evidence.get("authorities", {}).get("depth", {}).get("same_instance"):
        missing.append("depth_same_instance")

    if evidence.get("sqlite", {}).get("normal_violations"):
        missing.append("normal_sqlite_callback_violations")
    for operation, row in evidence.get("sqlite", {}).get("negative_controls", {}).items():
        if not row.get("detected") or row.get("detected_target") != operation:
            missing.append(f"sqlite_negative_control:{operation}")

    if evidence.get("synchronous_stores", {}).get("normal_violations"):
        missing.append("normal_store_callback_violations")
    for target, row in evidence.get("synchronous_stores", {}).get("negative_controls", {}).items():
        if not row.get("detected") or row.get("detected_target") != target:
            missing.append(f"store_negative_control:{target}")

    if evidence.get("filesystem", {}).get("normal_violations"):
        missing.append("normal_filesystem_callback_violations")
    for target, row in evidence.get("filesystem", {}).get("negative_controls", {}).items():
        if not row.get("detected") or row.get("detected_target") != target:
            missing.append(f"filesystem_negative_control:{target}")
    unscoped = evidence.get("filesystem", {}).get("unscoped_control", {})
    if not unscoped.get("file_created") or unscoped.get("detected_as_scoped"):
        missing.append("unscoped_open_false_positive_control")

    observer = evidence.get("launcher_hooks", {}).get("observer", {})
    if not (
        observer.get("configured_state")
        and observer.get("effective_state")
        and int(observer.get("observed_traversal_count", 0)) >= 1
    ):
        missing.append("executed_launcher_observer_effective_state")
    live_source = evidence.get("launcher_hooks", {}).get("live_source", {})
    if not live_source.get("configured_state"):
        missing.append("launcher_live_source_configuration")
    return sorted(set(missing))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--root")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.case:
        if not args.root or not args.output:
            raise SystemExit("--case requires --root and --output")
        payload = _run_case(args.case, Path(args.root))
        Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    payload = collect_structured_evidence()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("verdict") == "REAL_CALLBACK_PERSISTENCE_GATE_CLOSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
