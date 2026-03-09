from __future__ import annotations

from core.option_liquidity_cache import (
    clear_option_liquidity_cache,
    lookup_option_liquidity,
    update_option_liquidity_cache,
)


def setup_function() -> None:
    clear_option_liquidity_cache()


def teardown_function() -> None:
    clear_option_liquidity_cache()


def test_update_option_liquidity_cache_preserves_known_values_on_incomplete_newer_snapshot() -> None:
    update_option_liquidity_cache(
        [
            {
                "symbol": "NIFTY",
                "expiry": "2026-03-12",
                "strike": 22500,
                "type": "CE",
                "instrument_token": 991001,
                "volume": 4500,
                "current_volume": 4500,
                "oi": 22000,
                "oi_change": 150,
                "snapshot_ts_epoch": 100.0,
            }
        ],
        source="unit_seed",
    )
    update_option_liquidity_cache(
        [
            {
                "symbol": "NIFTY",
                "expiry": "2026-03-12",
                "strike": 22500,
                "type": "CE",
                "instrument_token": 991001,
                "volume": None,
                "current_volume": None,
                "oi": None,
                "oi_change": None,
                "snapshot_ts_epoch": 200.0,
            }
        ],
        source="unit_incomplete",
    )

    payload = lookup_option_liquidity(
        instrument_token=991001,
        symbol="NIFTY",
        expiry="2026-03-12",
        strike=22500,
        option_type="CE",
    )

    assert payload["volume"] == 4500.0
    assert payload["current_volume"] == 4500.0
    assert payload["oi"] == 22000.0
    assert payload["oi_change"] == 150.0
    assert payload["snapshot_ts_epoch"] == 100.0


def test_update_option_liquidity_cache_ignores_older_snapshot() -> None:
    update_option_liquidity_cache(
        [
            {
                "symbol": "BANKNIFTY",
                "expiry": "2026-03-12",
                "strike": 48000,
                "type": "PE",
                "instrument_token": 991002,
                "volume": 6000,
                "oi": 31000,
                "snapshot_ts_epoch": 250.0,
            }
        ],
        source="unit_newer",
    )
    update_option_liquidity_cache(
        [
            {
                "symbol": "BANKNIFTY",
                "expiry": "2026-03-12",
                "strike": 48000,
                "type": "PE",
                "instrument_token": 991002,
                "volume": 1000,
                "oi": 5000,
                "snapshot_ts_epoch": 200.0,
            }
        ],
        source="unit_older",
    )

    payload = lookup_option_liquidity(instrument_token=991002)

    assert payload["volume"] == 6000.0
    assert payload["oi"] == 31000.0
    assert payload["snapshot_ts_epoch"] == 250.0
