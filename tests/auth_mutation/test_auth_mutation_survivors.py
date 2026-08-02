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
def _reset(monkeypatch):
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


def _install_module(monkeypatch, name: str, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(core, name.rsplit(".", 1)[-1], module, raising=False)
    return module


def test_tail_and_caller_boundaries(monkeypatch):
    assert auth._tail4("abcd") == "abcd"
    assert auth._tail4("abcde") == "bcde"

    target = SimpleNamespace(f_globals={"__name__": "owner.module"}, f_back=None)
    logging_frame = SimpleNamespace(f_globals={"__name__": "logging"}, f_back=target)
    auth_frame = SimpleNamespace(f_globals={"__name__": auth.__name__}, f_back=logging_frame)
    entry = SimpleNamespace(f_globals={}, f_back=auth_frame)
    monkeypatch.setattr(auth, "inspect", SimpleNamespace(currentframe=lambda: entry))
    assert auth._caller_module_name() == "owner.module"


def test_reset_and_partial_credential_state_are_fail_closed():
    auth._ACTIVE_API_KEY = "api"
    auth._ACTIVE_ACCESS_TOKEN = "token"
    auth.reset_kite_runtime_credentials_guard()
    assert auth._ACTIVE_API_KEY == ""
    assert auth._ACTIVE_ACCESS_TOKEN == ""

    auth._ACTIVE_API_KEY = "api"
    auth._ACTIVE_ACCESS_TOKEN = ""
    with pytest.raises(RuntimeError) as exc_info:
        auth._register_runtime_credentials("api", "token")
    assert exc_info.value.args == ("CREDENTIAL_DRIFT_DETECTED",)
    assert auth._ACTIVE_API_KEY == "api"
    assert auth._ACTIVE_ACCESS_TOKEN == ""


def test_credential_registration_normalizes_and_detects_each_drift_dimension():
    auth._register_runtime_credentials(" api ", " token ")
    assert auth._ACTIVE_API_KEY == "api"
    assert auth._ACTIVE_ACCESS_TOKEN == "token"

    auth._register_runtime_credentials("api", "token")
    with pytest.raises(RuntimeError) as api_exc:
        auth._register_runtime_credentials("other", "token")
    assert api_exc.value.args == ("CREDENTIAL_DRIFT_DETECTED",)
    with pytest.raises(RuntimeError) as token_exc:
        auth._register_runtime_credentials("api", "other")
    assert token_exc.value.args == ("CREDENTIAL_DRIFT_DETECTED",)


def test_get_credentials_forwards_root_and_requires_token(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cfg, "KITE_API_KEY", " api ", raising=False)

    def resolve(**kwargs):
        calls.append(kwargs)
        return " token "

    monkeypatch.setattr(auth, "resolve_access_token", resolve)
    assert auth.get_kite_credentials(repo_root_path=tmp_path) == ("api", "token")
    assert calls == [{"repo_root_path": tmp_path, "require_token": True}]

    monkeypatch.setattr(cfg, "KITE_API_KEY", "", raising=False)
    with pytest.raises(RuntimeError) as missing_api:
        auth.get_kite_credentials()
    assert missing_api.value.args == ("kite_api_key_missing",)

    monkeypatch.setattr(cfg, "KITE_API_KEY", "api", raising=False)
    monkeypatch.setattr(auth, "resolve_access_token", lambda **_kwargs: "")
    with pytest.raises(RuntimeError) as missing_token:
        auth.get_kite_credentials()
    assert missing_token.value.args == ("kite_access_token_missing",)


def test_startup_validation_defaults_and_exact_secret_failure(monkeypatch, tmp_path):
    calls = []

    def credentials(**kwargs):
        calls.append(kwargs)
        return "api", "token"

    monkeypatch.setattr(auth, "get_kite_credentials", credentials)
    monkeypatch.setattr(cfg, "KITE_API_SECRET", "", raising=False)

    assert auth.validate_kite_startup_credentials(repo_root_path=tmp_path) == {
        "api_key": "api",
        "access_token": "token",
        "api_secret": "",
    }
    assert calls == [{"repo_root_path": tmp_path}]

    with pytest.raises(RuntimeError) as exc_info:
        auth.validate_kite_startup_credentials(require_api_secret=True)
    assert exc_info.value.args == ("kite_api_secret_missing",)


def test_canonical_resolution_forwards_root_normalizes_and_has_exact_errors(monkeypatch, tmp_path):
    calls = []

    def credentials(**kwargs):
        calls.append(kwargs)
        return "api", "token"

    monkeypatch.setattr(auth, "get_kite_credentials", credentials)
    assert auth._resolve_canonical_runtime_credentials(
        api_key=" api ", access_token=" token ", repo_root_path=tmp_path
    ) == ("api", "token")
    assert calls == [{"repo_root_path": tmp_path}]

    with pytest.raises(RuntimeError) as api_exc:
        auth._resolve_canonical_runtime_credentials(api_key="other")
    assert api_exc.value.args == ("CREDENTIAL_DRIFT_DETECTED",)
    with pytest.raises(RuntimeError) as token_exc:
        auth._resolve_canonical_runtime_credentials(access_token="other")
    assert token_exc.value.args == ("CREDENTIAL_DRIFT_DETECTED",)


def test_client_and_ticker_forward_every_security_parameter(monkeypatch, tmp_path):
    resolved_calls = []

    def resolve(**kwargs):
        resolved_calls.append(kwargs)
        return "api", "token"

    monkeypatch.setattr(auth, "_resolve_canonical_runtime_credentials", resolve)

    class Client:
        def __init__(self, *, api_key):
            self.api_key = api_key
            self.token = None

        def set_access_token(self, token):
            self.token = token

    _install_module(monkeypatch, "core.kite_client", _RAW_KITECONNECT=Client)
    client = auth.get_kite_client(
        api_key="requested-api", access_token="requested-token", repo_root_path=tmp_path
    )
    assert (client.api_key, client.token) == ("api", "token")
    assert resolved_calls[-1] == {
        "api_key": "requested-api",
        "access_token": "requested-token",
        "repo_root_path": tmp_path,
    }

    events = []
    monkeypatch.setattr(
        auth,
        "record_feed_startup_event",
        lambda event, **kwargs: events.append((event, kwargs)),
    )
    ticker_calls = []

    class Ticker:
        def __init__(self, *args, **kwargs):
            ticker_calls.append((args, kwargs))

    _install_module(monkeypatch, "core.kite_depth_ws", KiteTicker=Ticker)
    ticker = auth.get_kite_ticker(
        api_key="requested-api",
        access_token="requested-token",
        debug=False,
        repo_root_path=tmp_path,
    )
    assert isinstance(ticker, Ticker)
    assert resolved_calls[-1] == {
        "api_key": "requested-api",
        "access_token": "requested-token",
        "repo_root_path": tmp_path,
    }
    assert ticker_calls == [
        (("api", "token"), {
            "debug": False,
            "reconnect": True,
            "reconnect_max_tries": 300,
            "reconnect_max_delay": 60,
        })
    ]
    assert events[0] == (
        "KITE_TICKER_CREATE_ATTEMPTED",
        {
            "source": "core.auth.get_kite_ticker",
            "details": {
                "api_key_present": True,
                "api_key_tail4": "api",
                "access_token_present": True,
                "access_token_len": 5,
                "access_token_tail4": "oken",
                "debug": False,
            },
        },
    )
    assert events[-1][0] == "KITE_TICKER_CREATED"
    assert events[-1][1]["source"] == "core.auth.get_kite_ticker"
    assert events[-1][1]["details"] == {"kite_id": id(ticker)}


def test_missing_raw_clients_raise_exact_errors(monkeypatch):
    _install_module(monkeypatch, "core.kite_client", _RAW_KITECONNECT=None)
    with pytest.raises(RuntimeError) as auth_client_exc:
        auth.build_kite_auth_client(api_key="api")
    assert auth_client_exc.value.args == ("kiteconnect_not_installed",)

    monkeypatch.setattr(auth, "_resolve_canonical_runtime_credentials", lambda **_kwargs: ("api", "token"))
    with pytest.raises(RuntimeError) as client_exc:
        auth.get_kite_client()
    assert client_exc.value.args == ("kiteconnect_not_installed",)


def test_env_token_switch_accepts_only_documented_truthy_values(monkeypatch):
    for value in ("1", "true", "TRUE", " yes ", "on", "ON"):
        monkeypatch.setenv("KITE_ALLOW_ENV_TOKEN_FOR_CI", value)
        assert auth_manager._allow_env_token_for_ci() is True
    for value in ("", "0", "false", "no", "off", "unexpected"):
        monkeypatch.setenv("KITE_ALLOW_ENV_TOKEN_FOR_CI", value)
        assert auth_manager._allow_env_token_for_ci() is False
    monkeypatch.delenv("KITE_ALLOW_ENV_TOKEN_FOR_CI", raising=False)
    assert auth_manager._allow_env_token_for_ci() is False


def test_token_resolution_enforces_artifact_check_and_records_exact_cache(monkeypatch, tmp_path):
    checks = []
    _install_module(
        monkeypatch,
        "core.security_guard",
        enforce_no_repo_token_artifacts=lambda root: checks.append(Path(root).resolve()),
    )
    monkeypatch.setattr(auth_manager.time, "time", lambda: 123.5)
    token_path = tmp_path / ".runtime" / "kite_access_token"
    token_path.parent.mkdir(parents=True)
    token_path.write_text(" repo-token \n", encoding="utf-8")

    assert auth_manager.resolve_access_token(repo_root_path=tmp_path) == "repo-token"
    assert checks == [tmp_path.resolve()]
    assert auth_manager._CACHE == {
        "token": "repo-token",
        "token_source": "repo_file",
        "ts_epoch": 123.5,
    }

    checks.clear()
    auth_manager._CACHE.clear()
    assert auth_manager.resolve_access_token(
        repo_root_path=tmp_path, enforce_artifact_check=False
    ) == "repo-token"
    assert checks == []


def test_missing_token_error_is_exact_and_optional_mode_is_empty(monkeypatch, tmp_path):
    _install_module(
        monkeypatch,
        "core.security_guard",
        enforce_no_repo_token_artifacts=lambda _root: None,
    )
    expected_path = (tmp_path / ".runtime" / "kite_access_token").resolve()
    with pytest.raises(RuntimeError) as exc_info:
        auth_manager.resolve_access_token(repo_root_path=tmp_path)
    assert exc_info.value.args == (
        "[AUTH] missing_kite_access_token\n"
        f"Missing token at {expected_path}\n"
        "Run scripts/kite_autologin_localhost.py to refresh token.",
    )
    assert auth_manager.resolve_access_token(
        repo_root_path=tmp_path, require_token=False
    ) == ""


def test_auth_and_network_classifiers_cover_each_keyword_and_class():
    for exc in (
        TimeoutError("x"),
        type("ConnectionProblem", (Exception,), {})("x"),
        type("NetworkProblem", (Exception,), {})("x"),
        type("RequestProblem", (Exception,), {})("x"),
        RuntimeError("timed out"),
        RuntimeError("connection lost"),
        RuntimeError("network down"),
    ):
        assert auth_manager._is_network_error(exc) is True
    assert auth_manager._is_network_error(RuntimeError("invalid session connection")) is False
    assert auth_manager._is_network_error(RuntimeError("ordinary")) is False

    assert auth_manager.is_auth_error(code=403) is True
    assert auth_manager.is_auth_error(code=401) is False
    for text in (
        "invalid session",
        "tokenexception",
        "forbidden websocket",
        "access token is invalid",
        "unauthorized",
    ):
        assert auth_manager.is_auth_error(reason_text=text) is True
    for name in ("TokenException", "PermissionException", "AuthenticationError"):
        exc = type(name, (Exception,), {})("ordinary")
        assert auth_manager.is_auth_error(exc) is True
    assert auth_manager.is_auth_error(RuntimeError("ordinary")) is False


def test_state_payloads_and_events_are_exact(monkeypatch, tmp_path):
    events = []
    monkeypatch.setattr(auth_manager.time, "time", lambda: 77.0)
    monkeypatch.setattr(auth_manager, "_append_auth_event", events.append)

    required = auth_manager.set_auth_required_state(
        reason="expired", source="ws", code=403, repo_root_path=tmp_path
    )
    assert required == {
        "status": "AUTH_REQUIRED",
        "reason": "expired",
        "source": "ws",
        "code": 403,
        "ts_epoch": 77.0,
    }
    assert events[-1] == {"event": "AUTH_REQUIRED", **required}
    assert json.loads(auth_manager.auth_state_path(tmp_path).read_text()) == required

    cleared = auth_manager.clear_auth_required_state(source="manual", repo_root_path=tmp_path)
    assert cleared == {
        "status": "OK",
        "reason": "",
        "source": "manual",
        "ts_epoch": 77.0,
    }
    assert events[-1] == {"event": "AUTH_OK", **cleared}


def test_validate_token_returns_exact_authority_payloads(monkeypatch, tmp_path):
    monkeypatch.setattr(auth_manager.time, "time", lambda: 99.0)
    monkeypatch.setenv("KITE_API_KEY", "api")
    monkeypatch.setattr(auth_manager, "resolve_access_token", lambda **_kwargs: "token")

    class Client:
        def __init__(self, kite=None, error=None):
            self.kite = kite
            self.error = error

        def ensure(self):
            if self.error:
                raise self.error

    profile = SimpleNamespace(profile=lambda: {"user_id": "U1", "user_name": "User"})
    _install_module(monkeypatch, "core.kite_client", kite_client=Client(kite=profile))
    assert auth_manager.validate_token(repo_root_path=tmp_path) == {
        "ok": True,
        "auth_state": "OK",
        "error": "",
        "ts_epoch": 99.0,
        "user_id": "U1",
        "user_name": "User",
    }

    TokenException = type("TokenException", (Exception,), {})
    events = []
    monkeypatch.setattr(auth_manager, "_append_auth_event", events.append)
    _install_module(
        monkeypatch,
        "core.kite_client",
        kite_client=Client(error=TokenException("expired")),
    )
    assert auth_manager.validate_token(repo_root_path=tmp_path) == {
        "ok": False,
        "auth_state": "AUTH_REQUIRED",
        "error": "profile_error:TokenException:expired",
        "ts_epoch": 99.0,
    }
    assert events == [
        {
            "event": "AUTH_CACHE_INVALIDATED",
            "reason": "profile_auth_error:TokenException",
            "ts_epoch": 99.0,
        }
    ]

    _install_module(
        monkeypatch,
        "core.kite_client",
        kite_client=Client(error=TimeoutError("slow")),
    )
    assert auth_manager.validate_token(repo_root_path=tmp_path) == {
        "ok": False,
        "auth_state": "UNKNOWN_NETWORK",
        "error": "profile_error:TimeoutError",
        "ts_epoch": 99.0,
    }
