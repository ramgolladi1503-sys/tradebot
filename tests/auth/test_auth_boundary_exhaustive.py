from __future__ import annotations

from pathlib import Path

import pytest

from config import config as cfg
import core.auth as auth
import core.auth_manager as auth_manager
import core.kite_client as kite_client_module
import core.kite_depth_ws as kite_depth_ws
import core.runtime_auth_freshness as runtime_auth_freshness
import core.security_guard as security_guard


pytestmark = [pytest.mark.unit, pytest.mark.behavior, pytest.mark.safety]


@pytest.fixture(autouse=True)
def _reset_auth_state(monkeypatch):
    auth.reset_kite_runtime_credentials_guard()
    auth_manager._CACHE.clear()
    monkeypatch.delenv("TRADING_BOT_TOKEN_PATH", raising=False)
    monkeypatch.delenv("KITE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("KITE_ALLOW_ENV_TOKEN_FOR_CI", raising=False)
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    yield
    auth.reset_kite_runtime_credentials_guard()
    auth_manager._CACHE.clear()


def test_tail4_handles_empty_short_and_long_values():
    assert auth._tail4("") == ""
    assert auth._tail4("abc") == "abc"
    assert auth._tail4("abcdef") == "cdef"


def test_caller_module_name_returns_nonempty_module():
    assert auth._caller_module_name() == __name__


def test_register_runtime_credentials_accepts_same_pair_and_rejects_drift(caplog):
    caplog.set_level("INFO")
    auth._register_runtime_credentials("api_1234", "token_5678")
    auth._register_runtime_credentials("api_1234", "token_5678")

    assert "runtime_credential_guard" in caplog.text
    with pytest.raises(RuntimeError, match="CREDENTIAL_DRIFT_DETECTED"):
        auth._register_runtime_credentials("api_9999", "token_5678")


def test_get_kite_credentials_rejects_missing_api_key(monkeypatch):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "", raising=False)

    with pytest.raises(RuntimeError, match="kite_api_key_missing"):
        auth.get_kite_credentials()


def test_get_kite_credentials_rejects_empty_resolved_token(monkeypatch):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "api_1234", raising=False)
    monkeypatch.setattr(auth, "resolve_access_token", lambda **_kwargs: "")

    with pytest.raises(RuntimeError, match="kite_access_token_missing"):
        auth.get_kite_credentials()


def test_validate_startup_credentials_without_token_returns_api_key(monkeypatch):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "api_1234", raising=False)

    result = auth.validate_kite_startup_credentials(
        require_access_token=False,
        caller_module="test_startup",
    )

    assert result == {"api_key": "api_1234", "access_token": "", "api_secret": ""}


def test_validate_startup_credentials_with_token_and_secret(monkeypatch):
    monkeypatch.setattr(auth, "get_kite_credentials", lambda **_kwargs: ("api_1234", "token_5678"))
    monkeypatch.setattr(cfg, "KITE_API_SECRET", "secret_9999", raising=False)

    result = auth.validate_kite_startup_credentials(
        require_access_token=True,
        require_api_secret=True,
        caller_module="test_startup",
    )

    assert result == {
        "api_key": "api_1234",
        "access_token": "token_5678",
        "api_secret": "secret_9999",
    }


def test_resolve_canonical_credentials_rejects_explicit_api_key_drift(monkeypatch):
    monkeypatch.setattr(auth, "get_kite_credentials", lambda **_kwargs: ("canonical_api", "canonical_token"))

    with pytest.raises(RuntimeError, match="CREDENTIAL_DRIFT_DETECTED"):
        auth._resolve_canonical_runtime_credentials(
            api_key="other_api",
            access_token="canonical_token",
        )


def test_resolve_canonical_credentials_rejects_explicit_token_drift(monkeypatch):
    monkeypatch.setattr(auth, "get_kite_credentials", lambda **_kwargs: ("canonical_api", "canonical_token"))

    with pytest.raises(RuntimeError, match="CREDENTIAL_DRIFT_DETECTED"):
        auth._resolve_canonical_runtime_credentials(
            api_key="canonical_api",
            access_token="other_token",
        )


def test_resolve_canonical_credentials_accepts_omitted_explicit_values(monkeypatch):
    monkeypatch.setattr(auth, "get_kite_credentials", lambda **_kwargs: ("canonical_api", "canonical_token"))

    assert auth._resolve_canonical_runtime_credentials() == (
        "canonical_api",
        "canonical_token",
    )


