from config import config as cfg
import core.governance_gate as gate


def _base_market_data():
    return {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "market_open": True,
        "quote_ok": True,
        "chain_source": "live",
        "option_chain_health": {"missing_quote_pct": 0.0},
        "orb_bias": "UP",
        "day_confidence": 0.8,
        "regime_probs": {"TREND": 0.72, "RANGE": 0.28},
    }


def test_trading_allowed_snapshot_feed_stale_is_ltp_time_based(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "GOV_GATE_REQUIRE_AUTH", True, raising=False)
    monkeypatch.setattr(cfg, "GOV_GATE_ENFORCE_PAPER", False, raising=False)
    now_epoch = 1_000.0
    monkeypatch.setattr(gate, "now_utc_epoch", lambda: now_epoch)
    monkeypatch.setattr(gate.risk_halt, "is_halted", lambda: False)
    monkeypatch.setattr(gate, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(
        gate,
        "_load_recent_auth_health",
        lambda now_epoch: {"ok": True, "age_sec": 12.0, "reason": "", "auth_state": "OK"},
    )
    market_data = {
        **_base_market_data(),
        "ltp_ts_epoch": now_epoch - 0.5,
        "depth_age_sec": 12.0,
    }
    snap = gate.trading_allowed_snapshot(market_data)
    assert snap.allowed is True
    assert "FEED_STALE" not in snap.reasons


def test_trading_allowed_snapshot_blocks_when_auth_not_recent(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "GOV_GATE_REQUIRE_AUTH", True, raising=False)
    now_epoch = 2_000.0
    monkeypatch.setattr(gate, "now_utc_epoch", lambda: now_epoch)
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

    snap = gate.trading_allowed_snapshot(
        {
            **_base_market_data(),
            "ltp_ts_epoch": now_epoch - 0.3,
            "depth_age_sec": 0.4,
        }
    )

    assert snap.allowed is False
    assert "AUTH_NOT_VERIFIED_RECENTLY" in snap.reasons


def test_snapshot_feed_health_ignores_global_stale_when_snapshot_fresh(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "GOV_GATE_REQUIRE_AUTH", True, raising=False)
    now_epoch = 3_000.0
    monkeypatch.setattr(gate, "now_utc_epoch", lambda: now_epoch)
    monkeypatch.setattr(
        gate,
        "get_freshness_status",
        lambda force=False: {
            "ok": False,
            "state": "STALE",
            "market_open": True,
            "reasons": ["ltp_stale age=999 max=2.5"],
            "ltp": {"age_sec": 999.0},
            "depth": {"age_sec": 999.0},
        },
    )
    monkeypatch.setattr(gate.risk_halt, "is_halted", lambda: False)
    monkeypatch.setattr(gate, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(
        gate,
        "_load_recent_auth_health",
        lambda now_epoch: {"ok": True, "age_sec": 1.0, "reason": "", "auth_state": "OK"},
    )
    snap = gate.trading_allowed_snapshot(
        {
            **_base_market_data(),
            "ltp_ts_epoch": now_epoch - 0.2,
            "depth_age_sec": 0.3,
        }
    )
    assert snap.allowed is True
    assert "FEED_STALE" not in snap.reasons
    assert snap.details.get("freshness_source") == "market_snapshot"


def test_index_instrument_does_not_require_depth(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "GOV_GATE_REQUIRE_AUTH", True, raising=False)
    now_epoch = 4_000.0
    monkeypatch.setattr(gate, "now_utc_epoch", lambda: now_epoch)
    monkeypatch.setattr(gate.risk_halt, "is_halted", lambda: False)
    monkeypatch.setattr(gate, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(
        gate,
        "_load_recent_auth_health",
        lambda now_epoch: {"ok": True, "age_sec": 1.0, "reason": "", "auth_state": "OK"},
    )
    snap = gate.trading_allowed_snapshot(
        {
            **_base_market_data(),
            "instrument": "INDEX",
            "ltp_ts_epoch": now_epoch - 0.1,
            "depth_age_sec": None,
        }
    )
    assert snap.allowed is True
    assert "FEED_STALE" not in snap.reasons
