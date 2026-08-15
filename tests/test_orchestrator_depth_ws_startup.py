from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from config import config as cfg
from tests.fixtures.canonical_feed_factory import make_valid_canonical_feed_pair


def test_start_depth_ws_or_raise_fail_closed(monkeypatch):
    import core.orchestrator as orchestrator_mod
    import core.auth as auth_mod
    monkeypatch.setattr(auth_mod, "get_kite_credentials", lambda: ("api_key", "access_token", "enctoken"))

    class _Dummy:
        def _start_depth_ws(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "DRY_RUN", False, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_STARTUP_FAIL_CLOSED", True, raising=False)
    import core.auth
    monkeypatch.setattr(core.auth, "get_kite_credentials", lambda: None, raising=False)

    with pytest.raises(RuntimeError, match="boom"):
        orchestrator_mod.Orchestrator._start_depth_ws_or_raise(
            _Dummy(),
            start_depth_ws_enabled=True,
        )


def test_start_depth_ws_or_raise_fail_open(monkeypatch):
    import core.orchestrator as orchestrator_mod
    import core.auth as auth_mod
    monkeypatch.setattr(auth_mod, "get_kite_credentials", lambda: ("api_key", "access_token", "enctoken"))

    class _Dummy:
        def _start_depth_ws(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "DRY_RUN", False, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_STARTUP_FAIL_CLOSED", False, raising=False)
    import core.auth
    monkeypatch.setattr(core.auth, "get_kite_credentials", lambda: None, raising=False)

    orchestrator_mod.Orchestrator._start_depth_ws_or_raise(
        _Dummy(),
        start_depth_ws_enabled=True,
    )


def test_start_depth_ws_or_raise_recoverable_network_error_degrades(monkeypatch):
    import core.orchestrator as orchestrator_mod
    import core.auth as auth_mod
    monkeypatch.setattr(auth_mod, "get_kite_credentials", lambda: ("api_key", "access_token", "enctoken"))

    class _Dummy:
        def _start_depth_ws(self):
            raise RuntimeError(
                "kite_depth_ws_profile_failed:HTTPSConnectionPool(host='api.kite.trade', port=443): "
                "Max retries exceeded with url: /user/profile (Caused by NameResolutionError("
                "\"<urllib3.connection.HTTPSConnection object at 0x1>: Failed to resolve 'api.kite.trade' "
                "([Errno 8] nodename nor servname provided, or not known)\"))"
            )

    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "DRY_RUN", False, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_STARTUP_FAIL_CLOSED", True, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_STARTUP_FAIL_OPEN_ON_RECOVERABLE_ERRORS", True, raising=False)
    import core.auth
    monkeypatch.setattr(core.auth, "get_kite_credentials", lambda: None, raising=False)

    orchestrator_mod.Orchestrator._start_depth_ws_or_raise(
        _Dummy(),
        start_depth_ws_enabled=True,
    )


def _patch_start_depth_ws_dependencies(monkeypatch, *, runtime_snapshot: dict):
    import core.auth_health as auth_health
    import core.feed.runtime_store as runtime_store
    import core.kite_depth_ws as ws
    import core.orchestrator as orchestrator_mod

    class _KiteOk:
        def __init__(self, api_key=None):
            self.api_key = api_key

        def profile(self):
            return {"user_id": "ABCD1234"}

    start_mock = Mock()
    monkeypatch.setattr(orchestrator_mod, "start_depth_ws", start_mock)
    monkeypatch.setattr(orchestrator_mod.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(orchestrator_mod.kite_client, "kite", _KiteOk("api_key_1234"), raising=False)
    monkeypatch.setattr(auth_health, "get_kite_auth_health", lambda force=True: {"ok": True, "user_id": "ABCD1234"})
    monkeypatch.setattr(ws, "build_depth_subscription_tokens", lambda symbols: ([101], [{"symbol": "NIFTY", "count": 1}]))
    # Keep the legacy runtime-store boundary available for the startup method,
    # but seed the authoritative currentness source as a production-shaped
    # canonical truth/runtime pair.  The startup validator must decide from
    # canonical feed authority, not from an ad-hoc dict alone.
    monkeypatch.setattr(runtime_store, "read_latest_runtime_snapshot", lambda: runtime_snapshot)
    root = Path(os.environ["DATA_ROOT"]) / "logs"
    make_valid_canonical_feed_pair(
        root,
        feed_ok=bool(runtime_snapshot.get("ws_connected", False)),
        runtime_updates=runtime_snapshot,
    )
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(cfg, "SYMBOLS", ["NIFTY"], raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_STARTUP_SNAPSHOT_MAX_AGE_SEC", 30.0, raising=False)
    return orchestrator_mod, start_mock


def test_start_depth_ws_raises_on_fresh_failed_runtime_snapshot(monkeypatch):
    runtime_snapshot = {
        "ts_epoch": time.time(),
        "runtime_state": "SUBSCRIBE_FAILED",
        "source": "start_depth_ws:subscribe_failed",
        "last_error": "no_instrument_tokens",
        "ws_connected": False,
    }
    orchestrator_mod, start_mock = _patch_start_depth_ws_dependencies(
        monkeypatch,
        runtime_snapshot=runtime_snapshot,
    )

    with pytest.raises(RuntimeError, match="runtime_state=SUBSCRIBE_FAILED"):
        orchestrator_mod.Orchestrator._start_depth_ws(object())
    assert start_mock.call_count == 1


def test_start_depth_ws_ignores_stale_failed_runtime_snapshot(monkeypatch):
    runtime_snapshot = {
        "ts_epoch": time.time() - 120.0,
        "runtime_state": "SUBSCRIBE_FAILED",
        "source": "start_depth_ws:subscribe_failed",
        "last_error": "stale_failure",
        "ws_connected": False,
    }
    orchestrator_mod, start_mock = _patch_start_depth_ws_dependencies(
        monkeypatch,
        runtime_snapshot=runtime_snapshot,
    )

    orchestrator_mod.Orchestrator._start_depth_ws(object())
    assert start_mock.call_count == 1
