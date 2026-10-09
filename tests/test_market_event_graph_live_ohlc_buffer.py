from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from config import config as cfg
from core.ohlc_buffer import OhlcBuffer
from core.market_event_graph_live_ohlc_buffer import (
    configure_live_source_session_store,
    record_live_source_shadow_tick,
    reset_live_source_shadow_buffer,
    shadow_ohlc_buffer,
)
from core.market_session_store import MarketSessionStore
from core.market_event_graph_live_ohlc_buffer import get_live_source_shadow_completed_bars


@pytest.fixture(autouse=True)
def _clear_session_bar_store():
    configure_live_source_session_store(None, session_date=None)
    yield
    configure_live_source_session_store(None, session_date=None)


def test_shadow_buffer_disabled_mode_mutates_no_state(monkeypatch):
    configure_live_source_session_store(None, session_date=None)
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)

    result = record_live_source_shadow_tick(
        symbol="NIFTY",
        instrument_token=256265,
        price=25000.0,
        source_tick_epoch=100.0,
        source_type="live_websocket",
        feed_identity={"feed_session_id": "session-1", "reconnect_generation": 1},
    )

    assert result["status"] == "DISABLED"
    assert shadow_ohlc_buffer.get_bars("NIFTY") == []


def test_ohlc_buffer_without_volume_quality_keeps_legacy_accumulation():
    buffer = OhlcBuffer()
    ts = datetime(2026, 10, 2, 9, 30, tzinfo=timezone.utc)

    buffer.update_tick("NIFTY", 25000, volume=5, ts=ts)
    buffer.update_tick("NIFTY", 25001, volume=3, ts=ts)

    bar = buffer.get_bars("NIFTY")[-1]
    assert bar["volume"] == 8
    assert "volume_observation_complete" not in bar["bar_provenance"]


def test_shadow_completed_bar_view_excludes_prior_ist_session_rows():
    configure_live_source_session_store(None, session_date=None)
    reset_live_source_shadow_buffer()
    ist = ZoneInfo("Asia/Kolkata")
    prior_open = datetime(2026, 9, 7, 9, 15, tzinfo=ist)
    current_open = datetime(2026, 9, 8, 9, 15, tzinfo=ist)
    for event_time, price in (
        (prior_open, 25000.0),
        (prior_open + timedelta(minutes=1), 25001.0),
        (current_open, 25100.0),
        (current_open + timedelta(minutes=1), 25101.0),
    ):
        assert shadow_ohlc_buffer.update_tick(
            "NIFTY",
            price,
            ts=event_time,
            provenance={"source_type": "deterministic_test"},
        )["accepted"] is True

    bars_before_read = shadow_ohlc_buffer.get_bars("NIFTY")
    completed = get_live_source_shadow_completed_bars(
        "NIFTY", as_of=current_open + timedelta(minutes=1)
    )

    assert [bar["ts"] for bar in completed] == [current_open]
    assert shadow_ohlc_buffer.get_bars("NIFTY") == bars_before_read


def test_shadow_buffer_accepts_only_new_raw_ticks(monkeypatch):
    configure_live_source_session_store(None, session_date=None)
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    identity = {"feed_session_id": "session-1", "reconnect_generation": 7}
    capture = {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
    }

    first = record_live_source_shadow_tick(
        symbol="NIFTY",
        instrument_token=256265,
        price=25000.0,
        source_tick_epoch=100.0,
        source_type="live_websocket",
        payload_mode="full",
            feed_identity=identity, **capture,
    )
    repeated = record_live_source_shadow_tick(
        symbol="NIFTY",
        instrument_token=256265,
        price=25001.0,
        source_tick_epoch=100.0,
        source_type="live_websocket",
        payload_mode="full",
            feed_identity=identity, **capture,
    )

    assert first["accepted"] is True
    assert repeated["status"] == "STALE_OR_REPEATED_TICK"
    bars = shadow_ohlc_buffer.get_completed_bars("NIFTY", as_of=datetime.fromtimestamp(180.0, tz=timezone.utc))
    assert [bar["close"] for bar in bars] == [25000.0]
    provenance = bars[-1]["bar_provenance"]
    assert provenance["live_feed_session_id"] == "session-1"
    assert provenance["reconnect_generation"] == 7
    assert provenance["instrument_token"] == 256265


