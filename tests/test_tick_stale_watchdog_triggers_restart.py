import core.kite_depth_ws as ws


def test_tick_stale_watchdog_triggers_restart(monkeypatch):
    calls = []
    monkeypatch.setattr(ws, "_STALE_STRIKES", 1, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_LAST_FEED_HEALTH_STATE", None, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "_latest_db_tick_epoch", lambda: 100.0)

    def _restart(reason="unknown", ignore_cooldown=False):
        calls.append(reason)
        return True

    out = ws._run_db_tick_watchdog_cycle(
        now_epoch=110.5,
        market_open=True,
        stale_restart_sec=5.0,
        reset_sec=2.0,
        strikes_to_restart=2,
        restart_cb=_restart,
    )

    assert out["restarted"] is True
    assert calls == ["tick_stalled"]


def test_tick_stale_watchdog_ignores_db_lag_when_ws_ticks_are_fresh(monkeypatch):
    calls = []
    events = []
    monkeypatch.setattr(ws, "_STALE_STRIKES", 1, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 109.5, raising=False)
    monkeypatch.setattr(ws, "_LAST_FEED_HEALTH_STATE", None, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload: events.append((event, payload)))
    monkeypatch.setattr(ws, "_latest_db_tick_epoch", lambda: 100.0)

    def _restart(reason="unknown", ignore_cooldown=False):
        calls.append(reason)
        return True

    out = ws._run_db_tick_watchdog_cycle(
        now_epoch=110.5,
        market_open=True,
        stale_restart_sec=5.0,
        reset_sec=2.0,
        strikes_to_restart=2,
        restart_cb=_restart,
    )

    assert out["restarted"] is False
    assert out["stale_strikes"] == 0
    assert calls == []
    assert any(event == "FEED_HEALTH_OK" for event, _payload in events)