def test_build_kite_auth_client_requires_installed_sdk(monkeypatch):
    monkeypatch.setattr(kite_client_module, "_RAW_KITECONNECT", None)

    with pytest.raises(RuntimeError, match="kiteconnect_not_installed"):
        auth.build_kite_auth_client(api_key="api_1234")


def test_build_kite_auth_client_constructs_raw_client(monkeypatch):
    created = []

    class RawClient:
        def __init__(self, *, api_key):
            created.append(api_key)
            self.api_key = api_key

    monkeypatch.setattr(kite_client_module, "_RAW_KITECONNECT", RawClient)

    client = auth.build_kite_auth_client(api_key="api_1234")

    assert client.api_key == "api_1234"
    assert created == ["api_1234"]


def test_get_kite_client_requires_installed_sdk(monkeypatch):
    monkeypatch.setattr(auth, "_resolve_canonical_runtime_credentials", lambda **_kwargs: ("api", "token"))
    monkeypatch.setattr(kite_client_module, "_RAW_KITECONNECT", None)

    with pytest.raises(RuntimeError, match="kiteconnect_not_installed"):
        auth.get_kite_client()


def test_get_kite_ticker_requires_installed_sdk_and_records_failure(monkeypatch):
    events = []
    monkeypatch.setattr(auth, "_resolve_canonical_runtime_credentials", lambda **_kwargs: ("api", "token"))
    monkeypatch.setattr(auth, "record_feed_startup_event", lambda event, **kwargs: events.append((event, kwargs)))
    monkeypatch.setattr(kite_depth_ws, "KiteTicker", None)

    with pytest.raises(RuntimeError, match="kiteconnect_not_installed"):
        auth.get_kite_ticker(debug=False)

    assert [event for event, _payload in events] == [
        "KITE_TICKER_CREATE_ATTEMPTED",
        "KITE_TICKER_CREATE_FAILED",
    ]
    assert events[-1][1]["error"] == "kiteconnect_not_installed"


def test_get_kite_ticker_records_constructor_failure(monkeypatch):
    events = []

    class BrokenTicker:
        def __init__(self, *_args, **_kwargs):
            raise ValueError("bad ticker")

    monkeypatch.setattr(auth, "_resolve_canonical_runtime_credentials", lambda **_kwargs: ("api", "token"))
    monkeypatch.setattr(auth, "record_feed_startup_event", lambda event, **kwargs: events.append((event, kwargs)))
    monkeypatch.setattr(kite_depth_ws, "KiteTicker", BrokenTicker)

    with pytest.raises(ValueError, match="bad ticker"):
        auth.get_kite_ticker()

    assert events[-1][0] == "KITE_TICKER_CREATE_FAILED"
    assert events[-1][1]["error"] == "ValueError:bad ticker"


def test_get_kite_ticker_constructs_reconnecting_client_and_records_success(monkeypatch):
    events = []
    created = []

    class FakeTicker:
        def __init__(self, *args, **kwargs):
            created.append((args, kwargs))

    monkeypatch.setattr(auth, "_resolve_canonical_runtime_credentials", lambda **_kwargs: ("api", "token"))
    monkeypatch.setattr(auth, "record_feed_startup_event", lambda event, **kwargs: events.append((event, kwargs)))
    monkeypatch.setattr(kite_depth_ws, "KiteTicker", FakeTicker)

    ticker = auth.get_kite_ticker(debug=False)

    assert isinstance(ticker, FakeTicker)
    args, kwargs = created[0]
    assert args == ("api", "token")
    assert kwargs == {
        "debug": False,
        "reconnect": True,
        "reconnect_max_tries": 300,
        "reconnect_max_delay": 60,
    }
    assert events[-1][0] == "KITE_TICKER_CREATED"
    assert events[-1][1]["details"]["kite_id"] == id(ticker)


def test_read_repo_token_handles_missing_file_and_read_error(monkeypatch, tmp_path):
    assert auth_manager._read_repo_token(tmp_path) == ""

    token_path = tmp_path / ".runtime" / "kite_access_token"
    token_path.parent.mkdir(parents=True)
    token_path.write_text("token", encoding="utf-8")
    original_read_text = Path.read_text

    def broken_read_text(self, *args, **kwargs):
        if self == token_path.resolve():
            raise OSError("unreadable")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", broken_read_text)
    assert auth_manager._read_repo_token(tmp_path) == ""


