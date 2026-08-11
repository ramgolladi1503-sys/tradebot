from __future__ import annotations

from pathlib import Path

import pytest

from config import config as cfg
import core.auth_manager as auth_manager
import core.kite_client as kite_client_module


pytestmark = [pytest.mark.unit, pytest.mark.behavior, pytest.mark.safety]


@pytest.fixture(autouse=True)
def _reset_auth_state(monkeypatch):
    auth_manager._CACHE.clear()
    monkeypatch.delenv("TRADING_BOT_TOKEN_PATH", raising=False)
    monkeypatch.delenv("KITE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("KITE_ALLOW_ENV_TOKEN_FOR_CI", raising=False)
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    yield
    auth_manager._CACHE.clear()


def _write_repo_token(root: Path, token: str) -> Path:
    path = root / ".runtime" / "kite_access_token"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8")
    return path


class _ProfileKite:
    def __init__(self, result=None, error: Exception | None = None):
        self._result = result
        self._error = error

    def profile(self):
        if self._error is not None:
            raise self._error
        return self._result


def _install_profile_client(monkeypatch, kite) -> None:
    monkeypatch.setattr(kite_client_module.kite_client, "ensure", lambda: kite)
    monkeypatch.setattr(kite_client_module.kite_client, "kite", kite, raising=False)


def test_repo_token_precedes_ci_environment_token(monkeypatch, tmp_path):
    _write_repo_token(tmp_path, "repo_token_1234\n")
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "env_token_9999")
    monkeypatch.setenv("KITE_ALLOW_ENV_TOKEN_FOR_CI", "true")

    resolved = auth_manager.resolve_access_token(
        repo_root_path=tmp_path,
        enforce_artifact_check=False,
    )

    assert resolved == "repo_token_1234"
    assert auth_manager._CACHE["token_source"] == "repo_file"


def test_environment_token_requires_explicit_ci_override(monkeypatch, tmp_path):
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "env_token_must_not_be_used")

    resolved = auth_manager.resolve_access_token(
        repo_root_path=tmp_path,
        require_token=False,
        enforce_artifact_check=False,
    )

    assert resolved == ""
    assert "token" not in auth_manager._CACHE


def test_missing_required_token_fails_closed(tmp_path):
    with pytest.raises(RuntimeError, match="missing_kite_access_token"):
        auth_manager.resolve_access_token(
            repo_root_path=tmp_path,
            require_token=True,
            enforce_artifact_check=False,
        )


def test_invalid_session_is_auth_failure_not_network_success():
    error = RuntimeError("connection invalid session")
    assert auth_manager.is_auth_error(error) is True
    assert auth_manager._is_network_error(error) is False


def test_network_classifier_accepts_explicit_network_failures():
    assert auth_manager._is_network_error(TimeoutError("timed out")) is True
    assert auth_manager._is_network_error(ConnectionError("connection reset")) is True
    assert auth_manager._is_network_error(RuntimeError("network unavailable")) is True


def test_validate_token_verified_profile_returns_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("KITE_API_KEY", "api_key_1234")
    monkeypatch.setattr(auth_manager, "resolve_access_token", lambda **_kwargs: "token_5678")
    _install_profile_client(
        monkeypatch,
        _ProfileKite({"user_id": "LLL209", "user_name": "Ram"}),
    )

    result = auth_manager.validate_token(repo_root_path=tmp_path)

    assert result["ok"] is True
    assert result["auth_state"] == "OK"
    assert result["user_id"] == "LLL209"
    assert result["user_name"] == "Ram"


def test_validate_token_missing_api_key_fails_before_token_resolution(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "", raising=False)
    called = {"resolve": False}

    def _unexpected_resolve(**_kwargs):
        called["resolve"] = True
        raise AssertionError("token resolution must not run without API key")

    monkeypatch.setattr(auth_manager, "resolve_access_token", _unexpected_resolve)

    result = auth_manager.validate_token(repo_root_path=tmp_path)

    assert result["ok"] is False
    assert result["auth_state"] == "FAILED"
    assert result["error"] == "missing_api_key:KITE_API_KEY"
    assert called["resolve"] is False


def test_validate_token_network_failure_is_unknown_and_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("KITE_API_KEY", "api_key_1234")
    monkeypatch.setattr(auth_manager, "resolve_access_token", lambda **_kwargs: "token_5678")
    _install_profile_client(monkeypatch, _ProfileKite(error=TimeoutError("timed out")))

    result = auth_manager.validate_token(repo_root_path=tmp_path)

    assert result["ok"] is False
    assert result["auth_state"] == "UNKNOWN_NETWORK"
    assert result["error"] == "profile_error:TimeoutError"


def test_validate_token_invalid_session_requires_auth_and_clears_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("KITE_API_KEY", "api_key_1234")
    monkeypatch.setattr(auth_manager, "resolve_access_token", lambda **_kwargs: "token_5678")
    monkeypatch.setattr(auth_manager, "_append_auth_event", lambda _payload: None)
    auth_manager._CACHE.update({"token": "token_5678", "token_source": "repo_file"})
    _install_profile_client(
        monkeypatch,
        _ProfileKite(error=RuntimeError("TokenException: invalid session")),
    )

    result = auth_manager.validate_token(repo_root_path=tmp_path)

    assert result["ok"] is False
    assert result["auth_state"] == "AUTH_REQUIRED"
    assert auth_manager._CACHE == {}


def test_validate_token_unclassified_profile_failure_remains_failed(monkeypatch, tmp_path):
    monkeypatch.setenv("KITE_API_KEY", "api_key_1234")
    monkeypatch.setattr(auth_manager, "resolve_access_token", lambda **_kwargs: "token_5678")
    _install_profile_client(monkeypatch, _ProfileKite(error=ValueError("bad payload")))

    result = auth_manager.validate_token(repo_root_path=tmp_path)

    assert result["ok"] is False
    assert result["auth_state"] == "FAILED"
    assert result["error"] == "profile_error:ValueError:bad payload"
