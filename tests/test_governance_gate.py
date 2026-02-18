from config import config as cfg
import core.governance_gate as gate


def _base_market_data():
    return {
        "symbol": "NIFTY",
        "quote_ok": True,
        "chain_source": "live",
        "option_chain_health": {"missing_quote_pct": 0.0},
        "orb_bias": "UP",
        "day_confidence": 0.8,
        "regime_probs": {"TREND": 0.72, "RANGE": 0.28},
    }


def test_trading_allowed_snapshot_blocks_stale_depth(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "GOV_GATE_REQUIRE_AUTH", True, raising=False)
    monkeypatch.setattr(cfg, "GOV_GATE_ENFORCE_PAPER", False, raising=False)
    monkeypatch.setattr(
        gate,
        "get_freshness_status",
        lambda force=False: {
            "ok": False,
            "state": "STALE",
            "market_open": True,
            "reasons": ["depth_stale"],
            "ltp": {"age_sec": 0.5},
            "depth": {"age_sec": 12.0},
        },
    )
    monkeypatch.setattr(gate.risk_halt, "is_halted", lambda: False)
    monkeypatch.setattr(gate, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(
        gate,
        "_load_recent_auth_health",
        lambda now_epoch: {"ok": True, "age_sec": 12.0, "reason": "", "auth_state": "OK"},
    )

    snap = gate.trading_allowed_snapshot(_base_market_data())

    assert snap.allowed is False
    assert "FEED_STALE" in snap.reasons


def test_trading_allowed_snapshot_blocks_when_auth_not_recent(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "GOV_GATE_REQUIRE_AUTH", True, raising=False)
    monkeypatch.setattr(
        gate,
        "get_freshness_status",
        lambda force=False: {
            "ok": True,
            "state": "OK",
            "market_open": True,
            "reasons": [],
            "ltp": {"age_sec": 0.3},
            "depth": {"age_sec": 0.4},
        },
    )
    monkeypatch.setattr(gate.risk_halt, "is_halted", lambda: False)
    monkeypatch.setattr(gate, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(
        gate,
        "_load_recent_auth_health",
        lambda now_epoch: {
            "ok": False,
            "age_sec": 999.0,
            "reason": "auth_health_stale",
            "auth_state": "FAILED",
        },
    )

    snap = gate.trading_allowed_snapshot(_base_market_data())

    assert snap.allowed is False
    assert "AUTH_NOT_VERIFIED_RECENTLY" in snap.reasons
