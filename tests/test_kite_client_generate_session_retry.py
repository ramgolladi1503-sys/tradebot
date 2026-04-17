from __future__ import annotations

import pytest

from config import config as cfg
import core.kite_client as kite_client_module
from core.kite_client import KiteClient


class _FakeAuthKite:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.set_access_token_calls = []

    def generate_session(self, request_token, api_secret=None):
        _ = request_token
        _ = api_secret
        self.calls += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return dict(item)

    def set_access_token(self, token):
        self.set_access_token_calls.append(str(token))


def test_generate_session_retries_once_on_timeout_then_succeeds(monkeypatch):
    fake = _FakeAuthKite(
        [
            TimeoutError("handshake timed out"),
            {"access_token": "token_1234"},
        ]
    )
    client = KiteClient()
    monkeypatch.setattr(kite_client_module, "_RAW_KITECONNECT", object())
    monkeypatch.setattr(client, "_create_kite_for_auth", lambda api_key=None: fake)
    monkeypatch.setattr(cfg, "KITE_GENERATE_SESSION_RETRY_ATTEMPTS", 3, raising=False)
    monkeypatch.setattr(cfg, "KITE_GENERATE_SESSION_RETRY_BACKOFF_SEC", 0.0, raising=False)
    monkeypatch.setattr(kite_client_module.time, "sleep", lambda _secs: None)

    result = client.generate_session("request_token", "api_secret", api_key="api_key_1234")

    assert result.get("access_token") == "token_1234"
    assert fake.calls == 2
    assert fake.set_access_token_calls == ["token_1234"]


def test_generate_session_does_not_retry_token_exception(monkeypatch):
    fake = _FakeAuthKite([RuntimeError("TokenException: invalid session")])
    client = KiteClient()
    monkeypatch.setattr(kite_client_module, "_RAW_KITECONNECT", object())
    monkeypatch.setattr(client, "_create_kite_for_auth", lambda api_key=None: fake)
    monkeypatch.setattr(cfg, "KITE_GENERATE_SESSION_RETRY_ATTEMPTS", 3, raising=False)
    monkeypatch.setattr(cfg, "KITE_GENERATE_SESSION_RETRY_BACKOFF_SEC", 0.0, raising=False)
    monkeypatch.setattr(kite_client_module.time, "sleep", lambda _secs: None)

    with pytest.raises(RuntimeError, match="TokenException"):
        client.generate_session("request_token", "api_secret", api_key="api_key_1234")
    assert fake.calls == 1


def test_generate_session_raises_after_retry_budget_exhausted(monkeypatch):
    fake = _FakeAuthKite(
        [
            TimeoutError("read timeout"),
            TimeoutError("read timeout"),
        ]
    )
    client = KiteClient()
    monkeypatch.setattr(kite_client_module, "_RAW_KITECONNECT", object())
    monkeypatch.setattr(client, "_create_kite_for_auth", lambda api_key=None: fake)
    monkeypatch.setattr(cfg, "KITE_GENERATE_SESSION_RETRY_ATTEMPTS", 2, raising=False)
    monkeypatch.setattr(cfg, "KITE_GENERATE_SESSION_RETRY_BACKOFF_SEC", 0.0, raising=False)
    monkeypatch.setattr(kite_client_module.time, "sleep", lambda _secs: None)

    with pytest.raises(TimeoutError):
        client.generate_session("request_token", "api_secret", api_key="api_key_1234")
    assert fake.calls == 2