def test_shadow_volume_uses_cumulative_deltas_and_marks_baseline_incomplete(monkeypatch):
    configure_live_source_session_store(None, session_date=None)
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    identity = {"feed_session_id": "session-1", "reconnect_generation": 7}
    capture = {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
    }
    args = dict(symbol="NIFTY", instrument_token=256265, source_type="live_websocket", feed_identity=identity, **capture)

    first = record_live_source_shadow_tick(price=25000, source_tick_epoch=100, cumulative_volume=1000, **args)
    second = record_live_source_shadow_tick(price=25001, source_tick_epoch=101, cumulative_volume=1005, **args)
    repeated = record_live_source_shadow_tick(price=25002, source_tick_epoch=102, cumulative_volume=1005, **args)

    assert first["accepted"] and second["accepted"] and repeated["accepted"]
    bar = shadow_ohlc_buffer.get_bars("NIFTY")[-1]
    assert bar["volume"] is None  # first tick lacked a baseline; unknown stays unknown for this minute
    provenance = bar["bar_provenance"]
    assert provenance["volume_observation_complete"] is False
    assert provenance["volume_source"] == "kite_cumulative_day_volume"
    assert provenance["volume_delta_status"] == "DELTA_OBSERVED"
    assert provenance["volume_is_estimate"] is True


def test_shadow_volume_counts_deltas_only_after_a_complete_baseline(monkeypatch):
    configure_live_source_session_store(None, session_date=None)
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    identity = {"feed_session_id": "session-1", "reconnect_generation": 7}
    capture = {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
    }
    args = dict(symbol="NIFTY", instrument_token=256265, source_type="live_websocket", feed_identity=identity, **capture)

    record_live_source_shadow_tick(price=25000, source_tick_epoch=100, cumulative_volume=1000, **args)
    second = record_live_source_shadow_tick(price=25001, source_tick_epoch=110, cumulative_volume=1005, **args)
    third = record_live_source_shadow_tick(price=25002, source_tick_epoch=111, cumulative_volume=1008, **args)

    assert second["volume_delta_status"] == "DELTA_OBSERVED"
    assert third["volume_delta_status"] == "DELTA_OBSERVED"
    bars = shadow_ohlc_buffer.get_bars("NIFTY")
    assert len(bars) == 1
    assert bars[-1]["volume"] is None  # unknown baseline poisons the first minute
    assert bars[-1]["bar_provenance"]["volume_observation_complete"] is False


