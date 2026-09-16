"""Tests for SQLite runtime isolation from external storage."""
import os
import shutil
import tempfile
from pathlib import Path
import pytest

from core.runtime_paths import _resolve_db_root, _repo_root
from core.paths import db_dir, trade_db_path
from core.runtime_storage_authority import StorageAuthority, bind_environment


def test_resolve_db_root_defaults_to_local_internal_storage(monkeypatch):
    """DB_ROOT defaults to local repo-local .runtime/db, not external volume."""
    monkeypatch.delenv("DB_ROOT", raising=False)
    monkeypatch.delenv("DATA_ROOT", raising=False)
    expected = (_repo_root() / ".runtime" / "db").resolve()
    assert _resolve_db_root() == expected


def test_resolve_db_root_respects_explicit_env(tmp_path, monkeypatch):
    """DB_ROOT explicitly set in environment is honored."""
    target_dir = tmp_path / "custom_db"
    target_dir.mkdir()
    monkeypatch.setenv("DB_ROOT", str(target_dir))
    assert _resolve_db_root() == target_dir.resolve()
    assert db_dir() == target_dir.resolve()
    assert trade_db_path("DEFAULT") == target_dir.resolve() / "DEFAULT.sqlite"


def test_bind_environment_pins_db_root_to_local_storage(tmp_path, monkeypatch):
    """bind_environment pins DB_ROOT to local storage while DATA_ROOT points to external root."""
    external_root = tmp_path / "external_volume" / "session_root"
    local_db = tmp_path / "local_nvme" / "db"
    external_root.mkdir(parents=True)
    local_db.mkdir(parents=True)

    auth = StorageAuthority(
        volume=tmp_path / "external_volume",
        runtime_root=external_root,
        device_id=external_root.stat().st_dev,
    )

    orig_env = {k: os.environ.get(k) for k in ("DATA_ROOT", "DB_ROOT", "LOG_DIR", "REPO_LOG_DIR")}
    try:
        bind_environment(auth, local_db_root=local_db)
        assert os.environ["DATA_ROOT"] == str(external_root)
        assert os.environ["DB_ROOT"] == str(local_db.resolve())
        assert db_dir() == local_db.resolve()

        # Simulate external volume loss by removing external_root
        shutil.rmtree(external_root)
        assert not external_root.exists()

        # Local DB directory and path remain accessible and writable
        assert local_db.exists()
        sqlite_file = local_db / "DEFAULT.sqlite"
        sqlite_file.write_text("dummy sqlite payload", encoding="utf-8")
        assert sqlite_file.read_text(encoding="utf-8") == "dummy sqlite payload"
    finally:
        for k, v in orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
