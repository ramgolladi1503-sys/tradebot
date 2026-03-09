import json
import runpy
from pathlib import Path

import pytest

from config import config as cfg
import core.feed_restart_guard as restart_guard


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "clear_feed_restart_guard.py"
)


def test_clear_feed_restart_guard_requires_confirmation(monkeypatch):
    monkeypatch.setattr("sys.argv", ["clear_feed_restart_guard.py"])
    with pytest.raises(SystemExit, match="--yes-i-mean-it"):
        runpy.run_path(str(SCRIPT_PATH), run_name="__main__")


def test_clear_feed_restart_guard_resets_state(monkeypatch, tmp_path):
    state_path = tmp_path / "feed_restart_guard_state.json"
    guard = restart_guard.FeedRestartGuard()

    monkeypatch.setattr(restart_guard, "STATE_PATH", state_path)
    monkeypatch.setattr(restart_guard, "feed_restart_guard", guard)
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_WINDOW_SEC", 3600.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_MAX", 1, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_COOLDOWN_SEC", 900.0, raising=False)

    assert guard.allow_restart(now=1000.0, reason="first") is True
    assert guard.allow_restart(now=1001.0, reason="trip") is False

    monkeypatch.setattr("sys.argv", ["clear_feed_restart_guard.py", "--yes-i-mean-it"])
    runpy.run_path(str(SCRIPT_PATH), run_name="__main__")

    payload = json.loads(state_path.read_text())
    assert payload.get("breaker_open_until") == 0.0
    assert payload.get("restart_epochs") == []
