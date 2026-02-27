from types import SimpleNamespace

from core import runtime_health


def test_runtime_health_shape(monkeypatch):
    monkeypatch.setattr(
        runtime_health,
        "get_freshness_status",
        lambda force=False: {
            "state": "OK",
            "market_open": True,
            "ltp": {"age_sec": 1.0},
            "depth": {"age_sec": 2.0},
            "reasons": [],
        },
    )
    monkeypatch.setattr(
        runtime_health,
        "get_feed_debug",
        lambda now_epoch=None: {
            "ws_connected": True,
            "subscribed_tokens_count": 2,
            "last_tick_age_sec": 1.5,
        },
    )

    exec_engine = SimpleNamespace(
        kill_switch_triggered=False,
        kill_switch_reason=None,
        get_last_spread_decision=lambda: {"spread_pct": 0.01},
        get_reconciliation_status=lambda: {"daemon_running": True, "last_cycle_ts_epoch": 123.0},
    )
    risk_state = SimpleNamespace(mode="NORMAL", daily_pnl_pct=0.01, open_risk_pct=0.02)
    orch = SimpleNamespace(execution_engine=exec_engine, risk_state=risk_state)

    payload = runtime_health.get_runtime_health(orchestrator=orch, now_epoch=123.0)
    assert "ts_epoch" in payload
    assert "mode" in payload
    assert "market_open" in payload
    assert "feed" in payload
    assert "execution" in payload
    assert "risk" in payload
    assert "recon" in payload
