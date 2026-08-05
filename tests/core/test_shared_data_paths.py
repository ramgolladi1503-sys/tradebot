from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_shared_data_roots_default_outside_repo(monkeypatch):
    for key in (
        "TRADEBOT_DATA_ROOT",
        "TRADEBOT_HISTORICAL_DATA_ROOT",
        "TRADEBOT_REPLAY_DATA_ROOT",
        "TRADEBOT_MARKET_DATA_ROOT",
        "TRADEBOT_RESEARCH_INPUTS_ROOT",
        "TRADEBOT_ARCHIVED_LIVE_EVIDENCE_ROOT",
    ):
        monkeypatch.delenv(key, raising=False)

    import core.shared_data_paths as paths

    importlib.reload(paths)
    assert paths.shared_data_root() == Path.home() / "tradebot-shared-data"
    assert paths.historical_data_root() == paths.shared_data_root() / "historical"
    assert paths.replay_data_root() == paths.shared_data_root() / "replay"


def test_shared_data_roots_allow_specific_overrides(tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    replay = tmp_path / "custom-replay"
    monkeypatch.setenv("TRADEBOT_DATA_ROOT", str(shared))
    monkeypatch.setenv("TRADEBOT_REPLAY_DATA_ROOT", str(replay))

    import core.shared_data_paths as paths

    importlib.reload(paths)
    assert paths.shared_data_root() == shared.resolve()
    assert paths.historical_data_root() == (shared / "historical").resolve()
    assert paths.replay_data_root() == replay.resolve()
    assert paths.market_data_root() == (shared / "market_data").resolve()


def test_required_shared_data_path_fails_closed_with_clear_message(tmp_path):
    import core.shared_data_paths as paths

    missing = tmp_path / "missing"
    with pytest.raises(paths.SharedDataRootMissingError) as excinfo:
        paths.require_existing_shared_data_path(missing, purpose="offline replay")

    message = str(excinfo.value)
    assert "offline replay requires external TradeBot data" in message
    assert "TRADEBOT_DATA_ROOT" in message
