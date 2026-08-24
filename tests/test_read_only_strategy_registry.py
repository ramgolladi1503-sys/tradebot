import json

import pytest

from core.read_only_strategy_registry import build_strategy_registry, write_strategy_registry


def test_registry_is_explicit_and_pending():
    payload = build_strategy_registry(session_id="s1", source_sha="a" * 40)
    entry = payload["strategies"][0]
    assert entry["strategy_id"] == "CAS_SW_RUNTIME_V2_1514"
    assert len(entry["spec_sha"]) == 64
    assert entry["runtime_status"] == "PENDING"
    assert entry["enabled"] is False
    assert entry["execution_status"] == "advisory_only"
    assert payload["live_execution_authorized"] is False


def test_registry_no_overwrite(tmp_path):
    path = tmp_path / "STRATEGY_REGISTRY.json"
    write_strategy_registry(path, session_id="s1", source_sha="a" * 40)
    with pytest.raises(FileExistsError):
        write_strategy_registry(path, session_id="s1", source_sha="a" * 40)
    assert json.loads(path.read_text())["verdict"] == "PENDING"

