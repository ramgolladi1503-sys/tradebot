from __future__ import annotations

import json
from pathlib import Path

import pytest

from config import config as cfg
import core.auth as auth
import core.auth_manager as auth_manager
import core.kite_client as kite_client_module


pytestmark = [pytest.mark.unit, pytest.mark.behavior, pytest.mark.safety]


@pytest.fixture(autouse=True)
def _reset_auth_process_state(monkeypatch):
    auth.reset_kite_runtime_credentials_guard()
    auth_manager._CACHE.clear()
    monkeypatch.delenv("TRADING_BOT_TOKEN_PATH", raising=False)
    monkeypatch.delenv("KITE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("KITE_ALLOW_ENV_TOKEN_FOR_CI", raising=False)
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    yield
    auth.reset_kite_runtime_credentials_guard()
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


def test_access_token_path_uses_repo_runtime_by_default(tmp_path):
    assert auth_manager.access_token_path(tmp_path) == (
        tmp_path / ".runtime" / "kite_access_token"
    ).resolve()


def test_access_token_path_honors_explicit_override(monkeypatch, tmp_path):
    override = tmp_path / "private" / "token.txt"
    monkeypatch.setenv("TRADING_BOT_TOKEN_PATH", str(override))

    assert auth_manager.access_token_path(tmp_path) == override.resolve()


def test_repo_token_has_precedence_over_ci_environment_token(monkeypatch, tmp_path):
    _write_repo_token(tmp_path, "repo_token_1234\n")
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "env_token_9999")
    monkeypatch.setenv("KITE_ALLOW_ENV_TOKEN_FOR_CI", "true")

    resolved = auth_manager.resolve_access_token(
        repo_root_path=tmp_path,
        enforce_artifact_check=False,
    )

    assert resolved == "repo_token_1234"
    assert auth_manager._CACHE["token_source"] == "repo_file"


@pytest.mark.parametrize("enabled", ["1", "true", "yes", "on", "TRUE", " Yes "])
def test_environment_token_is_accepted_only_with_explicit_ci_override(
    monkeypatch, tmp_path, enabled
):
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "ci_token_1234")
    monkeypatch.setenv("KITE_ALLOW_ENV_TOKEN_FOR_CI", enabled)

    resolved = auth_manager.resolve_access_token(
        repo_root_path=tmp_path,
        enforce_artifact_check=False,
    )

    assert resolved == "ci_token_1234"
    assert auth_manager._CACHE["token_source"] == "env_ci"


@pytest.mark.parametrize("disabled", ["", "0", "false", "no", "off", "unexpected"])
def test_environment_token_is_rejected_without_ci_override(
    monkeypatch, tmp_path, disabled
):
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "env_token_must_not_be_used")
    if disabled:
        monkeypatch.setenv("KITE_ALLOW_ENV_TOKEN_FOR_CI", disabled)

    assert (
        auth_manager.resolve_access_token(
            repo_root_path=tmp_path,
            require_token=False,
            enforce_artifact_check=False,
        )
        == ""
    )
    assert "token" not in auth_manager._CACHE


def test_missing_required_token_fails_closed(tmp_path):
    with pytest.raises(RuntimeError, match="missing_kite_access_token"):
        auth_manager.resolve_access_token(
            repo_root_path=tmp_path,
            require_token=True,
            enforce_artifact_check=False,
        )


def test_missing_optional_token_returns_empty_without_false_cache(tmp_path):
    resolved = auth_manager.resolve_access_token(
        repo_root_path=tmp_path,
        require_token=False,
        enforce_artifact_check=False,
    )

    assert resolved == ""
    assert auth_manager._CACHE == {}


@pytest.mark.parametrize(
    ("exc", "code", "reason"),
    [
        (None, 403, ""),
        (RuntimeError("invalid session"), None, ""),
        (RuntimeError("TokenException"), None, ""),
        (RuntimeError("access token is invalid"), None, ""),
        (RuntimeError("unauthorized"), None, ""),
        (RuntimeError("websocket forbidden"), None, ""),
        (type("TokenException", (Exception,), {})("expired"), None, ""),
        (type("PermissionException", (Exception,), {})("denied"), None, ""),
        (type("AuthenticationError", (Exception,), {})("denied"), None, ""),
    ],
)
def test_auth_error_classifier_accepts_supported_auth_failures(exc, code, reason):
    assert auth_manager.is_auth_error(exc, code=code, reason_text=reason) is True


@pytest.mark.parametrize(
    "exc",
    [
        TimeoutError("timed out"),
        ConnectionError("connection reset"),
        RuntimeError("broker unavailable"),
        ValueError("malformed profile"),
    ],
)
def test_auth_error_classifier_does_not_misclassify_non_auth_failures(exc):
    assert auth_manager.is_auth_error(exc) is False


def test_network_classifier_does_not_mask_invalid_session_as_network_error():
    assert auth_manager._is_network_error(RuntimeError("connection invalid session")) is False
    assert auth_manager._is_network_error(TimeoutError("timed out")) is True


def test_validate_token_happy_path_returns_verified_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("KITE_API_KEY", "api_key_1234")
    monkeypatch.setattr(auth_manager, "resolve_access_token", lambda **_kwargs: "token_5678")
    _install_profile_client(
        monkeypatch,
        _ProfileKite({"user_id": "LLL209", "user_name": "Ram"}),
    )

    result = auth_manager.validate_token(repo_root_path=tmp_path)

    assert result["ok"] is True
    assert result["auth_state"] == "OK"
    assert result["error"] == ""
    assert result["user_id"] == "LLL209"
    assert result["user_name"] == "Ram"
    assert isinstance(result["ts_epoch"], float)


