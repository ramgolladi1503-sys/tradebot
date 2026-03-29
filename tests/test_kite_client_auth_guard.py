import pytest

from config import config as cfg
import core.auth as auth_module
from core.auth import get_kite_client, reset_kite_runtime_credentials_guard, validate_kite_startup_credentials
import core.kite_client as kite_client_mod
from core.kite_client import kite_client


class _FakeKite:
    def historical_data(self, **_kwargs):
        raise Exception("TokenException: invalid session")


def test_historical_auth_error_raises_runtime_error(monkeypatch):
    fake = _FakeKite()
    monkeypatch.setattr(kite_client, "ensure", lambda: fake)
    monkeypatch.setattr(kite_client, "_is_historical_auth_error", lambda exc: True)

    with pytest.raises(RuntimeError, match="Kite auth failed"):
        kite_client.historical(
            instrument_token=123,
            from_date="2026-03-27",
            to_date="2026-03-27",
            interval="minute",
        )


def test_ensure_uses_canonical_file_token_and_recreates_client(monkeypatch):
    reset_kite_runtime_credentials_guard()
    created = []

    def _create_kite(api_key, access_token):
        client = object()
        created.append((api_key, access_token, client))
        return client

    monkeypatch.setattr(cfg, "KITE_API_KEY", "api_key_1234", raising=False)
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "env_token_should_be_ignored")
    monkeypatch.setattr(auth_module, "resolve_access_token", lambda **kwargs: "file_token_5678")
    monkeypatch.setattr(kite_client, "_create_kite", _create_kite)
    monkeypatch.setattr(kite_client, "kite", None, raising=False)

    first = kite_client.ensure()
    second = kite_client.ensure()

    assert len(created) == 2
    assert created[0][0] == "api_key_1234"
    assert created[0][1] == "file_token_5678"
    assert created[1][1] == "file_token_5678"
    assert first is not second
    assert kite_client._active_access_token == "file_token_5678"


def test_get_kite_client_raises_on_runtime_token_mismatch(monkeypatch):
    reset_kite_runtime_credentials_guard()

    class _RawKite:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.access_token = None

        def set_access_token(self, token):
            self.access_token = token

    monkeypatch.setattr(cfg, "KITE_API_KEY", "api_key_1234", raising=False)
    tokens = iter(["token_one_1234", "token_two_5678"])
    monkeypatch.setattr(auth_module, "resolve_access_token", lambda **kwargs: next(tokens))
    monkeypatch.setattr(kite_client_mod, "_RAW_KITECONNECT", _RawKite)
    monkeypatch.setattr(kite_client, "kite", object(), raising=False)

    client = get_kite_client()
    assert client.access_token == "token_one_1234"

    with pytest.raises(RuntimeError, match="CREDENTIAL_DRIFT_DETECTED"):
        get_kite_client()


def test_get_kite_client_rejects_explicit_credentials_outside_canonical_source(monkeypatch):
    reset_kite_runtime_credentials_guard()

    class _RawKite:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.access_token = None

        def set_access_token(self, token):
            self.access_token = token

    monkeypatch.setattr(cfg, "KITE_API_KEY", "api_key_1234", raising=False)
    monkeypatch.setattr(auth_module, "resolve_access_token", lambda **kwargs: "token_file_5678")
    monkeypatch.setattr(kite_client_mod, "_RAW_KITECONNECT", _RawKite)

    with pytest.raises(RuntimeError, match="CREDENTIAL_DRIFT_DETECTED"):
        get_kite_client(api_key="api_key_1234", access_token="token_other_9999")


def test_get_kite_client_logs_active_credentials_with_caller_module(monkeypatch, caplog):
    reset_kite_runtime_credentials_guard()

    class _RawKite:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.access_token = None

        def set_access_token(self, token):
            self.access_token = token

    monkeypatch.setattr(cfg, "KITE_API_KEY", "api_key_1234", raising=False)
    monkeypatch.setattr(auth_module, "resolve_access_token", lambda **kwargs: "token_file_5678")
    monkeypatch.setattr(kite_client_mod, "_RAW_KITECONNECT", _RawKite)

    caplog.set_level("INFO")
    client = get_kite_client()

    assert client.access_token == "token_file_5678"
    assert "runtime_credential_guard" in caplog.text
    assert f"caller_module={__name__}" in caplog.text
    assert "kite_client_initialized" in caplog.text


def test_validate_kite_startup_credentials_requires_api_key(monkeypatch):
    reset_kite_runtime_credentials_guard()
    monkeypatch.setattr(cfg, "KITE_API_KEY", "", raising=False)

    with pytest.raises(RuntimeError, match="kite_api_key_missing"):
        validate_kite_startup_credentials(require_access_token=False, caller_module=__name__)


def test_validate_kite_startup_credentials_requires_api_secret_when_requested(monkeypatch):
    reset_kite_runtime_credentials_guard()
    monkeypatch.setattr(cfg, "KITE_API_KEY", "api_key_1234", raising=False)
    monkeypatch.setattr(cfg, "KITE_API_SECRET", "", raising=False)

    with pytest.raises(RuntimeError, match="kite_api_secret_missing"):
        validate_kite_startup_credentials(
            require_access_token=False,
            require_api_secret=True,
            caller_module=__name__,
        )