def test_shadow_volume_attributes_cross_minute_delta_as_estimate(monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    capture = {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
        "feed_identity": {"feed_session_id": "session-1", "reconnect_generation": 7},
    }
    record_live_source_shadow_tick(
        symbol="NIFTY", instrument_token=256265, price=25000, source_tick_epoch=100,
        source_type="live_websocket", cumulative_volume=1000, **capture,
    )
    record_live_source_shadow_tick(
        symbol="NIFTY", instrument_token=256265, price=25001, source_tick_epoch=161,
        source_type="live_websocket", cumulative_volume=1005, **capture,
    )
    record_live_source_shadow_tick(
        symbol="NIFTY", instrument_token=256265, price=25002, source_tick_epoch=162,
        source_type="live_websocket", cumulative_volume=1008, **capture,
    )

    bars = shadow_ohlc_buffer.get_bars("NIFTY")
    assert bars[0]["volume"] is None
    assert bars[1]["volume"] == 8.0
    assert bars[1]["bar_provenance"]["volume_observation_complete"] is True
    assert bars[1]["bar_provenance"]["volume_attribution"] == "CURRENT_SOURCE_TICK_MINUTE_ESTIMATE"
    assert bars[1]["bar_provenance"]["volume_is_estimate"] is True


def test_shadow_volume_regression_rebaselines_and_keeps_price_tick(monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    identity = {"feed_session_id": "session-1", "reconnect_generation": 7}
    capture = {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
    }
    args = dict(symbol="NIFTY", instrument_token=256265, source_type="live_websocket", feed_identity=identity, **capture)

    record_live_source_shadow_tick(price=25000, source_tick_epoch=100, cumulative_volume=1000, **args)
    result = record_live_source_shadow_tick(price=24999, source_tick_epoch=110, cumulative_volume=3, **args)
    subsequent = record_live_source_shadow_tick(price=24998, source_tick_epoch=111, cumulative_volume=5, **args)

    assert result["accepted"] is True
    assert result["volume_delta_status"] == "CUMULATIVE_REGRESSION_REBASELINE"
    assert subsequent["volume_delta_status"] == "DELTA_OBSERVED"
    bars = shadow_ohlc_buffer.get_bars("NIFTY")
    assert bars[-1]["volume"] is None
    assert bars[-1]["bar_provenance"]["volume_observation_complete"] is False


def test_reconnect_generation_change_rebaselines_volume(monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    capture = {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
    }
    record_live_source_shadow_tick(
        symbol="NIFTY", instrument_token=256265, price=25000, source_tick_epoch=100,
        source_type="live_websocket", cumulative_volume=1000,
        feed_identity={"feed_session_id": "session-1", "feed_epoch": 3, "reconnect_generation": 7}, **capture,
    )
    after_reconnect = record_live_source_shadow_tick(
        symbol="NIFTY", instrument_token=256265, price=25001, source_tick_epoch=110,
        source_type="live_websocket", cumulative_volume=1200,
        feed_identity={"feed_session_id": "session-1", "feed_epoch": 3, "reconnect_generation": 8}, **capture,
    )

    assert after_reconnect["accepted"] is True
    assert after_reconnect["volume_delta_status"] == "BASELINE_REQUIRED"
    bars = shadow_ohlc_buffer.get_bars("NIFTY")
    assert len(bars) == 1
    assert bars[0]["volume"] is None
    assert bars[0]["bar_provenance"]["reconnect_generation"] == 8


def test_invalid_volume_does_not_reject_price_tick_or_advance_baseline(monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    capture = {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
        "feed_identity": {"feed_session_id": "session-1", "reconnect_generation": 7},
    }
    baseline = record_live_source_shadow_tick(
        symbol="NIFTY", instrument_token=256265, price=25000, source_tick_epoch=100,
        source_type="live_websocket", cumulative_volume=1000, **capture,
    )
    invalid = record_live_source_shadow_tick(
        symbol="NIFTY", instrument_token=256265, price=25001, source_tick_epoch=101,
        source_type="live_websocket", cumulative_volume=float("nan"), **capture,
    )
    invalid_provenance = dict(shadow_ohlc_buffer.get_bars("NIFTY")[-1]["bar_provenance"])
    following = record_live_source_shadow_tick(
        symbol="NIFTY", instrument_token=256265, price=25002, source_tick_epoch=102,
        source_type="live_websocket", cumulative_volume=1005, **capture,
    )

    assert baseline["accepted"] is True
    assert invalid["accepted"] is True
    assert invalid["volume_observation_complete"] is False
    assert following["accepted"] is True
    assert following["volume_delta_status"] == "DELTA_OBSERVED"
    assert shadow_ohlc_buffer.get_bars("NIFTY")[-1]["close"] == 25002
    assert shadow_ohlc_buffer.get_bars("NIFTY")[-1]["volume"] is None
    assert invalid_provenance["volume_cumulative_day_value"] is None
    assert invalid_provenance["volume_delta_status"] == "MISSING_OR_INVALID_CUMULATIVE"


def test_shadow_buffer_preserves_live_provenance_fields(monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    identity = {"feed_session_id": "session-1", "reconnect_generation": 7}
    capture = {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
        "packet_kind": "INDEX_FULL",
    }

    result = record_live_source_shadow_tick(
        symbol="NIFTY",
        instrument_token=256265,
        price=25000.0,
        source_tick_epoch=100.0,
        source_type="live_websocket",
        payload_mode="full",
        feed_identity=identity,
        **capture,
    )

    assert result["accepted"] is True
    bars = shadow_ohlc_buffer.get_bars("NIFTY")
    provenance = bars[-1]["bar_provenance"]
    assert provenance["provider"] == "kite"
    assert provenance["token_domain"] == "kite_instrument_token"
    assert provenance["universe_hash"] == "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371"
    assert provenance["symbol"] == "NIFTY"
    assert provenance["packet_kind"] == "INDEX_FULL"


def test_shadow_buffer_preserves_identity_on_same_minute_updates(monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    identity = {"feed_session_id": "session-1", "reconnect_generation": 7}
    capture = {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
        "packet_kind": "INDEX_QUOTE",
    }

    first = record_live_source_shadow_tick(
        symbol="NIFTY",
        instrument_token=256265,
        price=25000.0,
        source_tick_epoch=100.0,
        source_type="live_websocket",
        payload_mode="quote",
        feed_identity=identity,
        **capture,
    )
    second = record_live_source_shadow_tick(
        symbol="NIFTY",
        instrument_token=256265,
        price=25001.0,
        source_tick_epoch=101.0,
        source_type="live_websocket",
        payload_mode="full",
        packet_kind="INDEX_FULL",
        feed_identity=identity,
        provider="kite",
        token_domain="kite_instrument_token",
        universe_hash="fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
    )

    assert first["accepted"] is True
    assert second["accepted"] is True
    provenance = shadow_ohlc_buffer.get_bars("NIFTY")[-1]["bar_provenance"]
    assert provenance["provider"] == "kite"
    assert provenance["token_domain"] == "kite_instrument_token"
    assert provenance["universe_hash"] == "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371"
    assert provenance["symbol"] == "NIFTY"
    assert provenance["packet_kind"] == "INDEX_FULL"
    assert provenance["payload_mode"] == "full"


def test_shadow_buffer_conflicting_live_identity_fails_closed(monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    initial = shadow_ohlc_buffer.update_tick(
        "NIFTY",
        25000.0,
        volume=5.0,
        ts=datetime.fromtimestamp(100.0, tz=timezone.utc),
        provenance={
            "source_type": "live_websocket",
            "live_feed_session_id": "session-1",
            "reconnect_generation": 7,
            "instrument_token": 256265,
            "payload_mode": "full",
            "provider": "kite",
            "token_domain": "kite_instrument_token",
            "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
            "symbol": "NIFTY",
            "packet_kind": "INDEX_FULL",
        },
    )
    conflict = shadow_ohlc_buffer.update_tick(
        "NIFTY",
        25001.0,
        volume=None,
        ts=datetime.fromtimestamp(101.0, tz=timezone.utc),
        provenance={
            "source_type": "live_websocket",
            "live_feed_session_id": "session-1",
            "reconnect_generation": 7,
            "instrument_token": 256265,
            "payload_mode": "full",
            "provider": "other",
            "token_domain": "kite_instrument_token",
            "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
            "symbol": "NIFTY",
            "packet_kind": "INDEX_FULL",
            "volume_observation_complete": False,
        },
    )

    assert initial["accepted"] is True
    assert conflict["accepted"] is False
    assert conflict["status"] == "PROVENANCE_IDENTITY_MISMATCH"
    assert conflict["field"] == "provider"
    provenance = shadow_ohlc_buffer.get_bars("NIFTY")[-1]["bar_provenance"]
    assert provenance["provider"] == "kite"
    assert shadow_ohlc_buffer.get_bars("NIFTY")[-1]["volume"] == 5.0


def test_shadow_buffer_accepts_generic_ticks_without_provenance(monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)

    result = shadow_ohlc_buffer.update_tick(
        "GENERIC",
        100.0,
        ts=datetime.fromtimestamp(100.0, tz=timezone.utc),
    )

    assert result["accepted"] is True
    provenance = shadow_ohlc_buffer.get_bars("GENERIC")[-1]["bar_provenance"]
    assert provenance["source_type"] == "unknown"
    assert provenance["provider"] is None
    assert provenance["token_domain"] is None
    assert provenance["universe_hash"] is None
    assert provenance["symbol"] is None
    assert provenance["packet_kind"] is None


def test_shadow_buffer_historical_seed_behavior_remains_unchanged():
    reset_live_source_shadow_buffer()
    seeded = shadow_ohlc_buffer.seed_bars(
        "SEED",
        [
            {
                "date": datetime.fromtimestamp(60.0, tz=timezone.utc),
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
                "volume": 12,
            }
        ],
    )

    assert seeded["accepted"] is True
    assert seeded["status"] == "SEEDED"
    provenance = shadow_ohlc_buffer.get_bars("SEED")[-1]["bar_provenance"]
    assert provenance["historical_seed"] is True
    assert "provider" not in provenance
    assert "token_domain" not in provenance
    assert "universe_hash" not in provenance
    assert "symbol" not in provenance
    assert "packet_kind" not in provenance


def test_shadow_buffer_persists_completed_bar_and_restores_same_session_only(tmp_path, monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    persisted_events = []
    monkeypatch.setattr(
        "core.candle_pipeline_diagnostics.emit_candle_pipeline_event",
        lambda **event: persisted_events.append(event),
    )
    session_date = "2026-10-02"
    db_path = tmp_path / "session.sqlite"
    store = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    start = datetime(2026, 10, 2, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    configure_live_source_session_store(
        store, session_date=session_date, symbols=("NIFTY",), restore_as_of=start,
    )
    identity = {"feed_session_id": "capture-1", "feed_epoch": 0, "reconnect_generation": 1}
    capture = {
        "provider": "kite", "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
    }
    args = dict(symbol="NIFTY", instrument_token=256265, source_type="live_websocket", **capture)

    first = record_live_source_shadow_tick(
        **args, price=25000, source_tick_epoch=(start + timedelta(seconds=10)).timestamp(),
        feed_identity=identity, cumulative_volume=100,
    )
    same_minute = record_live_source_shadow_tick(
        **args, price=25001, source_tick_epoch=(start + timedelta(seconds=20)).timestamp(),
        feed_identity=identity, cumulative_volume=105,
    )
    next_minute = record_live_source_shadow_tick(
        **args, price=25002, source_tick_epoch=(start + timedelta(minutes=1)).timestamp(),
        feed_identity=identity, cumulative_volume=110,
    )
    assert first["accepted"] and same_minute["accepted"] and next_minute["accepted"]
    # The WebSocket callback only updates memory; persistence is performed by
    # the observer's completed-bar read path, outside the tick callback.
    assert store.get_bars(
        "NIFTY", as_of=start + timedelta(minutes=1), timeframe="1m", session_date=session_date,
    ) == []
    get_live_source_shadow_completed_bars("NIFTY", as_of=start + timedelta(minutes=1))
    durable_event = next(
        event for event in reversed(persisted_events)
        if event.get("producer") == "core.market_event_graph_live_ohlc_buffer"
    )
    assert durable_event["bar_state"] == "COMPLETED_DURABLE"
    assert durable_event["details"]["persistence_latency_ms"] >= 0
    persisted = store.get_bars(
        "NIFTY", as_of=start + timedelta(minutes=1), timeframe="1m", session_date=session_date,
    )
    assert len(persisted) == 1
    assert persisted[0]["volume"] is None
    assert persisted[0]["bar_provenance"]["durable_persisted"] is True

    reopened = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    configure_live_source_session_store(
        reopened, session_date=session_date, symbols=("NIFTY",),
        restore_as_of=start + timedelta(minutes=1, seconds=30),
    )
    second_identity = {"feed_session_id": "capture-2", "feed_epoch": 1, "reconnect_generation": 1}
    restarted = record_live_source_shadow_tick(
        **args, price=25003, source_tick_epoch=(start + timedelta(minutes=1, seconds=30)).timestamp(),
        feed_identity=second_identity, cumulative_volume=5,
    )
    assert restarted["accepted"] is True
    bars = shadow_ohlc_buffer.get_bars("NIFTY")
    recovered = [bar for bar in bars if bar["ts"] == start]
    assert len(recovered) == 1
    assert recovered[0]["volume"] is None
    assert recovered[0]["bar_provenance"]["recovered_completed_bar"] is True
    assert recovered[0]["bar_provenance"]["live_feed_session_id"] == "capture-1"
    assert all(bar["ts"].date().isoformat() == session_date for bar in bars)
    from core.market_event_graph_live_runtime_bridge import _bar_has_live_provenance
    accepted, reason = _bar_has_live_provenance(
        recovered[0], expected_symbol="NIFTY", expected_token=256265,
        subscription={"feed_session_id": "capture-2", "feed_epoch": 1},
    )
    assert accepted is False
    assert reason == "FEED_SESSION_ID_MISMATCH"

    # The event-time completion cutoff durably closes the current 09:16 bar.
    get_live_source_shadow_completed_bars("NIFTY", as_of=start + timedelta(minutes=2))
    late_tick = record_live_source_shadow_tick(
        **args, price=25004, source_tick_epoch=(start + timedelta(minutes=1, seconds=45)).timestamp(),
        feed_identity=second_identity, cumulative_volume=7,
    )
    assert late_tick["status"] == "LATE_TICK_AFTER_DURABLE_FINALIZATION"
    assert len(reopened.get_bars(
        "NIFTY", as_of=start + timedelta(minutes=2), timeframe="1m", session_date=session_date,
    )) == 2


@pytest.mark.parametrize(
    ("first_tick", "next_tick", "expected_bar"),
    (
        (
            datetime(2026, 10, 5, 9, 14, 10, tzinfo=ZoneInfo("Asia/Kolkata")),
            datetime(2026, 10, 5, 9, 15, 10, tzinfo=ZoneInfo("Asia/Kolkata")),
            datetime(2026, 10, 5, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata")),
        ),
        (
            datetime(2026, 10, 5, 15, 29, 10, tzinfo=ZoneInfo("Asia/Kolkata")),
            datetime(2026, 10, 5, 15, 30, 10, tzinfo=ZoneInfo("Asia/Kolkata")),
            datetime(2026, 10, 5, 15, 29, tzinfo=ZoneInfo("Asia/Kolkata")),
        ),
    ),
)
def test_out_of_session_completed_bar_is_skipped_without_ending_observation(
    tmp_path, monkeypatch, first_tick, next_tick, expected_bar,
):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    events = []
    monkeypatch.setattr(
        "core.candle_pipeline_diagnostics.emit_candle_pipeline_event",
        lambda **event: events.append(event),
    )
    session_date = "2026-10-05"
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    configure_live_source_session_store(
        store,
        session_date=session_date,
        symbols=("NIFTY",),
        restore_as_of=first_tick,
    )
    identity = {"feed_session_id": "session-1", "feed_epoch": 0, "reconnect_generation": 1}
    capture = {
        "symbol": "NIFTY",
        "instrument_token": 256265,
        "source_type": "live_websocket",
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
        "feed_identity": identity,
    }
    assert record_live_source_shadow_tick(
        **capture, price=25000.0, source_tick_epoch=first_tick.timestamp(),
    )["accepted"] is True
    assert record_live_source_shadow_tick(
        **capture, price=25001.0, source_tick_epoch=next_tick.timestamp(),
    )["accepted"] is True

    cutoff = next_tick + timedelta(seconds=60)
    completed = get_live_source_shadow_completed_bars("NIFTY", as_of=cutoff)
    durable = store.get_bars(
        "NIFTY", as_of=cutoff, timeframe="1m", session_date=session_date,
    )

    assert [bar["ts"] for bar in completed] == [expected_bar]
    assert [bar["ts"] for bar in durable] == [expected_bar]
    skipped = [event for event in events if event.get("stage") == "T5_BAR_SKIPPED_OUTSIDE_SESSION"]
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "OUTSIDE_REGULAR_SESSION"
    assert skipped[0]["bar_state"] == "SKIPPED"


def test_unexpected_completed_bar_persistence_failure_still_fails_closed(monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    start = datetime(2026, 10, 5, 9, 15, 10, tzinfo=ZoneInfo("Asia/Kolkata"))

    class FailingStore:
        def get_bars(self, *args, **kwargs):
            return []

        def persist_completed_bar(self, *args, **kwargs):
            return {"status": "WRITE_FAILED", "persisted": False}

    configure_live_source_session_store(
        FailingStore(), session_date="2026-10-05", symbols=("NIFTY",), restore_as_of=start,
    )
    capture = {
        "symbol": "NIFTY",
        "instrument_token": 256265,
        "source_type": "live_websocket",
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
        "feed_identity": {"feed_session_id": "session-1", "feed_epoch": 0, "reconnect_generation": 1},
    }
    assert record_live_source_shadow_tick(
        **capture, price=25000.0, source_tick_epoch=start.timestamp(),
    )["accepted"] is True
    assert record_live_source_shadow_tick(
        **capture, price=25001.0, source_tick_epoch=(start + timedelta(minutes=1)).timestamp(),
    )["accepted"] is True

    with pytest.raises(RuntimeError, match="COMPLETED_BAR_PERSISTENCE_FAILED:WRITE_FAILED"):
        get_live_source_shadow_completed_bars(
            "NIFTY", as_of=start + timedelta(minutes=2),
        )


def test_shadow_buffer_rejects_replay_fixture_persistence(tmp_path, monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    start = datetime(2026, 10, 2, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    configure_live_source_session_store(
        store, session_date="2026-10-02", symbols=("NIFTY",), restore_as_of=start,
    )
    identity = {"feed_session_id": "test-feed", "feed_epoch": 0, "reconnect_generation": 1}
    capture = {
        "provider": "kite", "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
    }
    args = dict(symbol="NIFTY", instrument_token=256265, source_type="deterministic_test", feed_identity=identity, **capture)
    assert record_live_source_shadow_tick(
        **args, price=25000, source_tick_epoch=(start + timedelta(seconds=1)).timestamp(), cumulative_volume=100,
    )["accepted"] is True
    assert record_live_source_shadow_tick(
        **args, price=25001, source_tick_epoch=(start + timedelta(minutes=1)).timestamp(), cumulative_volume=101,
    )["accepted"] is True
    assert store.get_bars("NIFTY", as_of=start + timedelta(minutes=2), session_date="2026-10-02") == []


def test_shadow_buffer_restore_is_trading_date_scoped(tmp_path, monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    start = datetime(2026, 10, 2, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    db_path = tmp_path / "session.sqlite"
    store = MarketSessionStore(db_path=db_path, report_root=tmp_path / "reports")
    store.persist_completed_bar("NIFTY", {
        "ts": start, "open": 25000.0, "high": 25001.0, "low": 24999.0,
        "close": 25000.5, "volume": None,
        "bar_provenance": {"source_type": "live_websocket", "live_feed_session_id": "prior"},
    }, completed_as_of=start + timedelta(minutes=1))
    next_day = datetime(2026, 10, 3, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    capture = {
        "symbol": "NIFTY", "instrument_token": 256265, "source_type": "live_websocket",
        "provider": "kite", "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
        "feed_identity": {"feed_session_id": "next-day", "feed_epoch": 2, "reconnect_generation": 1},
    }
    configure_live_source_session_store(
        store, session_date="2026-10-03", symbols=("NIFTY",), restore_as_of=next_day,
    )
    result = record_live_source_shadow_tick(
        **capture, price=25010.0, source_tick_epoch=(next_day + timedelta(seconds=1)).timestamp(),
    )
    assert result["accepted"] is True
    assert [bar["ts"].date().isoformat() for bar in shadow_ohlc_buffer.get_bars("NIFTY")] == ["2026-10-03"]


def test_shadow_buffer_rejects_tick_outside_configured_store_session(tmp_path, monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    session_start = datetime(2026, 10, 2, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    store = MarketSessionStore(db_path=tmp_path / "session.sqlite", report_root=tmp_path / "reports")
    configure_live_source_session_store(
        store, session_date="2026-10-02", symbols=("NIFTY",), restore_as_of=session_start,
    )

    result = record_live_source_shadow_tick(
        symbol="NIFTY", instrument_token=256265, price=25010.0,
        source_tick_epoch=(session_start + timedelta(days=1, seconds=1)).timestamp(),
        source_type="live_websocket", provider="kite", token_domain="kite_instrument_token",
        universe_hash="fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
        feed_identity={"feed_session_id": "next-day", "feed_epoch": 2, "reconnect_generation": 1},
    )

    assert result["accepted"] is False
    assert result["status"] == "SESSION_DATE_MISMATCH"
    assert shadow_ohlc_buffer.get_bars("NIFTY") == []


def test_shadow_buffer_deduplicates_already_persisted_bars_across_provenance_shift(tmp_path, monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    ist = ZoneInfo("Asia/Kolkata")
    base = datetime(2026, 10, 2, 9, 15, tzinfo=ist)
    store = MarketSessionStore(db_path=tmp_path / "dedup.sqlite", report_root=tmp_path / "reports")
    configure_live_source_session_store(
        store, session_date="2026-10-02", symbols=("NIFTY",), restore_as_of=base,
    )

    capture = {
        "symbol": "NIFTY", "instrument_token": 256265, "source_type": "live_websocket",
        "provider": "kite", "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
        "feed_identity": {"feed_session_id": "sess-1", "feed_epoch": 1, "reconnect_generation": 1},
    }
    record_live_source_shadow_tick(**capture, price=25000.0, source_tick_epoch=(base + timedelta(seconds=10)).timestamp())
    # Advance to next minute to complete the first bar
    record_live_source_shadow_tick(**capture, price=25050.0, source_tick_epoch=(base + timedelta(seconds=70)).timestamp())

    cutoff = base + timedelta(minutes=2)
    # First persist
    res1 = get_live_source_shadow_completed_bars("NIFTY", as_of=cutoff)
    assert len(res1) == 2

    # Simulate in-memory bar provenance change (e.g. metadata shift or re-fetch)
    bars = shadow_ohlc_buffer.get_bars("NIFTY")
    assert len(bars) >= 2
    # Clear durable_persisted flag to simulate object re-creation with different provenance
    bars[0]["bar_provenance"]["durable_persisted"] = False
    bars[0]["bar_provenance"]["volume_cumulative_day_value"] = 999999.0

    # Second persist must not crash with SessionMemoryConflict, but safely detect already durable
    res2 = get_live_source_shadow_completed_bars("NIFTY", as_of=cutoff)
    assert len(res2) == 2

