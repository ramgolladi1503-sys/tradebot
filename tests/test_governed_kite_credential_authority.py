import importlib

import pytest


def test_conflicting_ambient_credentials_fail_closed(monkeypatch, tmp_path):
    source = tmp_path / "kite_app.env"
    source.write_text("KITE_API_KEY=governed-key\nKITE_API_SECRET=governed-secret\n")
    monkeypatch.setenv("KITE_CREDENTIALS_PATH", str(source))
    monkeypatch.setenv("KITE_API_KEY", "ambient-key")
    monkeypatch.setenv("KITE_API_SECRET", "governed-secret")
    import config.config as config
    with pytest.raises(RuntimeError, match="governed_kite_credential_conflict:KITE_API_KEY"):
        importlib.reload(config)


def test_external_source_is_used_without_repo_env(monkeypatch, tmp_path):
    source = tmp_path / "kite_app.env"
    source.write_text("export KITE_API_KEY=governed-key\nKITE_API_SECRET='governed-secret'\n")
    monkeypatch.setenv("KITE_CREDENTIALS_PATH", str(source))
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    monkeypatch.delenv("KITE_API_SECRET", raising=False)
    import config.config as config
    loaded = importlib.reload(config)
    assert loaded.KITE_API_KEY == "governed-key"
    assert loaded.KITE_API_SECRET == "governed-secret"
    assert "governed-secret" not in repr(loaded.KITE_CREDENTIAL_SOURCE)
