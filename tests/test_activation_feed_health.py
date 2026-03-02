from config import config as cfg
from core.market_data_monitor import FeedHealth
from core.trade_activation import should_activate


def _feed_health() -> FeedHealth:
    return FeedHealth(
        index_ok_age_sec=1.0,
        option_ok_age_sec=2.5,
        index_down_no_msg_sec=3.0,
        option_down_no_msg_sec=5.0,
    )


def test_stale_quotes_block_activation_even_when_feed_ok(monkeypatch):
    monkeypatch.setattr(cfg, "LIVE_ALLOW_MANUAL_ADVISORY_ACTIVATION", False, raising=False)
    feed = _feed_health()
    base = 1000.0
    feed.on_tick(
        token=256265,
        symbol="NIFTY",
        ts_epoch=base,
        has_depth=True,
        is_index=True,
        now_epoch=base,
    )

    allowed, signal = should_activate(
        "BUY",
        "BREAKOUT",
        entry=100.0,
        ltp=101.0,
        execution_mode="LIVE",
        feed_health=feed,
        now_epoch=base,
        quote_age_sec=9.0,
        spread_pct=0.01,
        return_signal=True,
    )

    assert allowed is False
    assert signal["feed_state"] == "OK"
    assert signal["reason"].startswith("quote_age_exceeded")
    assert signal["quote_age_sec"] == 9.0
    assert signal["spread_pct"] == 0.01


def test_feed_state_ok_allows_activation(monkeypatch):
    monkeypatch.setattr(cfg, "LIVE_ALLOW_MANUAL_ADVISORY_ACTIVATION", False, raising=False)
    feed = _feed_health()
    base = 1000.0
    feed.on_tick(
        token=256265,
        symbol="NIFTY",
        ts_epoch=base,
        has_depth=True,
        is_index=True,
        now_epoch=base,
    )

    allowed, signal = should_activate(
        "BUY",
        "BREAKOUT",
        entry=100.0,
        ltp=101.0,
        execution_mode="LIVE",
        feed_health=feed,
        now_epoch=base,
        quote_age_sec=0.2,
        spread_pct=0.01,
        return_signal=True,
    )

    assert allowed is True
    assert signal["feed_state"] == "OK"
    assert signal["reason"] in {"ok", "non_live_mode", "feed_gate_unavailable"}


def test_feed_state_degraded_is_advisory_only(monkeypatch):
    feed = _feed_health()
    base = 1000.0
    # Make index stale enough for DEGRADED, but not DOWN.
    feed.on_tick(
        token=256265,
        symbol="NIFTY",
        ts_epoch=base - 2.0,
        has_depth=True,
        is_index=True,
        now_epoch=base,
    )

    blocked_live, blocked_signal = should_activate(
        "BUY",
        "BREAKOUT",
        entry=100.0,
        ltp=101.0,
        execution_mode="LIVE",
        feed_health=feed,
        now_epoch=base,
        quote_age_sec=0.4,
        spread_pct=0.01,
        advisory=False,
        return_signal=True,
    )
    assert blocked_live is False
    assert blocked_signal["feed_state"] == "DEGRADED"

    monkeypatch.setattr(cfg, "LIVE_ALLOW_MANUAL_ADVISORY_ACTIVATION", True, raising=False)
    advisory_allowed, advisory_signal = should_activate(
        "BUY",
        "BREAKOUT",
        entry=100.0,
        ltp=101.0,
        execution_mode="LIVE",
        feed_health=feed,
        now_epoch=base,
        quote_age_sec=0.4,
        spread_pct=0.01,
        advisory=True,
        return_signal=True,
    )
    assert advisory_allowed is True
    assert advisory_signal["feed_state"] == "DEGRADED"
    assert advisory_signal["manual_override_used"] is True
    assert advisory_signal["ui_flag"] == "ADVISORY_MANUAL_OVERRIDE"
