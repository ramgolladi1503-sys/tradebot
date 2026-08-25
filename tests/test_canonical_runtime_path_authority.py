import importlib
import json
from pathlib import Path

import pytest


def _reload(monkeypatch, root: Path | None, *, live: bool = False):
    if root is None:
        monkeypatch.delenv("TRADEBOT_RUNTIME_ROOT", raising=False)
    else:
        monkeypatch.setenv("TRADEBOT_RUNTIME_ROOT", str(root))
    monkeypatch.setenv("TRADEBOT_CANONICAL_LIVE", "1" if live else "0")
    import core.runtime_paths as runtime_paths
    return importlib.reload(runtime_paths)


def test_configured_runtime_root_wins(monkeypatch, tmp_path):
    module = _reload(monkeypatch, tmp_path / "external", live=False)
    assert module.DATA_ROOT == (tmp_path / "external").resolve()


def test_live_missing_root_fails_closed(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError, match="CANONICAL_RUNTIME_ROOT_UNAVAILABLE"):
        _reload(monkeypatch, tmp_path / "missing", live=True)


def test_live_root_never_falls_back_to_checkout_runtime(monkeypatch, tmp_path):
    root = tmp_path / "external"
    root.mkdir()
    module = _reload(monkeypatch, root, live=True)
    assert ".runtime" not in str(module.DATA_ROOT)
    assert module.DB_ROOT.is_relative_to(root.resolve())


def test_feed_store_db_uses_canonical_root(monkeypatch, tmp_path):
    root = tmp_path / "external"
    root.mkdir()
    monkeypatch.setenv("TRADEBOT_RUNTIME_ROOT", str(root))
    monkeypatch.setenv("TRADEBOT_CANONICAL_LIVE", "1")
    import core.feed.runtime_store as store
    import core.runtime_paths as runtime_paths
    importlib.reload(runtime_paths)
    importlib.reload(store)
    assert store._db_path().is_relative_to(root.resolve())


def test_diagnostic_is_redacted_and_bound(monkeypatch, tmp_path):
    root = tmp_path / "external"
    root.mkdir()
    module = _reload(monkeypatch, root, live=True)
    destination = root / "runtime_path_authority.json"
    module.write_runtime_path_authority(destination, source_sha="a" * 40, session_root=root)
    payload = json.loads(destination.read_text())
    assert payload["path_authority_status"] == "PASS"
    assert "token" not in json.dumps(payload).lower()
    assert Path(payload["feed_db_path"]).is_relative_to(root.resolve())
