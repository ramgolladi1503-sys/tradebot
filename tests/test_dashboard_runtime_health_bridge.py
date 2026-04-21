import dashboard.streamlit_app_runtime as runtime


def test_bridge_runtime_ws_connected_overrides_local_no_ws(monkeypatch):
    monkeypatch.setattr(runtime.cfg, "UI_RUNTIME_HEALTH_MAX_AGE_SEC", 120.0, raising=False)
    monkeypatch.setattr(runtime.time, "time", lambda: 1_000.0)

    local_sm = {"state": "DOWN", "reason": "no_ws_messages"}
    local_fd = {"ws_connected": None}
    runtime_health = {
        "ts_epoch": 995.0,
        "market_open": True,
        "feed": {
            "ws_connected": True,
            "subscriptions_count": 74,
            "last_tick_age_sec": 0.8,
        },
    }

    sm, fd = runtime._bridge_feed_state_from_runtime_health(local_sm, local_fd, runtime_health)
    assert sm["state"] == "OK"
    assert sm["reason"] == "runtime_health_ws_connected"
    assert sm["ws_msg_age_sec"] == 0.8
    assert fd["ws_connected"] is True
    assert fd["subscribed_tokens_count"] == 74


def test_bridge_ignores_stale_runtime_health(monkeypatch):
    monkeypatch.setattr(runtime.cfg, "UI_RUNTIME_HEALTH_MAX_AGE_SEC", 60.0, raising=False)
    monkeypatch.setattr(runtime.time, "time", lambda: 1_000.0)

    local_sm = {"state": "DOWN", "reason": "no_ws_messages"}
    local_fd = {"ws_connected": None}
    stale_runtime_health = {
        "ts_epoch": 900.0,
        "market_open": True,
        "feed": {
            "ws_connected": True,
            "subscriptions_count": 73,
            "last_tick_age_sec": 0.5,
        },
    }

    sm, fd = runtime._bridge_feed_state_from_runtime_health(local_sm, local_fd, stale_runtime_health)
    assert sm == local_sm
    assert fd == local_fd


def test_bridge_runtime_ws_connected_but_stale_ticks_sets_degraded(monkeypatch):
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
            "last_tick_age_sec": 194.8,
            "ltp_age_sec": 194.8,
        },
    }

    sm, fd = runtime._bridge_feed_state_from_runtime_health(local_sm, local_fd, runtime_health)
    assert sm["state"] == "DEGRADED"
    assert sm["reason"] == "runtime_health_ws_connected_but_stale_ticks"
    assert fd["ws_connected"] is True


def test_dashboard_feed_display_summary_prefers_live_runtime_health_over_idle_snapshot():
    snapshot = {
        "feed_freshness": {"state": "IDLE", "market_open": True},
        "feed_debug": {"ws_connected": None},
        "runtime_health": {
            "feed": {
                "runtime_state": "RUNNING",
                "ws_connected": True,
                "subscribed_option_tokens_count": 68,
                "last_tick_age_sec": 0.4,
                "last_depth_age_sec": 0.0,
            }
        },
    }

    state, reason, ltp_age, depth_age = runtime._dashboard_feed_display_summary(snapshot)

    assert state == "OK"
    assert reason == "runtime_running"
    assert ltp_age == 0.4
    assert depth_age == 0.0
