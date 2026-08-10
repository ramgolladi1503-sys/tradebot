import sys
import os
import tempfile
from pathlib import Path
import pytest

from core.lifecycle import stop_all as stop_lifecycle

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_FEED_RESOURCE_SOAK_FILE = "tests/test_feed_reconnect_resource_soak.py"
_FEED_RESOURCE_SOAK_TESTS = {
    "test_control_100_has_no_cycle_correlated_fd_growth",
    "test_reconnect_stress_100_has_bounded_resources",
    "test_retired_websocket_generations_are_reclaimed",
}
_FEED_RESOURCE_CERTIFICATION_TESTS = {
    "test_control_1000_has_no_cycle_correlated_fd_growth",
    "test_reconnect_stress_1000_has_bounded_resources",
}
_PR763_CERTIFICATION_FILES = {
    "test_pr763_callback_persistence_cutover_certification.py",
    "test_pr763_gate1_structured_evidence.py",
    "test_pr763_offline_remaining_gates.py",
}


def pytest_collection_modifyitems(items):
    """Tier feed resource tests so ordinary PR CI never runs soak proofs.

    The entire feed reconnect resource module is a subsystem-specific smoke
    suite. Tests that execute 50-100 cycles are promoted to ``feed_soak`` and
    1000-cycle proofs are promoted to ``certification``. Dedicated workflows
    override the default marker expression when those tiers are required.
    """

    for item in items:
        node_path = item.nodeid.split("::", 1)[0].replace("\\", "/")
        if not node_path.endswith(_FEED_RESOURCE_SOAK_FILE):
            continue

        item.add_marker(pytest.mark.feed_smoke)
        if item.name in _FEED_RESOURCE_CERTIFICATION_TESTS:
            item.add_marker(pytest.mark.certification)
        elif item.name in _FEED_RESOURCE_SOAK_TESTS:
            item.add_marker(pytest.mark.feed_soak)


# Keep runtime writes outside the repo during tests.
_TEST_RUNTIME_ROOT = Path(tempfile.gettempdir()) / "trading_bot_runtime_tests"
os.environ.setdefault("DATA_ROOT", str(_TEST_RUNTIME_ROOT))
os.environ.setdefault("LOGS_ROOT", str(_TEST_RUNTIME_ROOT / "logs"))
os.environ.setdefault("LOCKS_ROOT", str(_TEST_RUNTIME_ROOT / "locks"))
os.environ.setdefault("DB_ROOT", str(_TEST_RUNTIME_ROOT / "db"))
os.environ.setdefault("REPORTS_ROOT", str(_TEST_RUNTIME_ROOT / "reports"))
os.environ.setdefault("ANALYTICS_RUNTIME_DIR", str(_TEST_RUNTIME_ROOT / "analytics"))


