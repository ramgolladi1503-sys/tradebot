from core.live_market_state_runtime import (
    evaluate_live_market_state,
    feature_snapshots_from_market_snapshot,
)
from core.market_state_engine_v1 import NO_TRADE, classify_market_state


def _authoritative():
    return {
        "price": 25000.0,
        "vwap": 24950.0,
        "atr": 100.0,
        "quote_age_sec": 0.5,
        "feed_authority": True,
        "session_open": True,
        "ema_fast": 24990.0,
        "ema_slow": 24920.0,
        "ema_slope_atr": 0.6,
        "structure_score": 0.8,
        "momentum_score": 0.7,
        "weighted_breadth": 0.8,
        "breadth": 0.6,
        "breadth_momentum": 0.5,
        "open_location_score": 0.4,
        "futures_confirmation_score": 0.5,
    }


def test_missing_feed_authority_fails_closed():
    row = _authoritative()
    row.pop("feed_authority")
    state = classify_market_state(row, symbol="NIFTY")
    assert state.zone == NO_TRADE
    assert state.entry_state == "BLOCKED"
    assert "FEED_AUTHORITY_UNPROVEN" in state.blockers


def test_missing_session_authority_fails_closed():
    row = _authoritative()
    row.pop("session_open")
    state = classify_market_state(row, symbol="NIFTY")
    assert state.zone == NO_TRADE
    assert state.entry_state == "BLOCKED"
    assert "SESSION_AUTHORITY_UNPROVEN" in state.blockers


def test_canonical_snapshot_adapter_maps_only_explicit_fields():
    snapshot = {
        "market_open": True,
        "symbols": {
            "NIFTY": {
                "ltp": 25000.0,
                "ohlc": {"high": 25050.0, "low": 24880.0},
                "regime": {
                    "vwap": 24950.0,
                    "atr": 100.0,
                    "ema_fast": 24990.0,
                    "ema_slow": 24920.0,
                    "weighted_breadth": 0.6,
                },
                "cross_asset": {"futures_confirmation_score": 0.5},
                "feed_health": {"quote_age_sec": 0.4, "feed_ok": True},
            }
        },
    }
    mapped = feature_snapshots_from_market_snapshot(snapshot)
    nifty = mapped["NIFTY"]
    assert nifty["price"] == 25000.0
    assert nifty["vwap"] == 24950.0
    assert nifty["atr"] == 100.0
    assert nifty["feed_authority"] is True
    assert nifty["session_open"] is True
    assert nifty["resistance"] == 25050.0
    assert nifty["support"] == 24880.0
    assert "vwap" not in mapped["BANKNIFTY"]
    assert "atr" not in mapped["BANKNIFTY"]


def test_incomplete_canonical_snapshot_is_blocked_not_inferred():
    snapshot = {
        "market_open": True,
        "symbols": {
            "NIFTY": {
                "ltp": 25000.0,
                "feed_health": {"quote_age_sec": 0.4, "feed_ok": True},
            },
            "BANKNIFTY": {
                "ltp": 55000.0,
                "feed_health": {"quote_age_sec": 0.4, "feed_ok": True},
            },
            "SENSEX": {
                "ltp": 82000.0,
                "feed_health": {"quote_age_sec": 0.4, "feed_ok": True},
            },
        },
    }
    mapped = feature_snapshots_from_market_snapshot(snapshot)
    payload = evaluate_live_market_state(mapped)
    assert payload["verdict"] == "BLOCKED"
    assert payload["cross_index"]["consensus"] == NO_TRADE
    for symbol in ("NIFTY", "BANKNIFTY", "SENSEX"):
        assert payload["indices"][symbol]["zone"] == NO_TRADE
        assert "MISSING_VWAP" in payload["indices"][symbol]["blockers"]
        assert "MISSING_ATR" in payload["indices"][symbol]["blockers"]
