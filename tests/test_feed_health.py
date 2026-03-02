from __future__ import annotations

import time
from types import SimpleNamespace

from config import config as cfg
from core.approval_store import approve_order_intent
from core.execution_router import ExecutionRouter
from core.market_data_monitor import FeedHealth, FeedState
from core.orders.order_intent import OrderIntent
from core.trade_activation import should_activate


def _trade(trade_id: str = "T-FEED-HEALTH"):
    return SimpleNamespace(
        trade_id=trade_id,
        symbol="NIFTY",
        instrument="OPT",
        instrument_id="NIFTY|2026-02-12|25200|CE",
        instrument_token=12345,
        side="BUY",
        entry_price=102.0,
        stop_loss=98.0,
        target=108.0,
        qty=10,
        confidence=0.8,
        tradable=True,
        tradable_reasons_blocking=[],
        order_type="LIMIT",
        expiry="2026-02-12",
        strike=25200,
        right="CE",
        exchange="NFO",
        product="MIS",
    )


def _snapshot():
    return {"bid": 100.0, "ask": 101.0, "ts": time.time(), "depth": {}}


def test_feed_health_state_transitions_with_synthetic_ticks():
    feed = FeedHealth(
        index_ok_age_sec=1.0,
        option_ok_age_sec=2.5,
        index_down_no_msg_sec=3.0,
        option_down_no_msg_sec=5.0,
    )

    cold = feed.snapshot(now_epoch=100.0)
    assert cold.state == FeedState.DOWN

    feed.on_tick(
        token=111,
        symbol="NIFTY",
        ts_epoch=100.0,
        has_depth=True,
        is_index=True,
        now_epoch=100.0,
    )
    ok = feed.snapshot(now_epoch=100.5)
    assert ok.state == FeedState.OK

    degraded = feed.snapshot(now_epoch=101.6)
    assert degraded.state == FeedState.DEGRADED
    assert "index_stale_tokens" in degraded.reason

    down = feed.snapshot(now_epoch=103.2)
    assert down.state == FeedState.DOWN
    assert "no_ws_messages" in down.reason


def test_execution_router_blocks_live_entries_when_degraded_or_down(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ALLOW_LIVE_PLACEMENT", True, raising=False)
    monkeypatch.setattr(cfg, "ENFORCE_READINESS_ON_EXECUTION", False, raising=False)
    monkeypatch.setattr(cfg, "READINESS_ENFORCE_ON_EXEC", False, raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "LIVE_REQUIRE_ARMED_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "feed_health.db"), raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")

    feed = FeedHealth(
        index_ok_age_sec=1.0,
        option_ok_age_sec=2.5,
        index_down_no_msg_sec=3.0,
        option_down_no_msg_sec=5.0,
    )

    now_epoch = time.time()
    feed.on_tick(
        token=111,
        symbol="NIFTY",
        ts_epoch=now_epoch - 2.0,
        has_depth=True,
        is_index=True,
        now_epoch=now_epoch,
    )
    trade_degraded = _trade("T-FEED-DEGRADED")
    degraded_hash = OrderIntent.from_trade(trade_degraded, mode="LIVE").order_intent_hash()
    ok, reason = approve_order_intent(degraded_hash, approver_id="tester", ttl_sec=600)
    assert ok is True, reason

    router = ExecutionRouter(feed_health=feed)
    filled, price, report = router.execute(
        trade_degraded,
        bid=100.0,
        ask=101.0,
        volume=1000,
        snapshot_fn=_snapshot,
    )
    assert filled is False
    assert price is None
    assert str(report.get("reason_if_aborted", "")) == "feed_state_DEGRADED"

    reconnect_calls: list[str] = []
    feed.set_reconnect_handler(lambda reason: reconnect_calls.append(str(reason)) or True)
    feed.on_tick(
        token=111,
        symbol="NIFTY",
        ts_epoch=now_epoch - 4.0,
        has_depth=True,
        is_index=True,
        now_epoch=now_epoch - 4.0,
    )
    trade_down = _trade("T-FEED-DOWN")
    trade_down.qty = 11
    down_hash = OrderIntent.from_trade(trade_down, mode="LIVE").order_intent_hash()
    ok2, reason2 = approve_order_intent(down_hash, approver_id="tester", ttl_sec=600)
    assert ok2 is True, reason2

    router_down = ExecutionRouter(feed_health=feed)
    filled2, price2, report2 = router_down.execute(
        trade_down,
        bid=100.0,
        ask=101.0,
        volume=1000,
        snapshot_fn=_snapshot,
    )
    assert filled2 is False
    assert price2 is None
    assert str(report2.get("reason_if_aborted", "")) == "feed_state_DOWN"
    assert reconnect_calls


def test_advisory_only_allowed_in_degraded(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "LIVE_ALLOW_MANUAL_ADVISORY_ACTIVATION", True, raising=False)

    feed = FeedHealth(
        index_ok_age_sec=1.0,
        option_ok_age_sec=2.5,
        index_down_no_msg_sec=3.0,
        option_down_no_msg_sec=5.0,
    )

    base = 1000.0
    feed.on_tick(
        token=111,
        symbol="NIFTY",
        ts_epoch=base - 2.0,
        has_depth=True,
        is_index=True,
        now_epoch=base,
    )

    blocked_live, _, _ = feed.gate_live_entries(advisory_only=False, now_epoch=base)
    allowed_advisory, _, _ = feed.gate_live_entries(advisory_only=True, now_epoch=base)
    assert blocked_live is False
    assert allowed_advisory is True
    assert feed.advisory_allowed(now_epoch=base) is True

    # Trade activation should obey the same LIVE gate unless explicitly advisory.
    assert (
        should_activate(
            "BUY",
            "BREAKOUT",
            entry=100,
            ltp=101,
            feed_health=feed,
            now_epoch=base,
        )
        is False
    )
    assert (
        should_activate(
            "BUY",
            "BREAKOUT",
            entry=100,
            ltp=101,
            feed_health=feed,
            advisory=True,
            now_epoch=base,
        )
        is True
    )

    blocked_down, _, _ = feed.gate_live_entries(advisory_only=True, now_epoch=base + 4.0)
    assert blocked_down is False
    assert feed.advisory_allowed(now_epoch=base + 4.0) is False
