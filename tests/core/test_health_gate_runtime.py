from __future__ import annotations

from config import config as cfg
from core.health_gate import evaluate_runtime_health


def _base_snapshot() -> dict:
    return {
        "schema_version": "1.0",
        "snapshot_id": "snap-runtime-001",
        "timestamp_epoch": 1772428800.123,
        "symbol": "NIFTY",
        "token_coverage": {
            "index_token": 256265,
            "option_tokens_count": 20,
            "option_tokens": [1001, 1002],
            "strike_window": {"atm": 24700, "min": 24400, "max": 25000, "step": 50},
        },
        "freshness": {
            "sla_threshold_sec": 2.5,
            "max_tick_age_sec": 1.2,
            "stale_tokens_count": 0,
        },
        "ticks": {
            "index": {
                "instrument_token": 256265,
                "last_price": 24705.0,
                "timestamp_epoch": 1772428800.12,
            },
            "options": {
                "1001": {"instrument_token": 1001, "last_price": 24.5, "timestamp_epoch": 1772428800.10},
                "1002": {"instrument_token": 1002, "last_price": 31.2, "timestamp_epoch": 1772428800.11},
            },
        },
        "expiry": {"is_expiry_day": False, "expiry_date": "2026-03-02"},
        "regime": {"state": "TREND", "confidence": 0.8},
        "health": {"ok": True, "blockers": []},
        "data_sources": {"ticks": "sqlite", "token_resolution": "resolver"},
    }


def test_evaluate_runtime_health_ok_snapshot_returns_ok(monkeypatch):
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKEN_COUNT", 10, raising=False)
    snap = _base_snapshot()
    out = evaluate_runtime_health(snap, feed_connected=True, db_ok=True)
    assert out["ok"] is True
    assert out["blockers"] == []


def test_evaluate_runtime_health_stale_returns_freshness_blocker(monkeypatch):
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKEN_COUNT", 10, raising=False)
    snap = _base_snapshot()
    snap["freshness"]["max_tick_age_sec"] = 9.0
    snap["freshness"]["sla_threshold_sec"] = 2.5
    out = evaluate_runtime_health(snap, feed_connected=True, db_ok=True)
    assert out["ok"] is False
    codes = [str(b.get("code")) for b in out["blockers"]]
    assert "FRESHNESS_STALE" in codes


def test_evaluate_runtime_health_token_coverage_returns_blocker(monkeypatch):
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKEN_COUNT", 50, raising=False)
    snap = _base_snapshot()
    snap["token_coverage"]["option_tokens_count"] = 5
    out = evaluate_runtime_health(snap, feed_connected=True, db_ok=True)
    assert out["ok"] is False
    codes = [str(b.get("code")) for b in out["blockers"]]
    assert "TOKEN_COVERAGE_BELOW_THRESHOLD" in codes

