from datetime import datetime, timezone

from config import config as cfg
from core.ohlc_buffer import OhlcBuffer
from core.market_event_graph_live_ohlc_buffer import (
    record_live_source_shadow_tick,
    reset_live_source_shadow_buffer,
    shadow_ohlc_buffer,
)


def test_shadow_buffer_disabled_mode_mutates_no_state(monkeypatch):
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


def test_shadow_buffer_accepts_only_new_raw_ticks(monkeypatch):
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
