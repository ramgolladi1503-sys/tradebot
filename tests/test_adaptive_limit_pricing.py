from __future__ import annotations

from datetime import datetime

from config import config as cfg
from core.execution_engine import ExecutionEngine


class _Trade:
    def __init__(
        self,
        *,
        side: str = "BUY",
        qty: int = 10,
        symbol: str = "NIFTY",
        confidence: float = 0.8,
        regime: str = "TREND",
        trade_id: str = "T-ALPHA-1",
        run_id: str = "RUN-ALPHA-1",
    ):
        self.side = side
        self.qty = qty
        self.symbol = symbol
        self.instrument = "OPT"
        self.confidence = confidence
        self.regime = regime
        self.trade_id = trade_id
        self.run_id = run_id
        self.timestamp = datetime.now()


def _snapshot_seq(quotes):
    idx = {"i": 0}

    def _fn():
        i = idx["i"]
        if i >= len(quotes):
            return dict(quotes[-1])
        idx["i"] += 1
        return dict(quotes[i])

    return _fn


def test_queue_depth_consumption_increases_buy_aggressiveness(monkeypatch):
    monkeypatch.setattr(cfg, "EXEC_ALPHA_QUEUE_BPS", 250.0, raising=False)
    monkeypatch.setattr(cfg, "EXEC_ALPHA_MIN_TICK", 0.01, raising=False)
    engine = ExecutionEngine()
    engine.slippage_bps = 0

    thin_depth = {
        "sell": [{"price": 101.0, "quantity": 5}],
        "buy": [{"price": 100.0, "quantity": 5}],
    }
    deep_depth = {
        "sell": [{"price": 101.0, "quantity": 500}],
        "buy": [{"price": 100.0, "quantity": 500}],
    }

    limit_thin, meta_thin = engine.adaptive_limit_price(
        "BUY",
        bid=100.0,
        ask=101.0,
        depth=thin_depth,
        qty=20,
        signal_strength=0.7,
    )
    limit_deep, meta_deep = engine.adaptive_limit_price(
        "BUY",
        bid=100.0,
        ask=101.0,
        depth=deep_depth,
        qty=20,
        signal_strength=0.7,
    )
    assert limit_thin > limit_deep
    assert float(meta_thin["queue_consumption_ratio"]) > float(meta_deep["queue_consumption_ratio"])


def test_urgency_and_time_decay_raise_limit(monkeypatch):
    monkeypatch.setattr(cfg, "EXEC_ALPHA_URGENCY_BPS", 250.0, raising=False)
    monkeypatch.setattr(cfg, "EXEC_ALPHA_TIME_DECAY_BPS", 250.0, raising=False)
    monkeypatch.setattr(cfg, "EXEC_ALPHA_MIN_TICK", 0.01, raising=False)
    engine = ExecutionEngine()
    engine.slippage_bps = 0

    calm_limit, _ = engine.adaptive_limit_price(
        "BUY",
        bid=100.0,
        ask=101.0,
        signal_strength=0.2,
        elapsed_sec=0.1,
        timeout_sec=5.0,
        retry_index=0,
        max_retries=5,
    )
    urgent_limit, urgent_meta = engine.adaptive_limit_price(
        "BUY",
        bid=100.0,
        ask=101.0,
        signal_strength=0.95,
        elapsed_sec=4.5,
        timeout_sec=5.0,
        retry_index=4,
        max_retries=5,
    )
    assert urgent_limit > calm_limit
    assert float(urgent_meta["urgency_score"]) > 0.8
    assert float(urgent_meta["time_decay_aggressiveness"]) > 0.5


def test_max_slippage_guard_caps_price(monkeypatch):
    monkeypatch.setattr(cfg, "EXEC_ALPHA_MIN_TICK", 0.01, raising=False)
    engine = ExecutionEngine()
    engine.slippage_bps = 100
    limit, meta = engine.adaptive_limit_price(
        "BUY",
        bid=100.0,
        ask=101.0,
        signal_strength=1.0,
        vol_z=5.0,
        max_slippage_bps=5.0,
    )
    assert limit <= 101.0505 + 1e-9
    assert meta["max_slippage_guard_hit"] is True


def test_retry_limit_and_price_stepping_abort(monkeypatch):
    monkeypatch.setattr(cfg, "EXEC_ADAPTIVE_RETRY_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "EXEC_ADAPTIVE_MAX_RETRIES", 2, raising=False)
    monkeypatch.setattr(cfg, "EXEC_ADAPTIVE_STEP_PCT", 0.001, raising=False)
    monkeypatch.setattr(cfg, "EXEC_ADAPTIVE_RETRY_LIMIT_REASON", "retry_limit_exceeded", raising=False)
    monkeypatch.setattr(cfg, "EXEC_ALPHA_MIN_TICK", 0.01, raising=False)
    engine = ExecutionEngine()
    trade = _Trade(side="BUY", qty=5, confidence=0.9)
    quotes = [
        {"bid": 100.0, "ask": 101.0, "ts": 1700000000.0, "regime": "TREND"},
        {"bid": 100.0, "ask": 102.0, "ts": 1700000000.1, "regime": "TREND"},
        {"bid": 100.0, "ask": 103.0, "ts": 1700000000.2, "regime": "TREND"},
        {"bid": 100.0, "ask": 104.0, "ts": 1700000000.3, "regime": "TREND"},
    ]
    filled, price, report = engine.simulate_limit_fill(
        trade=trade,
        limit_price=101.0,
        snapshot_fn=_snapshot_seq(quotes),
        timeout_sec=0.05,
        poll_sec=0.0,
        max_chase_pct=0.2,
        spread_widen_pct=100.0,
        max_spread_pct=2.0,
        fill_prob=0.0,
    )
    assert filled is False
    assert price is None
    assert report["reason_if_aborted"] == "retry_limit_exceeded"
    assert int(report.get("retry_count", 0)) == 2
    events = report.get("retry_events") or []
    assert len(events) == 2
    assert float(events[0]["new_limit"]) > float(events[0]["old_limit"])


def test_abort_when_regime_changes(monkeypatch):
    monkeypatch.setattr(cfg, "EXEC_ADAPTIVE_RETRY_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "EXEC_ADAPTIVE_MAX_RETRIES", 5, raising=False)
    monkeypatch.setattr(cfg, "EXEC_ADAPTIVE_ABORT_ON_REGIME_CHANGE", True, raising=False)
    engine = ExecutionEngine()
    trade = _Trade(side="BUY", qty=5, regime="TREND")
    quotes = [
        {"bid": 100.0, "ask": 101.0, "ts": 1700000000.0, "regime": "TREND"},
        {"bid": 100.0, "ask": 101.2, "ts": 1700000000.1, "regime": "RANGE"},
    ]
    filled, _, report = engine.simulate_limit_fill(
        trade=trade,
        limit_price=100.8,
        snapshot_fn=_snapshot_seq(quotes),
        timeout_sec=0.05,
        poll_sec=0.0,
        max_chase_pct=0.2,
        spread_widen_pct=2.0,
        max_spread_pct=2.0,
        fill_prob=0.0,
    )
    assert filled is False
    assert report["reason_if_aborted"] == "regime_changed"
