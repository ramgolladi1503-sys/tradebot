import time

from config import config as cfg
from core.feed_restart_guard import FeedRestartGuard


def test_restart_storm_breaker(monkeypatch):
    guard = FeedRestartGuard()
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_WINDOW_SEC", 60.0)
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_MAX", 2)
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_COOLDOWN_SEC", 300.0)

    base = time.time()
    assert guard.allow_restart(now=base, reason="first") is True
    assert guard.allow_restart(now=base + 1, reason="second") is True
    assert guard.allow_restart(now=base + 2, reason="third") is False
