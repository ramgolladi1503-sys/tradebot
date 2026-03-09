import dashboard.streamlit_app_runtime as runtime


def test_bridge_strict_live_threshold_degrades_when_stale(monkeypatch):
    monkeypatch.setattr(runtime.cfg, "UI_RUNTIME_HEALTH_MAX_AGE_SEC", 120.0, raising=False)
    monkeypatch.setattr(runtime.cfg, "SLA_MAX_LTP_AGE_SEC", 2.5, raising=False)
    monkeypatch.setattr(runtime.cfg, "FEED_HEALTH_OPTION_OK_AGE_SEC", 2.5, raising=False)
    monkeypatch.setattr(runtime.time, "time", lambda: 1_000.0)

    local_sm = {"state": "DOWN", "reason": "no_ws_messages"}
    local_fd = {"ws_connected": None}
    runtime_health = {
        "ts_epoch": 999.0,
        "market_open": True,
        "feed": {
            "ws_connected": True,
            "subscriptions_count": 74,
            "last_tick_age_sec": 6.0,
            "ltp_age_sec": 6.0,
            "allow_stale_quotes": False,
            "ltp_required": True,
            "ltp_max_age_sec": 2.5,
            "sla_status": "OK",
            "reasons": [],
        },
    }

    sm, fd = runtime._bridge_feed_state_from_runtime_health(local_sm, local_fd, runtime_health)
    assert sm["state"] == "DEGRADED"
    assert sm["reason"] == "runtime_health_ws_connected_but_stale_ticks"
    assert fd["ws_connected"] is True