def test_resolve_access_token_enforces_repository_artifact_guard(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        security_guard,
        "enforce_no_repo_token_artifacts",
        lambda root: calls.append(Path(root).resolve()),
    )
    token_path = tmp_path / ".runtime" / "kite_access_token"
    token_path.parent.mkdir(parents=True)
    token_path.write_text("token_1234", encoding="utf-8")

    resolved = auth_manager.resolve_access_token(repo_root_path=tmp_path)

    assert resolved == "token_1234"
    assert calls == [tmp_path.resolve()]


@pytest.mark.parametrize(
    "exc",
    [
        type("RequestFailure", (Exception,), {})("boom"),
        RuntimeError("network unavailable"),
        RuntimeError("connection reset"),
    ],
)
def test_network_error_classifier_covers_name_and_message_signals(exc):
    assert auth_manager._is_network_error(exc) is True


def test_auth_error_classifier_uses_reason_text_without_exception():
    assert auth_manager.is_auth_error(reason_text="access token is invalid") is True
    assert auth_manager.is_auth_error(reason_text="ordinary broker error") is False


def test_invalidate_cache_without_reason_does_not_emit_event(monkeypatch):
    events = []
    auth_manager._CACHE["token"] = "secret"
    monkeypatch.setattr(auth_manager, "_append_auth_event", events.append)

    auth_manager.invalidate_cache()

    assert auth_manager._CACHE == {}
    assert events == []


def test_invalidate_cache_with_reason_emits_audit_event(monkeypatch):
    events = []
    auth_manager._CACHE["token"] = "secret"
    monkeypatch.setattr(auth_manager, "_append_auth_event", events.append)

    auth_manager.invalidate_cache("manual_reset")

    assert auth_manager._CACHE == {}
    assert events[0]["event"] == "AUTH_CACHE_INVALIDATED"
    assert events[0]["reason"] == "manual_reset"
    assert isinstance(events[0]["ts_epoch"], float)


def test_validate_token_uses_config_api_key_when_environment_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "config_api", raising=False)
    monkeypatch.setattr(auth_manager, "resolve_access_token", lambda **_kwargs: "token")

    class ProfileClient:
        def profile(self):
            return {"user_id": "U1", "user_name": "Config User"}

    client = ProfileClient()
    monkeypatch.setattr(kite_client_module.kite_client, "ensure", lambda: client)
    monkeypatch.setattr(kite_client_module.kite_client, "kite", client, raising=False)

    result = auth_manager.validate_token(repo_root_path=tmp_path, force=False)

    assert result["auth_state"] == "OK"
    assert result["user_id"] == "U1"


def test_auth_state_path_and_missing_state_are_safe(tmp_path):
    expected = (tmp_path / ".runtime" / "auth_state.json").resolve()
    assert auth_manager.auth_state_path(tmp_path) == expected
    assert auth_manager.load_auth_state(repo_root_path=tmp_path) == {}


def test_runtime_auth_snapshot_delegates_to_freshness_resolver(monkeypatch, tmp_path):
    stored = {"status": "AUTH_REQUIRED"}
    health = {"auth_state": "OK"}
    calls = []
    monkeypatch.setattr(auth_manager, "load_auth_state", lambda **_kwargs: stored)
    monkeypatch.setattr(runtime_auth_freshness, "latest_auth_health", lambda: health)
    monkeypatch.setattr(
        runtime_auth_freshness,
        "resolve_runtime_auth_snapshot",
        lambda state, latest_health_payload: calls.append((state, latest_health_payload)) or {"resolved": True},
    )

    result = auth_manager.runtime_auth_snapshot(repo_root_path=tmp_path)

    assert result == {"resolved": True}
    assert calls == [(stored, health)]


def test_append_auth_event_writes_json_line(monkeypatch, tmp_path):
    monkeypatch.setattr(auth_manager, "logs_dir", lambda: tmp_path)

    auth_manager._append_auth_event({"event": "AUTH_OK", "value": object()})

    text = (tmp_path / "auth_events.jsonl").read_text(encoding="utf-8")
    assert '"event": "AUTH_OK"' in text
    assert '"value": "<' in text


def test_append_auth_event_swallows_open_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(auth_manager, "logs_dir", lambda: tmp_path)
    original_open = Path.open

    def broken_open(self, *args, **kwargs):
        if self.name == "auth_events.jsonl":
            raise OSError("disk unavailable")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", broken_open)

    auth_manager._append_auth_event({"event": "AUTH_OK"})

    assert not (tmp_path / "auth_events.jsonl").exists()
