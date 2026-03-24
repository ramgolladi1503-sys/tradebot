from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import core.runtime_guard as runtime_guard


def test_validate_repo_root_accepts_dynamic_repo_root():
    root = runtime_guard.validate_repo_root()

    assert root == Path(__file__).resolve().parents[1]
    assert (root / "main.py").exists()
    assert (root / "core").is_dir()


def test_validate_repo_root_rejects_malformed_root(tmp_path):
    (tmp_path / "core").mkdir()

    with pytest.raises(RuntimeError, match="INVALID REPO ROOT"):
        runtime_guard.validate_repo_root(tmp_path)


def test_runtime_guard_import_is_independent_of_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    module = importlib.reload(runtime_guard)

    assert module.ensure_runtime_repo_guard() == Path(__file__).resolve().parents[1]
