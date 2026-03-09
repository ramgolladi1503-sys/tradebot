import dashboard.streamlit_app_runtime as runtime


def test_live_strict_stale_degrades(monkeypatch):
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
            "sla_state": "LIVE",
            "allow_stale_quotes": False,
            "ltp_required": True,
            "ltp_age_sec": 6.0,
            "last_tick_age_sec": 6.0,
            "ltp_max_age_sec": 2.5,
            "depth_required": False,
            "ws_connected": True,
            "reasons": [],
            "sla_status": "OK",
        },
    }

    sm, _fd = runtime._bridge_feed_state_from_runtime_health(local_sm, local_fd, runtime_health)
    assert sm.get("state") == "DEGRADED"
    assert "stale_ticks" in str(sm.get("reason") or "")

    banner = runtime._feed_banner_text("DEGRADED", str(sm.get("reason") or ""), strict_live=True)
    assert isinstance(banner, str)
    assert "LIVE entries blocked" in banner
