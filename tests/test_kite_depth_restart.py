import core.kite_depth_ws as ws
from config import config as cfg


def test_restart_skips_without_cached_tokens(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [], raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    assert ws.restart_depth_ws(reason="unit_test_no_tokens") is False


def test_restart_respects_cooldown(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_FULL_RESTARTS", [], raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 9999.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)

    calls = {"start": 0, "stop": 0}

    def _start(tokens, profile_verified=False, **kwargs):
        calls["start"] += 1

    def _stop(reason="manual_stop"):
        calls["stop"] += 1

    monkeypatch.setattr(ws, "start_depth_ws", _start)
    monkeypatch.setattr(ws, "stop_depth_ws", _stop)

    assert ws.restart_depth_ws(reason="first") is True
    assert calls["start"] == 1
    assert calls["stop"] == 1

    # Immediate second restart should be blocked by cooldown.
    assert ws.restart_depth_ws(reason="second") is False
    assert calls["start"] == 1
    assert calls["stop"] == 1
