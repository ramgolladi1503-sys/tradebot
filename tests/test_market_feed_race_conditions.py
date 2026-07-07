from __future__ import annotations

from config import config as cfg
import core.kite_depth_ws as ws
import core.market_data_monitor as market_data_monitor
import core.tick_store as tick_store
from core.market_data_monitor import FeedHealth, FeedState
from core.trade_activation import should_activate


INDEX_TOKEN = 256265
OPTION_TOKEN = 991001


def _wire_tick_store_to_feed(monkeypatch, tmp_path, feed: FeedHealth):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "race_ticks.sqlite"), raising=False)
    tick_store._LAST_TICK_BY_TOKEN.clear()
    tick_store._tick_window.clear()
    tick_store._LAST_TICK_EPOCH = None

    fake_clock = {"now": 0.0}
    recorded_epochs: list[float] = []
    on_tick_calls: list[dict] = []

    monkeypatch.setattr(tick_store.time, "time", lambda: float(fake_clock["now"]))
    monkeypatch.setattr(
        tick_store,
        "record_tick_epoch",
        lambda ts_epoch: recorded_epochs.append(float(ts_epoch)),
    )

    original_on_tick = market_data_monitor.FeedHealth.on_tick

    def _spy_on_tick(self, **kwargs):
        on_tick_calls.append(dict(kwargs))
        return original_on_tick(self, **kwargs)

    monkeypatch.setattr(market_data_monitor.FeedHealth, "on_tick", _spy_on_tick)

    token_map = {
        INDEX_TOKEN: {"symbol": "NIFTY", "is_index": True},
        OPTION_TOKEN: {"symbol": "NIFTY_OPT", "is_index": False},
    }

    def _fake_record_tick(
        *,
        token,
        symbol=None,
        ts_epoch=None,
        has_depth=False,
        is_index=False,
        now_epoch=None,
        monitor=None,
    ):
        token_int = int(token)
        mapped = token_map.get(token_int, {"symbol": symbol, "is_index": is_index})
        feed.on_tick(
            token=token_int,
            symbol=mapped.get("symbol"),
            ts_epoch=ts_epoch,
            has_depth=has_depth,
            is_index=bool(mapped.get("is_index")),
            now_epoch=now_epoch,
        )

    monkeypatch.setattr(market_data_monitor, "record_tick", _fake_record_tick)
    return fake_clock, recorded_epochs, on_tick_calls


def _emit_tick(clock: dict, ts_epoch: float, token: int, last_price: float) -> None:
    clock["now"] = float(ts_epoch)
    ok = tick_store.insert_tick(
        ts=ts_epoch,
        token=token,
        last_price=last_price,
        volume=1,
        oi=1,
    )
    assert ok is True


def _feed() -> FeedHealth:
    return FeedHealth(
        index_ok_age_sec=1.0,
        option_ok_age_sec=2.5,
        index_down_no_msg_sec=3.0,
        option_down_no_msg_sec=5.0,
    )


def test_index_ticks_without_option_ticks_transitions_to_degraded(monkeypatch, tmp_path):
    feed = _feed()
    clock, epochs, on_tick_calls = _wire_tick_store_to_feed(monkeypatch, tmp_path, feed)

    # Initial stream has both index and option ticks.
    _emit_tick(clock, 1000.0, INDEX_TOKEN, 25000.0)
    _emit_tick(clock, 1000.0, OPTION_TOKEN, 120.0)
    # Race: only index ticks continue.
    _emit_tick(clock, 1002.0, INDEX_TOKEN, 25020.0)
    _emit_tick(clock, 1003.0, INDEX_TOKEN, 25035.0)

    snap = feed.snapshot(now_epoch=1003.8)
    assert snap.state == FeedState.DEGRADED
    assert snap.option_stale_tokens >= 1
    assert snap.index_stale_tokens == 0
    assert "option_stale_tokens" in snap.reason
    num_epochs = len(epochs)
    assert num_epochs >= 4
    num_calls = len(on_tick_calls)
    assert num_calls >= 4


def test_option_ticks_without_index_ticks_degrades_and_blocks_activation(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "LIVE_ALLOW_MANUAL_ADVISORY_ACTIVATION", False, raising=False)
    feed = _feed()
    clock, _epochs, _on_tick_calls = _wire_tick_store_to_feed(monkeypatch, tmp_path, feed)

    # Initial stream has both index and option ticks.
    _emit_tick(clock, 2000.0, INDEX_TOKEN, 45100.0)
    _emit_tick(clock, 2000.0, OPTION_TOKEN, 210.0)
    # Race: only option ticks continue.
    _emit_tick(clock, 2001.6, OPTION_TOKEN, 212.0)
    _emit_tick(clock, 2002.4, OPTION_TOKEN, 214.0)

    snap = feed.snapshot(now_epoch=2004.0)
    assert snap.state == FeedState.DEGRADED
    assert snap.index_stale_tokens >= 1
    assert snap.option_stale_tokens == 0
    assert "index_stale_tokens" in snap.reason

    allowed, signal = should_activate(
        "BUY",
        "BREAKOUT",
        entry=100.0,
        ltp=101.0,
        execution_mode="LIVE",
        feed_health=feed,
        advisory=False,
        now_epoch=2002.9,
        quote_age_sec=0.2,
        spread_pct=0.01,
        return_signal=True,
    )
    assert allowed is False
    assert signal["feed_state"] == "DEGRADED"


def test_silent_ws_for_n_seconds_triggers_reconnect_and_feed_down_blocks_activation(monkeypatch):
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    feed = _feed()
    feed.on_tick(
        token=INDEX_TOKEN,
        symbol="NIFTY",
        ts_epoch=3000.0,
        has_depth=True,
        is_index=True,
        now_epoch=3000.0,
    )
    feed.on_tick(
        token=OPTION_TOKEN,
        symbol="NIFTY",
        ts_epoch=3000.0,
        has_depth=False,
        is_index=False,
        now_epoch=3000.0,
    )

    restart_calls: list[dict] = []
    silent_state = {"confirm_hits": 0, "last_reconnect_epoch": 0.0}
    triggered = ws._maybe_trigger_silent_reconnect(
        now_epoch=3006.0,
        current_tokens={INDEX_TOKEN, OPTION_TOKEN},
        underlying_tokens={INDEX_TOKEN},
        last_global_msg_epoch=3000.0,
        last_msg_by_token={INDEX_TOKEN: 3000.0, OPTION_TOKEN: 3000.0},
        state=silent_state,
        index_threshold_sec=1.5,
        option_threshold_sec=3.0,
        confirm_needed=1,
        backoff_min_sec=1.0,
        backoff_max_sec=10.0,
        force_full_restart_after_sec=12.0,
        restart_cb=lambda **kwargs: restart_calls.append(dict(kwargs)) or True,
    )
    assert triggered is True
    num_restarts = len(restart_calls)
    assert num_restarts == 1
    assert "silent_feed" in str(restart_calls[0].get("reason", ""))

    down_snap = feed.snapshot(now_epoch=3006.0)
    assert down_snap.state == FeedState.DOWN
    allowed, signal = should_activate(
        "BUY",
        "BREAKOUT",
        entry=100.0,
        ltp=101.0,
        execution_mode="LIVE",
        feed_health=feed,
        advisory=False,
        now_epoch=3006.0,
        quote_age_sec=0.2,
        spread_pct=0.01,
        return_signal=True,
    )
    assert allowed is False
    assert signal["feed_state"] == "DOWN"
