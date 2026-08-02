from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from config import config as cfg
import core
import core.auth as auth
import core.auth_manager as auth_manager


@pytest.fixture(autouse=True)
def _reset_auth_state(monkeypatch):
    auth.reset_kite_runtime_credentials_guard()
    auth_manager._CACHE.clear()
    for name in (
        "TRADING_BOT_TOKEN_PATH",
        "KITE_ACCESS_TOKEN",
        "KITE_ALLOW_ENV_TOKEN_FOR_CI",
        "KITE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    yield
    auth.reset_kite_runtime_credentials_guard()
    auth_manager._CACHE.clear()


def _install_security_guard(monkeypatch, calls=None):
    module = types.ModuleType("core.security_guard")

    def enforce(root):
        if calls is not None:
            calls.append(Path(root).resolve())

    module.enforce_no_repo_token_artifacts = enforce
    monkeypatch.setitem(sys.modules, "core.security_guard", module)
    monkeypatch.setattr(core, "security_guard", module, raising=False)


def _install_kite_client_module(monkeypatch, *, raw_client=None, singleton=None):
    module = types.ModuleType("core.kite_client")
    module._RAW_KITECONNECT = raw_client
    module.kite_client = singleton
    monkeypatch.setitem(sys.modules, "core.kite_client", module)
    monkeypatch.setattr(core, "kite_client", module, raising=False)
    return module


def _install_depth_module(monkeypatch, ticker_cls):
    module = types.ModuleType("core.kite_depth_ws")
    module.KiteTicker = ticker_cls
    monkeypatch.setitem(sys.modules, "core.kite_depth_ws", module)
    monkeypatch.setattr(core, "kite_depth_ws", module, raising=False)
    return module


def test_auth_helpers_and_caller_fallbacks(monkeypatch):
    assert auth._tail4("") == ""
    assert auth._tail4("abc") == "abc"
    assert auth._tail4("abcdef") == "cdef"

    monkeypatch.setattr(
        auth,
        "inspect",
        SimpleNamespace(currentframe=lambda: None),
    )
    assert auth._caller_module_name() == "unknown"

    terminal = SimpleNamespace(f_globals={}, f_back=None)
    initial = SimpleNamespace(f_globals={}, f_back=terminal)
    monkeypatch.setattr(
        auth,
        "inspect",
        SimpleNamespace(currentframe=lambda: initial),
    )
    assert auth._caller_module_name() == "unknown"


def test_runtime_credential_guard_accepts_same_pair_and_rejects_drift():
    auth._register_runtime_credentials("api_1234", "token_5678")
    auth._register_runtime_credentials("api_1234", "token_5678")

    with pytest.raises(RuntimeError, match="CREDENTIAL_DRIFT_DETECTED"):
        auth._register_runtime_credentials("api_9999", "token_5678")


def test_get_kite_credentials_is_fail_closed_and_registers_success(monkeypatch):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "", raising=False)
    with pytest.raises(RuntimeError, match="kite_api_key_missing"):
        auth.get_kite_credentials()

    monkeypatch.setattr(cfg, "KITE_API_KEY", "api_1234", raising=False)
    monkeypatch.setattr(auth, "resolve_access_token", lambda **_kwargs: "")
    with pytest.raises(RuntimeError, match="kite_access_token_missing"):
        auth.get_kite_credentials()

    monkeypatch.setattr(auth, "resolve_access_token", lambda **_kwargs: "token_5678")
    assert auth.get_kite_credentials() == ("api_1234", "token_5678")
    assert auth._ACTIVE_API_KEY == "api_1234"
    assert auth._ACTIVE_ACCESS_TOKEN == "token_5678"


def test_validate_startup_credentials_covers_token_and_secret_contracts(monkeypatch):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "", raising=False)
    with pytest.raises(RuntimeError, match="kite_api_key_missing"):
        auth.validate_kite_startup_credentials(require_access_token=False)

    monkeypatch.setattr(cfg, "KITE_API_KEY", "api", raising=False)
    assert auth.validate_kite_startup_credentials(
        require_access_token=False,
        caller_module="mutation",
    ) == {"api_key": "api", "access_token": "", "api_secret": ""}

    monkeypatch.setattr(auth, "get_kite_credentials", lambda **_kwargs: ("api", "token"))
    monkeypatch.setattr(cfg, "KITE_API_SECRET", "", raising=False)
    with pytest.raises(RuntimeError, match="kite_api_secret_missing"):
        auth.validate_kite_startup_credentials(require_api_secret=True)

    monkeypatch.setattr(cfg, "KITE_API_SECRET", "secret", raising=False)
    assert auth.validate_kite_startup_credentials(
        require_access_token=True,
        require_api_secret=True,
    ) == {"api_key": "api", "access_token": "token", "api_secret": "secret"}


