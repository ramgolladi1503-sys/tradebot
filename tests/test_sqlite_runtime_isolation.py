"""Tests for SQLite runtime isolation from external storage."""
import os
import shutil
import tempfile
from pathlib import Path
import pytest

from core.runtime_paths import _resolve_db_root, _repo_root
from core.paths import db_dir, trade_db_path
from core.runtime_storage_authority import StorageAuthority, bind_environment


def test_resolve_db_root_defaults_to_local_internal_storage():
    """DB_ROOT defaults to local repo-local .runtime/db, not external volume."""
    orig_env = os.environ.pop("DB_ROOT", None)
    orig_data = os.environ.pop("DATA_ROOT", None)
    try:
        expected = (_repo_root() / ".runtime" / "db").resolve()
        assert _resolve_db_root() == expected
    finally:
        if orig_env is not None:
            os.environ["DB_ROOT"] = orig_env
        if orig_data is not None:
            os.environ["DATA_ROOT"] = orig_data


def test_resolve_db_root_respects_explicit_env(tmp_path):
    """DB_ROOT explicitly set in environment is honored."""
    target_dir = tmp_path / "custom_db"
    target_dir.mkdir()
    orig_env = os.environ.get("DB_ROOT")
    try:
        os.environ["DB_ROOT"] = str(target_dir)
        assert _resolve_db_root() == target_dir.resolve()
        assert db_dir() == target_dir.resolve()
        assert trade_db_path("DEFAULT") == target_dir.resolve() / "DEFAULT.sqlite"
    finally:
        if orig_env is not None:
            os.environ["DB_ROOT"] = orig_env
        else:
            os.environ.pop("DB_ROOT", None)


def test_bind_environment_pins_db_root_to_local_storage(tmp_path):
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

    orig_data = os.environ.get("DATA_ROOT")
    orig_db = os.environ.get("DB_ROOT")
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
        if orig_data is not None:
            os.environ["DATA_ROOT"] = orig_data
        else:
            os.environ.pop("DATA_ROOT", None)
        if orig_db is not None:
            os.environ["DB_ROOT"] = orig_db
        else:
            os.environ.pop("DB_ROOT", None)