def test_validate_token_missing_api_key_fails_before_client_access(monkeypatch, tmp_path):
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


def test_validate_token_missing_token_fails_without_profile_call(monkeypatch, tmp_path):
    monkeypatch.setenv("KITE_API_KEY", "api_key_1234")

    def _missing(**_kwargs):
        raise RuntimeError("[AUTH] missing_kite_access_token")

    monkeypatch.setattr(auth_manager, "resolve_access_token", _missing)

    result = auth_manager.validate_token(repo_root_path=tmp_path)

    assert result["ok"] is False
    assert result["auth_state"] == "FAILED"
    assert "missing_kite_access_token" in result["error"]


def test_validate_token_fails_when_client_manager_has_no_kite(monkeypatch, tmp_path):
    monkeypatch.setenv("KITE_API_KEY", "api_key_1234")
    monkeypatch.setattr(auth_manager, "resolve_access_token", lambda **_kwargs: "token_5678")
    monkeypatch.setattr(kite_client_module.kite_client, "ensure", lambda: object())
    monkeypatch.setattr(kite_client_module.kite_client, "kite", None, raising=False)

    result = auth_manager.validate_token(repo_root_path=tmp_path)

    assert result["ok"] is False
    assert result["auth_state"] == "FAILED"
    assert result["error"] == "kite_client_unavailable"


def test_validate_token_rejects_profile_without_user_id(monkeypatch, tmp_path):
    monkeypatch.setenv("KITE_API_KEY", "api_key_1234")
    monkeypatch.setattr(auth_manager, "resolve_access_token", lambda **_kwargs: "token_5678")
    _install_profile_client(monkeypatch, _ProfileKite({"user_name": "Ram"}))

    result = auth_manager.validate_token(repo_root_path=tmp_path)

    assert result["ok"] is False
    assert result["auth_state"] == "FAILED"
    assert result["error"] == "profile_missing_user_id"
    assert result["user_id"] == ""
    assert result["user_name"] == "Ram"


def test_validate_token_auth_failure_invalidates_cache_and_requires_auth(
    monkeypatch, tmp_path
):
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
    assert result["error"].startswith("profile_error:RuntimeError:")
    assert auth_manager._CACHE == {}


def test_validate_token_network_failure_is_explicitly_unknown(monkeypatch, tmp_path):
    monkeypatch.setenv("KITE_API_KEY", "api_key_1234")
    monkeypatch.setattr(auth_manager, "resolve_access_token", lambda **_kwargs: "token_5678")
    _install_profile_client(monkeypatch, _ProfileKite(error=TimeoutError("timed out")))

    result = auth_manager.validate_token(repo_root_path=tmp_path)

    # This records the current contract. Callers must use auth_state and must not
    # interpret UNKNOWN_NETWORK as proof that authentication was verified.
    assert result["ok"] is True
    assert result["auth_state"] == "UNKNOWN_NETWORK"
    assert result["error"] == "profile_error:TimeoutError"


def test_validate_token_unclassified_profile_failure_is_failed(monkeypatch, tmp_path):
    monkeypatch.setenv("KITE_API_KEY", "api_key_1234")
    monkeypatch.setattr(auth_manager, "resolve_access_token", lambda **_kwargs: "token_5678")
    _install_profile_client(monkeypatch, _ProfileKite(error=ValueError("bad payload")))

    result = auth_manager.validate_token(repo_root_path=tmp_path)

    assert result["ok"] is False
    assert result["auth_state"] == "FAILED"
    assert result["error"] == "profile_error:ValueError:bad payload"


def test_auth_required_and_clear_state_are_persisted_and_audited(monkeypatch, tmp_path):
    events = []
    monkeypatch.setattr(auth_manager, "_append_auth_event", events.append)

    required = auth_manager.set_auth_required_state(
        reason="TokenException: invalid session",
        source="ws_on_error",
        code=403,
        repo_root_path=tmp_path,
    )

    state_path = auth_manager.auth_state_path(repo_root_path=tmp_path)
    assert json.loads(state_path.read_text(encoding="utf-8")) == required
    assert auth_manager.load_auth_state(repo_root_path=tmp_path) == required
    assert events[-1]["event"] == "AUTH_REQUIRED"
    assert events[-1]["reason"] == "TokenException: invalid session"

    cleared = auth_manager.clear_auth_required_state(
        source="auth_validation",
        repo_root_path=tmp_path,
    )

    assert json.loads(state_path.read_text(encoding="utf-8")) == cleared
    assert auth_manager.load_auth_state(repo_root_path=tmp_path) == cleared
    assert cleared["status"] == "OK"
    assert events[-1]["event"] == "AUTH_OK"


@pytest.mark.parametrize("content", ["not-json", "[]", "null", '"string"'])
def test_load_auth_state_fails_safe_for_corrupt_or_non_object_state(tmp_path, content):
    path = auth_manager.auth_state_path(repo_root_path=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    assert auth_manager.load_auth_state(repo_root_path=tmp_path) == {}


def test_get_kite_credentials_logs_only_fingerprints(monkeypatch, caplog):
    auth.reset_kite_runtime_credentials_guard()
    monkeypatch.setattr(cfg, "KITE_API_KEY", "full_api_key_1234", raising=False)
    monkeypatch.setattr(auth, "resolve_access_token", lambda **_kwargs: "full_secret_token_5678")
    caplog.set_level("INFO")

    api_key, token = auth.get_kite_credentials()

    assert api_key == "full_api_key_1234"
    assert token == "full_secret_token_5678"
    assert "full_api_key_1234" not in caplog.text
    assert "full_secret_token_5678" not in caplog.text
    assert "1234" in caplog.text
    assert "5678" in caplog.text
