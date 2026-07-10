from __future__ import annotations

from types import MappingProxyType

import pytest

import core.orchestrator as orch_mod
from core.orchestrator_helpers import freeze_cycle_feed_truth_payload


def test_freeze_cycle_feed_truth_payload_returns_immutable_copy():
    source = {"ws_connected": True, "feed_ok": True}
    frozen = freeze_cycle_feed_truth_payload(source)

    assert isinstance(frozen, MappingProxyType)
    assert dict(frozen) == {"ws_connected": True, "feed_ok": True}

    source["ws_connected"] = False
    assert frozen["ws_connected"] is True

    with pytest.raises(TypeError):
        frozen["feed_ok"] = False


def test_load_cycle_feed_truth_payload_reads_once_and_freezes(tmp_path, monkeypatch):
    feed_truth_path = tmp_path / "feed_truth_latest.json"
    feed_truth_path.write_text('{"ws_connected": true, "feed_ok": true}', encoding="utf-8")

    calls = {"reads": 0}

    def _read_json_dict(path):
        calls["reads"] += 1
        return {"ws_connected": True, "feed_ok": True}

    monkeypatch.setattr(orch_mod, "_read_json_dict", _read_json_dict)

    frozen = orch_mod._load_cycle_feed_truth_payload(feed_truth_path)

    assert calls["reads"] == 1
    assert isinstance(frozen, MappingProxyType)
    assert frozen["feed_ok"] is True