def test_canonical_credentials_reject_explicit_drift(monkeypatch):
    monkeypatch.setattr(auth, "get_kite_credentials", lambda **_kwargs: ("api", "token"))
    assert auth._resolve_canonical_runtime_credentials() == ("api", "token")

    with pytest.raises(RuntimeError, match="CREDENTIAL_DRIFT_DETECTED"):
        auth._resolve_canonical_runtime_credentials(api_key="other", access_token="token")
    with pytest.raises(RuntimeError, match="CREDENTIAL_DRIFT_DETECTED"):
        auth._resolve_canonical_runtime_credentials(api_key="api", access_token="other")


def test_kite_client_construction_uses_only_canonical_credentials(monkeypatch):
    created = []

    class RawClient:
        def __init__(self, *, api_key):
            created.append(api_key)
            self.access_token = None

        def set_access_token(self, token):
            self.access_token = token

    module = _install_kite_client_module(monkeypatch, raw_client=None)
    with pytest.raises(RuntimeError, match="kiteconnect_not_installed"):
        auth.build_kite_auth_client(api_key="api")

    module._RAW_KITECONNECT = RawClient
    assert auth.build_kite_auth_client(api_key="auth_api").access_token is None

    monkeypatch.setattr(auth, "_resolve_canonical_runtime_credentials", lambda **_kwargs: ("api", "token"))
    client = auth.get_kite_client(api_key="ignored", access_token="ignored")
    assert client.access_token == "token"
    assert created == ["auth_api", "api"]


def test_kite_ticker_records_attempt_failure_and_success(monkeypatch):
    events = []
    monkeypatch.setattr(auth, "_resolve_canonical_runtime_credentials", lambda **_kwargs: ("api", "token"))
    monkeypatch.setattr(
        auth,
        "record_feed_startup_event",
        lambda event, **kwargs: events.append((event, kwargs)),
    )

    _install_depth_module(monkeypatch, None)
    with pytest.raises(RuntimeError, match="kiteconnect_not_installed"):
        auth.get_kite_ticker(debug=False)
    assert [row[0] for row in events] == [
        "KITE_TICKER_CREATE_ATTEMPTED",
        "KITE_TICKER_CREATE_FAILED",
    ]

    class BrokenTicker:
        def __init__(self, *_args, **_kwargs):
            raise ValueError("bad ticker")

    events.clear()
    _install_depth_module(monkeypatch, BrokenTicker)
    with pytest.raises(ValueError, match="bad ticker"):
        auth.get_kite_ticker()
    assert events[-1][0] == "KITE_TICKER_CREATE_FAILED"
    assert events[-1][1]["error"] == "ValueError:bad ticker"

    created = []

    class FakeTicker:
        def __init__(self, *args, **kwargs):
            created.append((args, kwargs))

    events.clear()
    _install_depth_module(monkeypatch, FakeTicker)
    ticker = auth.get_kite_ticker(debug=False)
    assert isinstance(ticker, FakeTicker)
    assert created == [
        (
            ("api", "token"),
            {
                "debug": False,
                "reconnect": True,
                "reconnect_max_tries": 300,
                "reconnect_max_delay": 60,
            },
        )
    ]
    assert events[-1][0] == "KITE_TICKER_CREATED"
    assert events[-1][1]["details"]["kite_id"] == id(ticker)


def test_lazy_feed_event_wrapper_delegates(monkeypatch):
    calls = []
    module = types.ModuleType("core.feed_startup_lifecycle")
    module.record_feed_startup_event = lambda *args, **kwargs: calls.append((args, kwargs)) or "ok"
    monkeypatch.setitem(sys.modules, "core.feed_startup_lifecycle", module)
    monkeypatch.setattr(core, "feed_startup_lifecycle", module, raising=False)

    assert auth.record_feed_startup_event("EVENT", source="mutation") == "ok"
    assert auth._record_feed_startup_event("PRIVATE", source="mutation") == "ok"
    assert calls == [
        (("EVENT",), {"source": "mutation"}),
        (("PRIVATE",), {"source": "mutation"}),
    ]