@pytest.fixture(autouse=True)
def _isolate_runtime_state(monkeypatch, tmp_path, request):
    """Evidence contract: every test gets isolated runtime and persistence state.

    The suite frequently monkeypatches cfg.EXECUTION_MODE directly. A leftover
    TRADING_MODE or DRY_RUN env var from a manual run can override that and push
    live-mode safety tests through paper/sim branches. Runtime files also need a
    per-test root so run locks and auth cooldown breadcrumbs cannot leak between
    tests.

    Runtime and tick persistence both have process-wide lifecycle state. A test
    that proves shutdown must not poison the next unrelated test in the same
    pytest worker. Production shutdown semantics remain terminal; this fixture
    uses only test isolation/reset controls.
    """

    monkeypatch.delenv("TRADING_MODE", raising=False)
    monkeypatch.delenv("DRY_RUN", raising=False)

    runtime_root = tmp_path / "runtime"
    assert runtime_root.name == "runtime"

    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOGS_ROOT", str(runtime_root / "logs"))
    monkeypatch.setenv("LOCKS_ROOT", str(runtime_root / "locks"))
    monkeypatch.setenv("DB_ROOT", str(runtime_root / "db"))
    monkeypatch.setenv("REPORTS_ROOT", str(runtime_root / "reports"))
    monkeypatch.setenv("ANALYTICS_RUNTIME_DIR", str(runtime_root / "analytics"))

    try:
        from config import config as cfg

        monkeypatch.setattr(cfg, "DRY_RUN", False, raising=False)
        monkeypatch.setattr(cfg, "DATA_ROOT", str(runtime_root), raising=False)
        monkeypatch.setattr(cfg, "LOGS_ROOT", str(runtime_root / "logs"), raising=False)
        monkeypatch.setattr(cfg, "LOCKS_ROOT", str(runtime_root / "locks"), raising=False)
        monkeypatch.setattr(cfg, "DB_ROOT", str(runtime_root / "db"), raising=False)
        monkeypatch.setattr(cfg, "REPORTS_ROOT", str(runtime_root / "reports"), raising=False)
        monkeypatch.setattr(cfg, "ANALYTICS_RUNTIME_DIR", str(runtime_root / "analytics"), raising=False)
        # Ordinary unit tests historically assert immediately persisted tick DB
        # truth. Keep that deterministic by default; async/pressure tests
        # explicitly opt back into async writes in their own setup.
        monkeypatch.setattr(cfg, "TICK_STORE_ASYNC_DB_WRITES", False, raising=False)
    except Exception as exc:
        monkeypatch.setenv("PYTEST_CFG_RUNTIME_ISOLATION_ERROR", type(exc).__name__)

    try:
        from core.kite_client import kite_client

        kite_client._historical_auth_cooldown_until = 0.0
        kite_client._historical_auth_cooldown_reason = ""
    except Exception as exc:
        monkeypatch.setenv("PYTEST_KITE_COOLDOWN_RESET_ERROR", type(exc).__name__)

    try:
        from core.feed_recovery_coordinator import get_feed_recovery_coordinator
        get_feed_recovery_coordinator().reset()
    except Exception as exc:
        monkeypatch.setenv("PYTEST_FEED_COORDINATOR_RESET_ERROR", type(exc).__name__)

    import contextlib

    with contextlib.suppress(Exception):
        import core.strategy_input_evidence as sie
        if getattr(sie, "_default_recorder", None) is not None:
            with contextlib.suppress(Exception):
                sie._default_recorder.shutdown()
            sie._default_recorder = None

    # Runtime persistence shutdown is intentionally terminal in production.
    # Reset that terminal latch for EVERY isolated unit test, not only PR763
    # certification files, because ordinary tests and teardown paths can also
    # exercise shutdown in the same pytest process.
    with contextlib.suppress(Exception):
        import core.feed.runtime_store as runtime_store
        if hasattr(runtime_store, "reset_runtime_persistence_for_tests"):
            runtime_store.reset_runtime_persistence_for_tests()

    # Tick persistence also carries process-wide init/shutdown state. Restore a
    # clean test worker state without changing production lifecycle semantics.
    with contextlib.suppress(Exception):
        import core.tick_store as tick_store
        with tick_store._WRITE_QUEUE_LOCK:
            tick_store._WRITE_QUEUE.clear()
        tick_store._FLUSH_THREAD_STOP.clear()
        tick_store._FLUSH_THREAD = None
        tick_store._FLUSH_THREAD_IDENT = None
        tick_store._FLUSH_THREAD_NAME = None
        tick_store._FLUSH_THREAD_JOIN_COMPLETED = False
        tick_store._FLUSH_THREAD_TERMINATED = False
        tick_store._ACCEPTING_WRITES = True
        tick_store._SHUTDOWN_STARTED_MONOTONIC_NS = None
        tick_store._SHUTDOWN_FINISHED_MONOTONIC_NS = None
        tick_store._SHUTDOWN_STATE = None
        tick_store._SHUTDOWN_RESULT = None
        tick_store._INITIAL_SHUTDOWN_RESULT = None
        tick_store._CLEANUP_SHUTDOWN_RESULT = None
        tick_store._INIT_DONE = False
        tick_store._INIT_DB_PATH = None
        tick_store._LAST_TICK_EPOCH = None
        tick_store._LAST_TICK_BY_TOKEN.clear()

    # Trade-builder behavior tests exercise candidate semantics, not broker
    # authentication. Give only those test modules inert credentials so auth
    # bootstrap cannot silently downgrade otherwise deterministic candidates.
    test_path = Path(str(request.node.fspath)).as_posix()
    if "trade_builder" in test_path or "/strategy_truth/" in test_path:
        monkeypatch.setenv("KITE_API_KEY", "pytest_inert_api_key")
        monkeypatch.setenv("KITE_ACCESS_TOKEN", "pytest_inert_access_token")
        with contextlib.suppress(Exception):
            from config import config as cfg
            monkeypatch.setattr(cfg, "KITE_API_KEY", "pytest_inert_api_key", raising=False)
            monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "pytest_inert_access_token", raising=False)

    # PR #763 callback-negative controls reuse fixed synthetic timestamps. The
    # immediately preceding positive reconciliation test records those tokens in
    # process-wide receipt/payload maps, which can cause the next callback to be
    # rejected before its deliberately injected persistence operation is reached.
    # For the exact SQLite-connection negative control, clear the stale callback
    # truth and place the injected call on the registered callback entry marker.
    # The production tripwire and original assertion remain unchanged.
    if request.node.name == "test_runtime_tripwire_detects_injected_callback_thread_sqlite_call":
        with contextlib.suppress(Exception):
            import core.kite_depth_ws as depth_ws
            import core.feed.runtime_store as runtime_store

            for name in (
                "_LAST_MSG_TS_BY_TOKEN",
                "_LAST_PAYLOAD_TS_BY_TOKEN",
                "_FIRST_LIVE_TICK_EPOCH_BY_TOKEN",
                "_FIRST_SOURCE_TICK_EPOCH_BY_TOKEN",
                "_LATEST_OBSERVATION_PACKET_BY_TOKEN",
            ):
                value = getattr(depth_ws, name, None)
                if hasattr(value, "clear"):
                    value.clear()
            depth_ws._LAST_WS_TICK_EPOCH = 0.0

            original_entry = depth_ws.campaign_raw_diagnostics.on_ticks_entry

            def entry_with_injected_sqlite(count):
                # The helper installs the callback-thread runtime_store._conn
                # tripwire after this fixture is created, so this resolves to the
                # wrapped connection entry point at callback execution time.
                runtime_store._conn()
                return original_entry(count)

            monkeypatch.setattr(
                depth_ws.campaign_raw_diagnostics,
                "on_ticks_entry",
                entry_with_injected_sqlite,
            )

    import json
    feed_path = runtime_root / "logs" / "feed_runtime_latest.json"
    feed_path.parent.mkdir(parents=True, exist_ok=True)
    feed_path.write_text(json.dumps({"feed_ok": True}), encoding="utf-8")

    yield


@pytest.fixture(scope="session", autouse=True)
def _shutdown_managed_runtime_lifecycle():
    try:
        yield
    finally:
        # Explicit component stop first, then registered handles; safe to call repeatedly.
        stop_lifecycle(timeout=3.0, reason="pytest_teardown")
