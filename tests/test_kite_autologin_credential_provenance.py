from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _module():
    path = Path(__file__).parents[1] / "scripts" / "kite_autologin_localhost.py"
    spec = importlib.util.spec_from_file_location("kite_autologin_provenance", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_governed_credentials_reject_ambient_shadowing(tmp_path, monkeypatch):
    path = tmp_path / "kite_app.env"
    path.write_text("KITE_API_KEY=key\nKITE_API_SECRET=secret\n")
    mod = _module()
    monkeypatch.setenv("KITE_CREDENTIALS_PATH", str(path))
    monkeypatch.setenv("KITE_API_KEY", "key")
    monkeypatch.setenv("KITE_API_SECRET", "different-secret")
    with pytest.raises(SystemExit, match="conflicts with governed credential source"):
        mod._resolve_api_secret()


def test_governed_credentials_are_used_when_ambient_values_absent(tmp_path, monkeypatch):
    path = tmp_path / "kite_app.env"
    path.write_text("export KITE_API_KEY='key'\nKITE_API_SECRET='secret'\n")
    mod = _module()
    monkeypatch.setenv("KITE_CREDENTIALS_PATH", str(path))
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    monkeypatch.delenv("KITE_API_SECRET", raising=False)
    assert mod._resolve_api_key() == "key"
    assert mod._resolve_api_secret() == "secret"


def test_startup_validation_receives_governed_credentials(tmp_path, monkeypatch):
    path = tmp_path / "kite_app.env"
    path.write_text("KITE_API_KEY=key\nKITE_API_SECRET=secret\n")
    mod = _module()
    monkeypatch.setenv("KITE_CREDENTIALS_PATH", str(path))
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    monkeypatch.delenv("KITE_API_SECRET", raising=False)
    mod._prepare_governed_credentials()
    assert mod.cfg.KITE_API_KEY == "key"
    assert mod.cfg.KITE_API_SECRET == "secret"