def test_token_path_and_repo_token_resolution(monkeypatch, tmp_path):
    explicit = tmp_path / "explicit.token"
    monkeypatch.setenv("TRADING_BOT_TOKEN_PATH", str(explicit))
    assert auth_manager.access_token_path(tmp_path) == explicit.resolve()
    monkeypatch.delenv("TRADING_BOT_TOKEN_PATH")

    token_path = tmp_path / ".runtime" / "kite_access_token"
    assert auth_manager.access_token_path(tmp_path) == token_path.resolve()
    assert auth_manager._read_repo_token(tmp_path) == ""

    token_path.parent.mkdir(parents=True)
    token_path.write_text(" repo-token \n", encoding="utf-8")
    calls = []
    _install_security_guard(monkeypatch, calls)
    assert auth_manager.resolve_access_token(repo_root_path=tmp_path) == "repo-token"
    assert auth_manager._CACHE["token_source"] == "repo_file"
    assert calls == [tmp_path.resolve()]


def test_env_token_requires_explicit_ci_permission(monkeypatch, tmp_path):
    _install_security_guard(monkeypatch)
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "env-token")

    with pytest.raises(RuntimeError, match="missing_kite_access_token"):
        auth_manager.resolve_access_token(repo_root_path=tmp_path)
    assert auth_manager.resolve_access_token(
        repo_root_path=tmp_path,
        require_token=False,
    ) == ""

    monkeypatch.setenv("KITE_ALLOW_ENV_TOKEN_FOR_CI", "yes")
    assert auth_manager._allow_env_token_for_ci() is True
    assert auth_manager.resolve_access_token(repo_root_path=tmp_path) == "env-token"
    assert auth_manager._CACHE["token_source"] == "env_ci"


def test_repo_token_read_failure_returns_empty(monkeypatch, tmp_path):
    token_path = tmp_path / ".runtime" / "kite_access_token"
    token_path.parent.mkdir(parents=True)
    token_path.write_text("token", encoding="utf-8")
    original = Path.read_text

    def fail(self, *args, **kwargs):
        if self == token_path.resolve():
            raise OSError("unreadable")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail)
    assert auth_manager._read_repo_token(tmp_path) == ""


def test_network_and_auth_classifiers_are_fail_closed():
    assert auth_manager._is_network_error(TimeoutError("boom")) is True
    assert auth_manager._is_network_error(RuntimeError("connection reset")) is True
    assert auth_manager._is_network_error(RuntimeError("network unavailable")) is True
    assert auth_manager._is_network_error(RuntimeError("invalid session")) is False
    assert auth_manager._is_network_error(RuntimeError("ordinary error")) is False

    assert auth_manager.is_auth_error(code=403) is True
    for text in (
        "invalid session",
        "TokenException",
        "forbidden websocket",
        "access token is invalid",
        "unauthorized",
    ):
        assert auth_manager.is_auth_error(reason_text=text) is True
    TokenException = type("TokenException", (Exception,), {})
    assert auth_manager.is_auth_error(TokenException("bad")) is True
    assert auth_manager.is_auth_error(reason_text="ordinary error") is False


def test_cache_invalidation_emits_only_when_reason_present(monkeypatch):
    events = []
    monkeypatch.setattr(auth_manager, "_append_auth_event", events.append)
    auth_manager._CACHE["token"] = "secret"
    auth_manager.invalidate_cache()
    assert auth_manager._CACHE == {}
    assert events == []

    auth_manager._CACHE["token"] = "secret"
    auth_manager.invalidate_cache("manual")
    assert events[0]["event"] == "AUTH_CACHE_INVALIDATED"
    assert events[0]["reason"] == "manual"
    assert isinstance(events[0]["ts_epoch"], float)


