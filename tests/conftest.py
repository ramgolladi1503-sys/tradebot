import sys
import os
import tempfile
from pathlib import Path
import pytest

from core.lifecycle import stop_all as stop_lifecycle

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Keep runtime writes outside the repo during tests.
_TEST_RUNTIME_ROOT = Path(tempfile.gettempdir()) / "trading_bot_runtime_tests"
os.environ.setdefault("DATA_ROOT", str(_TEST_RUNTIME_ROOT))
os.environ.setdefault("LOGS_ROOT", str(_TEST_RUNTIME_ROOT / "logs"))
os.environ.setdefault("LOCKS_ROOT", str(_TEST_RUNTIME_ROOT / "locks"))
os.environ.setdefault("DB_ROOT", str(_TEST_RUNTIME_ROOT / "db"))
os.environ.setdefault("REPORTS_ROOT", str(_TEST_RUNTIME_ROOT / "reports"))
os.environ.setdefault("ANALYTICS_RUNTIME_DIR", str(_TEST_RUNTIME_ROOT / "analytics"))


@pytest.fixture(autouse=True)
def _isolate_runtime_state(monkeypatch, tmp_path):
    """Evidence contract: every test gets isolated runtime state.

    The suite frequently monkeypatches cfg.EXECUTION_MODE directly. A leftover
    TRADING_MODE or DRY_RUN env var from a manual run can override that and push
    live-mode safety tests through paper/sim branches. Runtime files also need a
    per-test root so run locks and auth cooldown breadcrumbs cannot leak between
    tests.
    """

    monkeypatch.delenv("TRADING_MODE", raising=False)
    monkeypatch.delenv("DRY_RUN", raising=False)

    from core import tick_store

    tick_store.reset_runtime_state_for_tests()

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

    import json
    feed_path = runtime_root / "logs" / "feed_runtime_latest.json"
    feed_path.parent.mkdir(parents=True, exist_ok=True)
    feed_path.write_text(json.dumps({"feed_ok": True}), encoding="utf-8")

    yield

    tick_store.reset_runtime_state_for_tests()


@pytest.fixture(scope="session", autouse=True)
def _shutdown_managed_runtime_lifecycle():
    try:
        yield
    finally:
        # Explicit component stop first, then registered handles; safe to call repeatedly.
        stop_lifecycle(timeout=3.0, reason="pytest_teardown")
