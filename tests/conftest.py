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


@pytest.fixture(autouse=True)
def _isolate_runtime_state(monkeypatch, tmp_path):
    """Keep tests deterministic when the developer shell has live-mode state.

    The suite frequently monkeypatches cfg.EXECUTION_MODE directly. A leftover
    TRADING_MODE/DRY_RUN env var from a manual run can override that and push
    LIVE safety tests through PAPER/SIM branches. Runtime files also need a
    per-test root so run locks and auth cooldown breadcrumbs cannot leak between
    tests.
    """

    monkeypatch.delenv("TRADING_MODE", raising=False)
    monkeypatch.delenv("DRY_RUN", raising=False)

    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOGS_ROOT", str(runtime_root / "logs"))
    monkeypatch.setenv("LOCKS_ROOT", str(runtime_root / "locks"))
    monkeypatch.setenv("DB_ROOT", str(runtime_root / "db"))
    monkeypatch.setenv("REPORTS_ROOT", str(runtime_root / "reports"))

    try:
        from config import config as cfg

        monkeypatch.setattr(cfg, "DRY_RUN", False, raising=False)
        monkeypatch.setattr(cfg, "DATA_ROOT", str(runtime_root), raising=False)
        monkeypatch.setattr(cfg, "LOGS_ROOT", str(runtime_root / "logs"), raising=False)
        monkeypatch.setattr(cfg, "LOCKS_ROOT", str(runtime_root / "locks"), raising=False)
        monkeypatch.setattr(cfg, "DB_ROOT", str(runtime_root / "db"), raising=False)
        monkeypatch.setattr(cfg, "REPORTS_ROOT", str(runtime_root / "reports"), raising=False)
    except Exception:
        pass

    try:
        from core.kite_client import kite_client

        kite_client._historical_auth_cooldown_until = 0.0
        kite_client._historical_auth_cooldown_reason = ""
    except Exception:
        pass

    yield


@pytest.fixture(scope="session", autouse=True)
def _shutdown_managed_runtime_lifecycle():
    try:
        yield
    finally:
        # Explicit component stop first, then registered handles; safe to call repeatedly.
        stop_lifecycle(timeout=3.0, reason="pytest_teardown")
