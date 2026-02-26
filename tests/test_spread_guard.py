from __future__ import annotations

from config import config as cfg
from core.spread_guard import SpreadGuard


def _set_defaults(monkeypatch):
    monkeypatch.setattr(cfg, "SPREAD_GUARD_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_BASE_SPREAD_PCT", 0.01, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_VOL_METHOD", "ATR", raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_VOL_PERIOD", 20, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_VOL_FACTOR", 1.5, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_STDDEV_TO_ATR_MULT", 1.0, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_CRITICAL_VOL_PCT", 0.05, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_DYNAMIC_MIN_PCT", 0.001, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_DYNAMIC_MAX_PCT", 0.50, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_ENABLE_OPENING_AUCTION", True, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_OPENING_AUCTION_MIN", 5, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_ENABLE_ILLIQUID_CHECK", True, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_ILLIQUID_SPREAD_PCT", 0.20, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_MIN_VOLUME", 1.0, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_MIN_VOLUME_RATIO", 0.10, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_CACHE_TTL_SEC", 60.0, raising=False)


def _bars(*, start: float = 100.0, count: int = 30, range_pct: float = 0.01):
    out = []
    price = float(start)
    for idx in range(count):
        close = price + (0.1 if idx % 2 == 0 else -0.05)
        high = close * (1.0 + range_pct)
        low = close * (1.0 - range_pct)
        out.append(
            {
                "ts": 1700000000 + idx * 300,
                "open": price,
                "high": high,
                "low": low,
                "close": close,
            }
        )
        price = close
    return out


def test_dynamic_spread_threshold_uses_volatility(monkeypatch):
    _set_defaults(monkeypatch)
    guard = SpreadGuard()
    bars = _bars(range_pct=0.01)
    dynamic = guard.evaluate(
        bid=100.0,
        ask=102.5,
        ltp=100.0,
        instrument="NIFTY",
        bars=bars,
        market_open=False,
    )
    static_only = guard.evaluate(
        bid=100.0,
        ask=102.5,
        ltp=100.0,
        instrument="NIFTY",
        bars=[],
        market_open=False,
    )
    assert dynamic.allowed is True
    assert dynamic.max_spread_pct is not None and dynamic.max_spread_pct > 0.01
    assert static_only.allowed is False
    assert static_only.reason_code == "WIDE_SPREAD"


def test_spread_guard_blocks_critical_volatility(monkeypatch):
    _set_defaults(monkeypatch)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_CRITICAL_VOL_PCT", 0.015, raising=False)
    guard = SpreadGuard()
    very_volatile = _bars(range_pct=0.04)
    out = guard.evaluate(
        bid=100.0,
        ask=101.0,
        ltp=100.0,
        instrument="BANKNIFTY",
        bars=very_volatile,
        market_open=False,
    )
    assert out.allowed is False
    assert out.reason_code == "VOLATILITY_CRITICAL"
    assert out.volatility_critical is True


def test_spread_guard_blocks_opening_auction_window(monkeypatch):
    _set_defaults(monkeypatch)
    guard = SpreadGuard()
    out = guard.evaluate(
        bid=100.0,
        ask=100.5,
        ltp=100.0,
        instrument="NIFTY",
        bars=[],
        market_open=True,
        minutes_since_open_override=2,
    )
    assert out.allowed is False
    assert out.reason_code == "OPENING_AUCTION_GUARD"
    assert out.opening_auction is True


def test_spread_guard_blocks_illiquid_instrument(monkeypatch):
    _set_defaults(monkeypatch)
    monkeypatch.setattr(cfg, "SPREAD_GUARD_MIN_VOLUME", 100.0, raising=False)
    guard = SpreadGuard()
    out = guard.evaluate(
        bid=100.0,
        ask=100.2,
        ltp=100.0,
        instrument="SENSEX",
        bars=[],
        market_open=False,
        volume=10.0,
        avg_volume=500.0,
    )
    assert out.allowed is False
    assert out.reason_code == "ILLIQUID_INSTRUMENT"
    assert out.illiquid is True


def test_spread_guard_caches_volatility_computation(monkeypatch):
    _set_defaults(monkeypatch)
    guard = SpreadGuard()
    bars = _bars(range_pct=0.01)
    first = guard.evaluate(
        bid=100.0,
        ask=100.8,
        ltp=100.0,
        instrument="NIFTY",
        bars=bars,
        market_open=False,
    )
    second = guard.evaluate(
        bid=100.0,
        ask=100.8,
        ltp=100.0,
        instrument="NIFTY",
        bars=bars,
        market_open=False,
    )
    stats = guard.cache_stats
    assert first.volatility_source in {"ATR", "STDDEV"}
    assert second.volatility_source in {"ATR", "STDDEV"}
    assert stats["misses"] >= 1
    assert stats["hits"] >= 1
