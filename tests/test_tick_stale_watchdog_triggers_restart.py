import core.kite_depth_ws as ws


def test_tick_stale_watchdog_triggers_restart(monkeypatch):
    calls = []
    monkeypatch.setattr(ws, "_STALE_STRIKES", 1, raising=False)
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