def test_validate_token_covers_all_authority_states(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "", raising=False)
    result = auth_manager.validate_token(repo_root_path=tmp_path)
    assert result["ok"] is False and result["error"].startswith("missing_api_key")

    monkeypatch.setattr(cfg, "KITE_API_KEY", "api", raising=False)
    monkeypatch.setattr(
        auth_manager,
        "resolve_access_token",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("missing token")),
    )
    result = auth_manager.validate_token(repo_root_path=tmp_path)
    assert result["auth_state"] == "FAILED" and result["error"] == "missing token"

    monkeypatch.setattr(auth_manager, "resolve_access_token", lambda **_kwargs: "token")

    class Client:
        def __init__(self, *, kite=None, ensure_error=None):
            self.kite = kite
            self.ensure_error = ensure_error

        def ensure(self):
            if self.ensure_error is not None:
                raise self.ensure_error
            return self.kite

    _install_kite_client_module(monkeypatch, singleton=Client(kite=None))
    result = auth_manager.validate_token(repo_root_path=tmp_path)
    assert result["error"] == "kite_client_unavailable"

    profile = SimpleNamespace(profile=lambda: {"user_name": "No Id"})
    _install_kite_client_module(monkeypatch, singleton=Client(kite=profile))
    result = auth_manager.validate_token(repo_root_path=tmp_path)
    assert result["error"] == "profile_missing_user_id"

    profile = SimpleNamespace(profile=lambda: {"user_id": "U1", "user_name": "User"})
    _install_kite_client_module(monkeypatch, singleton=Client(kite=profile))
    result = auth_manager.validate_token(repo_root_path=tmp_path)
    assert result["ok"] is True
    assert result["auth_state"] == "OK"
    assert result["user_id"] == "U1"

    TokenException = type("TokenException", (Exception,), {})
    _install_kite_client_module(
        monkeypatch,
        singleton=Client(ensure_error=TokenException("invalid")),
    )
    result = auth_manager.validate_token(repo_root_path=tmp_path)
    assert result["ok"] is False and result["auth_state"] == "AUTH_REQUIRED"

    _install_kite_client_module(
        monkeypatch,
        singleton=Client(ensure_error=TimeoutError("timed out")),
    )
    result = auth_manager.validate_token(repo_root_path=tmp_path)
    assert result["ok"] is False and result["auth_state"] == "UNKNOWN_NETWORK"

    _install_kite_client_module(
        monkeypatch,
        singleton=Client(ensure_error=RuntimeError("ordinary")),
    )
    result = auth_manager.validate_token(repo_root_path=tmp_path)
    assert result["ok"] is False and result["auth_state"] == "FAILED"


def test_auth_state_persistence_and_runtime_snapshot(monkeypatch, tmp_path):
    assert auth_manager.load_auth_state(repo_root_path=tmp_path) == {}

    required = auth_manager.set_auth_required_state(
        reason="expired",
        source="mutation",
        code=403,
        repo_root_path=tmp_path,
    )
    assert required["status"] == "AUTH_REQUIRED"
    assert auth_manager.load_auth_state(repo_root_path=tmp_path)["reason"] == "expired"

    cleared = auth_manager.clear_auth_required_state(
        source="mutation",
        repo_root_path=tmp_path,
    )
    assert cleared["status"] == "OK"

    path = auth_manager.auth_state_path(tmp_path)
    path.write_text("[]", encoding="utf-8")
    assert auth_manager.load_auth_state(repo_root_path=tmp_path) == {}
    path.write_text("{bad", encoding="utf-8")
    assert auth_manager.load_auth_state(repo_root_path=tmp_path) == {}

    freshness = types.ModuleType("core.runtime_auth_freshness")
    freshness.latest_auth_health = lambda: {"auth_state": "OK"}
    freshness.resolve_runtime_auth_snapshot = lambda state, latest_health_payload: {
        "state": state,
        "health": latest_health_payload,
    }
    monkeypatch.setitem(sys.modules, "core.runtime_auth_freshness", freshness)
    monkeypatch.setattr(core, "runtime_auth_freshness", freshness, raising=False)
    path.write_text(json.dumps({"status": "AUTH_REQUIRED"}), encoding="utf-8")
    snapshot = auth_manager.runtime_auth_snapshot(repo_root_path=tmp_path)
    assert snapshot == {
        "state": {"status": "AUTH_REQUIRED"},
        "health": {"auth_state": "OK"},
    }


def test_append_auth_event_writes_and_swallows_disk_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(auth_manager, "logs_dir", lambda: tmp_path)
    auth_manager._append_auth_event({"event": "AUTH_OK", "value": object()})
    text = (tmp_path / "auth_events.jsonl").read_text(encoding="utf-8")
    assert '"event": "AUTH_OK"' in text
    assert '"value": "<' in text

    original = Path.open

    def fail(self, *args, **kwargs):
        if self.name == "auth_events.jsonl":
            raise OSError("disk unavailable")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail)
    auth_manager._append_auth_event({"event": "IGNORED"})
