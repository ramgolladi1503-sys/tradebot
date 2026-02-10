from __future__ import annotations

from pathlib import Path

import pytest

from core import security_guard


def test_repo_token_artifact_is_blocked(tmp_path: Path, monkeypatch):
    repo_root = tmp_path / "repo"
    token_file = repo_root / "models" / "kite_access_token.pkl"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_bytes(b"secret")
    monkeypatch.delenv("KITE_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("TRADING_BOT_TOKEN_PATH", str(tmp_path / "local" / "kite_access_token"))
    with pytest.raises(RuntimeError) as err:
        security_guard.enforce_startup_security(repo_root=repo_root, require_token=False)
    message = str(err.value)
    assert "token_artifact_in_repo" in message
    assert "models/kite_access_token.pkl" in message


def test_missing_token_has_clear_error(tmp_path: Path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("KITE_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("TRADING_BOT_TOKEN_PATH", str(tmp_path / "local" / "kite_access_token"))
    with pytest.raises(RuntimeError) as err:
        security_guard.resolve_kite_access_token(repo_root=repo_root, require_token=True)
    assert "missing_kite_access_token" in str(err.value)


def test_env_token_passes_guard(tmp_path: Path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "env_token_123")
    monkeypatch.setenv("TRADING_BOT_TOKEN_PATH", str(tmp_path / "local" / "kite_access_token"))
    token = security_guard.enforce_startup_security(repo_root=repo_root, require_token=True)
    assert token == "env_token_123"
