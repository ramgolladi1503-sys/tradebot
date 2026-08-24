from __future__ import annotations

import logging

import pytest

from config import config as cfg
import core.auth as auth


def test_get_credentials_accepts_governed_environment_api_key(monkeypatch):
    monkeypatch.setenv("KITE_API_KEY", "synthetic-env-key")
    monkeypatch.setattr(cfg, "KITE_API_KEY", "synthetic-config-key", raising=False)
    monkeypatch.setattr(auth, "_governed_launchctl_value", lambda _name: "synthetic-launchd-key")
    monkeypatch.setattr(auth, "resolve_access_token", lambda **_kwargs: "synthetic-token")
    auth.reset_kite_runtime_credentials_guard()

    api_key, token = auth.get_kite_credentials()

    assert api_key == "synthetic-env-key"
    assert token == "synthetic-token"


def test_validate_credentials_accepts_governed_environment_api_secret(monkeypatch):
    monkeypatch.setenv("KITE_API_KEY", "synthetic-env-key")
    monkeypatch.setenv("KITE_API_SECRET", "synthetic-env-secret")
    monkeypatch.setattr(cfg, "KITE_API_KEY", "", raising=False)
    monkeypatch.setattr(cfg, "KITE_API_SECRET", "", raising=False)

    result = auth.validate_kite_startup_credentials(
        require_access_token=False, require_api_secret=True, caller_module=__name__
    )

    assert result["api_key"] == "synthetic-env-key"
    assert result["api_secret"] == "synthetic-env-secret"


def test_empty_governed_environment_values_fall_back_deterministically(monkeypatch):
    monkeypatch.setenv("KITE_API_KEY", "   ")
    monkeypatch.setattr(cfg, "KITE_API_KEY", "synthetic-config-key", raising=False)
    monkeypatch.setattr(auth, "_governed_launchctl_value", lambda _name: "synthetic-launchd-key")
    monkeypatch.setattr(auth, "resolve_access_token", lambda **_kwargs: "synthetic-token")
    auth.reset_kite_runtime_credentials_guard()

    api_key, _token = auth.get_kite_credentials()

    assert api_key == "synthetic-config-key"


def test_missing_all_api_key_sources_fails_closed(monkeypatch):
    monkeypatch.setenv("KITE_API_KEY", "")
    monkeypatch.setattr(cfg, "KITE_API_KEY", "", raising=False)
    monkeypatch.setattr(auth, "_governed_launchctl_value", lambda _name: "")

    with pytest.raises(RuntimeError, match="kite_api_key_missing"):
        auth.validate_kite_startup_credentials(require_access_token=False, caller_module=__name__)


def test_credential_values_are_not_logged(monkeypatch, caplog):
    monkeypatch.setenv("KITE_API_KEY", "synthetic-env-key")
    monkeypatch.setattr(auth, "resolve_access_token", lambda **_kwargs: "synthetic-token")
    auth.reset_kite_runtime_credentials_guard()

    with caplog.at_level(logging.INFO):
        auth.get_kite_credentials()

    rendered = caplog.text
    assert "synthetic-env-key" not in rendered
    assert "synthetic-token" not in rendered
