"""EDGE-78 strategy parameter robustness tests.

Safety marker: stale_feed_blocks_order_intent.
"""

from __future__ import annotations

from core.breakout_candidate_generator import (
    BREAKOUT_INVALID_PARAMETER,
    build_breakout_candidate_intents,
)
from core.mean_reversion_candidate_generator import (
    MEAN_REVERSION_INVALID_PARAMETER,
    build_mean_reversion_candidate_intents,
)
from core.vwap_candidate_generator import (
    VWAP_INVALID_PARAMETER,
    build_vwap_candidate_intents,
)
from core.zero_hero_candidate_generator import (
    ZERO_HERO_INVALID_PARAMETER,
    build_zero_hero_candidate_intents,
)


def _entry_intent(report):
    return report.generated_intents[0]


def test_breakout_blocks_negative_volume_threshold():
    report = build_breakout_candidate_intents(
        {
            "instrument": "NIFTY",
            "ltp": 101.0,
            "range_high": 100.0,
            "range_low": 95.0,
            "volume_z": 1.0,
        },
        min_volume_z=-0.1,
    )
    intent = _entry_intent(report)

    assert intent.intent_type == "NO_TRADE"
    assert BREAKOUT_INVALID_PARAMETER in intent.blockers
    assert report.pool_ready is False
    assert report.to_payload()["is_order_action"] is False
    assert report.to_payload()["broker_api_called"] is False


def test_breakout_allows_zero_volume_threshold_boundary():
    report = build_breakout_candidate_intents(
        {
            "instrument": "NIFTY",
            "ltp": 101.0,
            "range_high": 100.0,
            "range_low": 95.0,
            "volume_z": 0.0,
        },
        min_volume_z=0.0,
    )
    intent = _entry_intent(report)

    assert intent.intent_type == "ENTRY"
    assert not intent.blockers
    assert report.pool_ready is True


def test_vwap_blocks_non_finite_deviation_threshold():
    report = build_vwap_candidate_intents(
        {
            "instrument": "NIFTY",
            "ltp": 103.0,
            "vwap": 100.0,
            "vwap_slope": 1.0,
        },
        min_deviation_bps=float("inf"),
    )
    intent = _entry_intent(report)

    assert intent.intent_type == "NO_TRADE"
    assert VWAP_INVALID_PARAMETER in intent.blockers
    assert intent.metadata["min_deviation_bps"] is None
    assert report.pool_ready is False


def test_vwap_blocks_negative_slope_threshold():
    report = build_vwap_candidate_intents(
        {
            "instrument": "NIFTY",
            "ltp": 103.0,
            "vwap": 100.0,
            "vwap_slope": 1.0,
        },
        min_slope=-0.1,
    )
    intent = _entry_intent(report)

    assert intent.intent_type == "NO_TRADE"
    assert VWAP_INVALID_PARAMETER in intent.blockers
    assert report.pool_ready is False


def test_mean_reversion_blocks_zero_deviation_threshold():
    report = build_mean_reversion_candidate_intents(
        {
            "instrument": "NIFTY",
            "ltp": 96.0,
            "vwap": 100.0,
            "oscillator": 1.0,
        },
        min_deviation_bps=0.0,
    )
    intent = _entry_intent(report)

    assert intent.intent_type == "NO_TRADE"
    assert MEAN_REVERSION_INVALID_PARAMETER in intent.blockers
    assert report.pool_ready is False


def test_mean_reversion_allows_zero_oscillator_threshold_boundary():
    report = build_mean_reversion_candidate_intents(
        {
            "instrument": "NIFTY",
            "ltp": 96.0,
            "vwap": 100.0,
            "oscillator": 1.0,
        },
        min_deviation_bps=10.0,
        min_oscillator_confirmation=0.0,
    )
    intent = _entry_intent(report)

    assert intent.intent_type == "ENTRY"
    assert not intent.blockers
    assert report.pool_ready is True


def test_zero_hero_blocks_inverted_premium_bounds():
    report = build_zero_hero_candidate_intents(
        {
            "instrument": "NIFTY",
            "premium": 12.0,
            "dte": 0.0,
            "underlying_momentum": 30.0,
            "volume_z": 1.0,
        },
        min_premium=25.0,
        max_premium=5.0,
    )
    intent = _entry_intent(report)

    assert intent.intent_type == "NO_TRADE"
    assert ZERO_HERO_INVALID_PARAMETER in intent.blockers
    assert report.pool_ready is False


def test_zero_hero_blocks_negative_momentum_threshold():
    report = build_zero_hero_candidate_intents(
        {
            "instrument": "NIFTY",
            "premium": 12.0,
            "dte": 0.0,
            "underlying_momentum": 30.0,
            "volume_z": 1.0,
        },
        min_momentum_bps=-1.0,
    )
    intent = _entry_intent(report)

    assert intent.intent_type == "NO_TRADE"
    assert ZERO_HERO_INVALID_PARAMETER in intent.blockers
    assert report.pool_ready is False


def test_zero_hero_allows_zero_volume_threshold_boundary():
    report = build_zero_hero_candidate_intents(
        {
            "instrument": "NIFTY",
            "premium": 12.0,
            "dte": 0.0,
            "underlying_momentum": 30.0,
            "volume_z": 0.0,
        },
        min_volume_z=0.0,
    )
    intent = _entry_intent(report)

    assert intent.intent_type == "ENTRY"
    assert not intent.blockers
    assert report.pool_ready is True
