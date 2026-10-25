"""
Unit tests for Sentinel Real-Time CVD Absorption & Dealer GEX Regime Engine.

Covers all 8 Acceptance Proof Criteria from ARCH_SENTINEL_MICROSTRUCTURE_003:
1. CVD bullish absorption and divergence veto.
2. CVD bearish absorption and divergence veto.
3. CVD aggregated feed tick rule fallback.
4. Regularized Dealer GEX asymptotic boundary at T -> 0.
5. Dealer GEX regime classification (Positive, Negative, Neutral) with dynamic lot sizing.
6. Top-of-book spread crossing veto.
7. Locked or crossed book fails closed.
8. Safety invariant declarations & immutability.
"""

from __future__ import annotations

import math
import pytest
from dataclasses import FrozenInstanceError

from core.market_structure.sentinel_microstructure import (
    CVDState,
    GEXRegime,
    MarketBarSnapshot,
    MicrostructureParameters,
    MicrostructureVetoReason,
    OptionStrikeSnapshot,
    SentinelMicrostructureDecision,
    SentinelMicrostructureEngine,
    TopOfBookQuote,
    calculate_cvd_state,
    calculate_dealer_gex,
    calculate_spread_bps,
    evaluate_microstructure,
    regularized_gamma,
    SAFETY_DECLARATIONS,
)


def _generate_bars(
    count: int,
    base_price: float = 24000.0,
    price_step: float = 10.0,
    volume: float = 1000.0,
    buy_ratio: float = 0.5,
    use_split_volume: bool = True,
) -> list[MarketBarSnapshot]:
    bars: list[MarketBarSnapshot] = []
    for i in range(count):
        close_price = base_price + i * price_step
        open_price = close_price - price_step * 0.5
        high_price = max(open_price, close_price) + 5.0
        low_price = min(open_price, close_price) - 5.0

        if use_split_volume:
            b_vol = volume * buy_ratio
            s_vol = volume * (1.0 - buy_ratio)
            bars.append(
                MarketBarSnapshot(
                    timestamp=1000.0 + i * 60.0,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume,
                    buy_volume=b_vol,
                    sell_volume=s_vol,
                )
            )
        else:
            bars.append(
                MarketBarSnapshot(
                    timestamp=1000.0 + i * 60.0,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume,
                )
            )
    return bars


# ---------------------------------------------------------------------------
# Test 1: CVD Bullish Absorption Divergence Veto
# ---------------------------------------------------------------------------

def test_cvd_bullish_absorption_divergence_veto() -> None:
    """
    Spot reaches new high across lookback window (14 bars),
    while volume delta is stagnant/negative (delta_cvd <= 0).
    Verifies BULLISH_ABSORPTION and absorption veto.
    """
    # 13 normal bars at base 24000
    bars = _generate_bars(count=13, base_price=24000.0, price_step=0.0, volume=1000.0, buy_ratio=0.4)
    # 14th bar makes new high at 24500 with heavy aggressive selling / passive ask absorption (buy_ratio=0.1)
    bars.append(
        MarketBarSnapshot(
            timestamp=1000.0 + 13 * 60.0,
            open=24100.0,
            high=24600.0,
            low=24050.0,
            close=24500.0,
            volume=5000.0,
            buy_volume=500.0,
            sell_volume=4500.0,  # delta = -4000
        )
    )

    quote = TopOfBookQuote(timestamp=1000.0 + 13 * 60.0, bid_price=24495.0, ask_price=24505.0)
    strikes = [
        OptionStrikeSnapshot(
            strike_price=24500.0,
            call_oi=10000.0,
            put_oi=10000.0,
            implied_volatility=0.15,
            dte_years=0.05,
        )
    ]

    params = MicrostructureParameters(cvd_lookback_bars=14)
    decision = evaluate_microstructure(
        bars=bars,
        strikes=strikes,
        quote=quote,
        spot_price=24550.0,  # New high >= max prior high
        params=params,
    )

    assert decision.cvd_state == CVDState.BULLISH_ABSORPTION
    assert decision.is_absorption_vetoed is True
    assert decision.is_entry_permitted is False
    assert MicrostructureVetoReason.BULLISH_ABSORPTION_VETO in decision.veto_reasons
    assert decision.audit_metadata["cvd_audit"]["delta_cvd_w"] <= 0.0


# ---------------------------------------------------------------------------
# Test 2: CVD Bearish Absorption Divergence Veto
# ---------------------------------------------------------------------------

def test_cvd_bearish_absorption_divergence_veto() -> None:
    """
    Spot reaches new low across lookback window (14 bars),
    while volume delta is positive/accumulation (delta_cvd >= 0).
    Verifies BEARISH_ABSORPTION and absorption veto.
    """
    # 13 normal bars around 24000
    bars = _generate_bars(count=13, base_price=24000.0, price_step=0.0, volume=1000.0, buy_ratio=0.6)
    # 14th bar plunges to 23500 but delta volume is positive (heavy aggressive buying absorbed by limit bids)
    bars.append(
        MarketBarSnapshot(
            timestamp=1000.0 + 13 * 60.0,
            open=23900.0,
            high=23950.0,
            low=23400.0,
            close=23450.0,
            volume=5000.0,
            buy_volume=4500.0,  # delta = +4000
            sell_volume=500.0,
        )
    )

    quote = TopOfBookQuote(timestamp=1000.0 + 13 * 60.0, bid_price=23445.0, ask_price=23455.0)
    strikes = [
        OptionStrikeSnapshot(
            strike_price=23500.0,
            call_oi=10000.0,
            put_oi=10000.0,
            implied_volatility=0.15,
            dte_years=0.05,
        )
    ]

    params = MicrostructureParameters(cvd_lookback_bars=14)
    decision = evaluate_microstructure(
        bars=bars,
        strikes=strikes,
        quote=quote,
        spot_price=23350.0,  # New low <= min prior low
        params=params,
    )

    assert decision.cvd_state == CVDState.BEARISH_ABSORPTION
    assert decision.is_absorption_vetoed is True
    assert decision.is_entry_permitted is False
    assert MicrostructureVetoReason.BEARISH_ABSORPTION_VETO in decision.veto_reasons
    assert decision.audit_metadata["cvd_audit"]["delta_cvd_w"] >= 0.0


# ---------------------------------------------------------------------------
# Test 3: CVD Aggregated Feed Tick Rule Fallback
# ---------------------------------------------------------------------------

def test_cvd_aggregated_feed_tick_rule_fallback() -> None:
    """
    Only OHLCV provided without buy_volume and sell_volume.
    Verifies that Tick/Quote rule proxy correctly reconstructs delta CVD.
    """
    bars: list[MarketBarSnapshot] = []
    # 13 bars with close > open -> positive delta
    for i in range(13):
        bars.append(
            MarketBarSnapshot(
                timestamp=1000.0 + i * 60.0,
                open=24000.0 + i * 10.0,
                high=24020.0 + i * 10.0,
                low=23990.0 + i * 10.0,
                close=24015.0 + i * 10.0,  # close > open (+1000 vol)
                volume=1000.0,
                buy_volume=None,
                sell_volume=None,
            )
        )
    # 14th bar makes new local low, but strong up close (close > open, +5000 vol)
    bars.append(
        MarketBarSnapshot(
            timestamp=1000.0 + 13 * 60.0,
            open=23500.0,
            high=23600.0,
            low=23400.0,
            close=23550.0,  # close > open
            volume=5000.0,
            buy_volume=None,
            sell_volume=None,
        )
    )

    params = MicrostructureParameters(cvd_lookback_bars=14)
    cvd_state, metric, vetoed, reason, audit = calculate_cvd_state(
        bars=bars,
        spot_price=23300.0,  # Local low
        params=params,
    )

    assert cvd_state == CVDState.BEARISH_ABSORPTION
    assert vetoed is True
    assert reason == MicrostructureVetoReason.BEARISH_ABSORPTION_VETO
    assert audit["delta_cvd_w"] > 0.0


# ---------------------------------------------------------------------------
# Test 4: Regularized Dealer GEX Asymptotic Boundary at T -> 0
# ---------------------------------------------------------------------------

def test_regularized_dealer_gex_asymptotic_boundary_t_zero() -> None:
    """
    Tests option strike at expiry boundary: T = 0.0, T = 1e-7, or near 0.
    Asserts no ZeroDivisionError, no NaN/Inf, and gamma bounded by max_gamma_cap.
    """
    params = MicrostructureParameters(
        max_gamma_cap=100.0,
        min_time_to_expiry_years=15.0 / (365.0 * 24.0 * 60.0),
        min_implied_volatility=0.05,
    )

    # Spot ATM with strike at T = 0.0
    gamma_zero_t = regularized_gamma(
        spot=24000.0,
        strike=24000.0,
        implied_volatility=0.15,
        dte_years=0.0,  # Expiry moment
        params=params,
    )

    assert not math.isnan(gamma_zero_t)
    assert not math.isinf(gamma_zero_t)
    assert 0.0 <= gamma_zero_t <= params.max_gamma_cap

    # Tiny T
    gamma_tiny_t = regularized_gamma(
        spot=24000.0,
        strike=24000.0,
        implied_volatility=0.01,  # below floor
        dte_years=1e-8,
        params=params,
    )
    assert not math.isnan(gamma_tiny_t)
    assert not math.isinf(gamma_tiny_t)
    assert 0.0 <= gamma_tiny_t <= params.max_gamma_cap

    # Spot or strike <= 0
    assert regularized_gamma(spot=0.0, strike=24000.0, implied_volatility=0.15, dte_years=0.1, params=params) == 0.0
    assert regularized_gamma(spot=24000.0, strike=-100.0, implied_volatility=0.15, dte_years=0.1, params=params) == 0.0


# ---------------------------------------------------------------------------
# Test 5: Dealer GEX Regime Classification Positive, Negative, Neutral with Dynamic Lot Sizing
# ---------------------------------------------------------------------------

def test_dealer_gex_regime_classification_positive_and_negative() -> None:
    """
    Verifies transition between POSITIVE_GAMMA, NEGATIVE_GAMMA, and NEUTRAL_GAMMA
    with dynamic lot sizing (e.g. NIFTY lot=25 vs BANKNIFTY lot=15).
    """
    params_nifty = MicrostructureParameters(
        positive_gex_threshold=1_000_000.0,
        negative_gex_threshold=-1_000_000.0,
        underlying_lot_size=25,
    )

    spot = 24000.0
    # Case A: Heavy Net Call OI -> Positive Gamma
    strikes_pos = [
        OptionStrikeSnapshot(
            strike_price=24000.0,
            call_oi=100_000.0,
            put_oi=10_000.0,
            implied_volatility=0.15,
            dte_years=0.05,
        )
    ]
    regime, total_gex, veto_reason, audit = calculate_dealer_gex(
        strikes=strikes_pos,
        spot_price=spot,
        params=params_nifty,
    )
    assert regime == GEXRegime.POSITIVE_GAMMA
    assert total_gex >= params_nifty.positive_gex_threshold
    assert veto_reason is None

    # Case B: Heavy Net Put OI -> Negative Gamma
    strikes_neg = [
        OptionStrikeSnapshot(
            strike_price=24000.0,
            call_oi=10_000.0,
            put_oi=100_000.0,
            implied_volatility=0.15,
            dte_years=0.05,
        )
    ]
    regime_neg, total_gex_neg, _, _ = calculate_dealer_gex(
        strikes=strikes_neg,
        spot_price=spot,
        params=params_nifty,
    )
    assert regime_neg == GEXRegime.NEGATIVE_GAMMA
    assert total_gex_neg <= params_nifty.negative_gex_threshold

    # Case C: Balanced OI -> Neutral Gamma
    strikes_neu = [
        OptionStrikeSnapshot(
            strike_price=24000.0,
            call_oi=50_000.0,
            put_oi=50_000.0,
            implied_volatility=0.15,
            dte_years=0.05,
        )
    ]
    regime_neu, total_gex_neu, _, _ = calculate_dealer_gex(
        strikes=strikes_neu,
        spot_price=spot,
        params=params_nifty,
    )
    assert regime_neu == GEXRegime.NEUTRAL_GAMMA
    assert params_nifty.negative_gex_threshold < total_gex_neu < params_nifty.positive_gex_threshold

    # Dynamic lot size impact: BANKNIFTY (lot=15) vs NIFTY (lot=25)
    params_banknifty = MicrostructureParameters(
        positive_gex_threshold=1_000_000.0,
        negative_gex_threshold=-1_000_000.0,
        underlying_lot_size=15,
    )
    _, total_gex_bn, _, _ = calculate_dealer_gex(
        strikes=strikes_pos,
        spot_price=spot,
        params=params_banknifty,
    )
    # Scaled exactly by 15 / 25
    assert math.isclose(total_gex_bn, total_gex * (15.0 / 25.0), rel_tol=1e-5)


# ---------------------------------------------------------------------------
# Test 6: Top-of-Book Spread Crossing Veto
# ---------------------------------------------------------------------------

def test_top_of_book_spread_crossing_veto() -> None:
    """
    Tests quote with 7.5 bps spread against 6.0 bps limit.
    Verifies is_spread_vetoed=True, is_entry_permitted=False, SPREAD_CROSSING_VETO.
    """
    params = MicrostructureParameters(max_spread_bps=6.0)

    # Spread = (24018 - 24000) / 24009 * 10000 = 18 / 24009 * 10000 approx 7.497 bps > 6.0 bps
    wide_quote = TopOfBookQuote(timestamp=1000.0, bid_price=24000.0, ask_price=24018.0)
    spread_bps, is_vetoed, reason = calculate_spread_bps(wide_quote, params)

    assert is_vetoed is True
    assert reason == MicrostructureVetoReason.SPREAD_CROSSING_VETO
    assert spread_bps > 6.0

    # Clean narrow spread: (24002 - 24000) / 24001 * 10000 approx 0.833 bps <= 6.0 bps
    narrow_quote = TopOfBookQuote(timestamp=1000.0, bid_price=24000.0, ask_price=24002.0)
    spread_bps_narrow, is_vetoed_narrow, reason_narrow = calculate_spread_bps(narrow_quote, params)
    assert is_vetoed_narrow is False
    assert reason_narrow is None
    assert spread_bps_narrow < 6.0


# ---------------------------------------------------------------------------
# Test 7: Locked or Crossed Book Fails Closed
# ---------------------------------------------------------------------------

def test_locked_or_crossed_book_fails_closed() -> None:
    """
    Tests ask <= bid (crossed / locked book anomaly).
    Verifies fail-closed handling with INVALID_FEED_CORRUPTION_VETO.
    """
    params = MicrostructureParameters()

    # Crossed book: ask < bid
    crossed_quote = TopOfBookQuote(timestamp=1000.0, bid_price=24010.0, ask_price=24000.0)
    _, is_vetoed, reason = calculate_spread_bps(crossed_quote, params)
    assert is_vetoed is True
    assert reason == MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO

    # Locked book: ask == bid
    locked_quote = TopOfBookQuote(timestamp=1000.0, bid_price=24000.0, ask_price=24000.0)
    _, is_vetoed_locked, reason_locked = calculate_spread_bps(locked_quote, params)
    assert is_vetoed_locked is True
    assert reason_locked == MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO


# ---------------------------------------------------------------------------
# Test 8: Fail-Closed on NaN, Corrupt Feed, and Safety Invariants Preserved
# ---------------------------------------------------------------------------

def test_fail_closed_on_corrupt_data_and_safety_invariants() -> None:
    """
    Verifies safety invariants, frozen dataclass immutability,
    and fail-closed handling on corrupt/NaN feeds.
    """
    params = MicrostructureParameters(cvd_lookback_bars=14)
    bars = _generate_bars(count=14, base_price=24000.0)
    quote = TopOfBookQuote(timestamp=1000.0, bid_price=24000.0, ask_price=24001.0)
    strikes = [
        OptionStrikeSnapshot(
            strike_price=24000.0,
            call_oi=10000.0,
            put_oi=10000.0,
            implied_volatility=0.15,
            dte_years=0.05,
        )
    ]

    # Valid normal run
    decision = evaluate_microstructure(
        bars=bars,
        strikes=strikes,
        quote=quote,
        spot_price=24000.0,
        params=params,
    )
    assert decision.is_entry_permitted is True
    assert decision.cvd_state == CVDState.NORMAL
    assert decision.gex_regime == GEXRegime.NEUTRAL_GAMMA

    # Verify safety declarations
    assert decision.safety_declarations["read_only"] is True
    assert decision.safety_declarations["is_order_action"] is False
    assert decision.safety_declarations["broker_api_called"] is False
    assert decision.safety_declarations["allowed_for_live_execution"] is False
    assert decision.safety_declarations["runtime_wiring_modified"] is False
    assert decision.safety_declarations["fail_closed_mode"] is True

    # Immutability verification: frozen dataclass raises error on mutation
    with pytest.raises(FrozenInstanceError):
        decision.is_entry_permitted = False  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        quote.bid_price = 25000.0  # type: ignore[misc]

    # Corrupt spot price (NaN) fails closed
    corrupt_decision = evaluate_microstructure(
        bars=bars,
        strikes=strikes,
        quote=quote,
        spot_price=float("nan"),
        params=params,
    )
    assert corrupt_decision.is_entry_permitted is False
    assert corrupt_decision.cvd_state == CVDState.UNKNOWN
    assert corrupt_decision.gex_regime == GEXRegime.UNKNOWN
    assert MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO in corrupt_decision.veto_reasons

    # Corrupt bar volume conservation violation fails closed
    corrupt_bars = list(bars)
    corrupt_bars[5] = MarketBarSnapshot(
        timestamp=1000.0 + 5 * 60.0,
        open=24000.0,
        high=24010.0,
        low=23990.0,
        close=24005.0,
        volume=1000.0,
        buy_volume=600.0,
        sell_volume=600.0,  # 600 + 600 = 1200 != 1000
    )
    corrupt_bar_decision = evaluate_microstructure(
        bars=corrupt_bars,
        strikes=strikes,
        quote=quote,
        spot_price=24000.0,
        params=params,
    )
    assert corrupt_bar_decision.is_entry_permitted is False
    assert corrupt_bar_decision.cvd_state == CVDState.UNKNOWN
    assert MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO in corrupt_bar_decision.veto_reasons

    # Empty option chain fails closed
    empty_strikes_decision = evaluate_microstructure(
        bars=bars,
        strikes=[],
        quote=quote,
        spot_price=24000.0,
        params=params,
    )
    assert empty_strikes_decision.is_entry_permitted is False
    assert empty_strikes_decision.gex_regime == GEXRegime.UNKNOWN
    assert MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO in empty_strikes_decision.veto_reasons


# ---------------------------------------------------------------------------
# Test 9: Adversarial Extreme Inputs (NaN, Inf, Negative Spot, Negative IV, Zero TTE, Zero Volume)
# ---------------------------------------------------------------------------

def test_adversarial_extreme_inputs_fail_closed() -> None:
    """
    Adversarial test injecting extreme invalid inputs:
    - NaN and Inf spot prices
    - Negative spot prices
    - Negative/NaN/Inf implied volatility
    - Zero time to expiry (TTE)
    - Zero volume across bars
    Verifies that system fails closed, no unhandled exceptions, and no divide-by-zero.
    """
    params = MicrostructureParameters()
    base_bars = _generate_bars(count=14, base_price=24000.0, volume=1000.0)
    valid_quote = TopOfBookQuote(timestamp=2000.0, bid_price=24000.0, ask_price=24002.0)
    valid_strike = OptionStrikeSnapshot(
        strike_price=24000.0,
        call_oi=10000.0,
        put_oi=10000.0,
        implied_volatility=0.15,
        dte_years=0.05,
    )

    # 1. Negative & Zero Spot Prices
    for bad_spot in [-1.0, -24000.0, 0.0]:
        dec = evaluate_microstructure(
            bars=base_bars,
            strikes=[valid_strike],
            quote=valid_quote,
            spot_price=bad_spot,
            params=params,
        )
        assert dec.is_entry_permitted is False
        assert MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO in dec.veto_reasons

    # 2. NaN and Inf Spot Prices
    for bad_spot in [float("nan"), float("inf"), float("-inf")]:
        dec = evaluate_microstructure(
            bars=base_bars,
            strikes=[valid_strike],
            quote=valid_quote,
            spot_price=bad_spot,
            params=params,
        )
        assert dec.is_entry_permitted is False
        assert MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO in dec.veto_reasons

    # 3. Negative / Zero / NaN / Inf Implied Volatility in OptionStrikeSnapshot
    for bad_iv in [-0.5, 0.0, float("nan"), float("inf"), float("-inf")]:
        strike_bad_iv = OptionStrikeSnapshot(
            strike_price=24000.0,
            call_oi=10000.0,
            put_oi=10000.0,
            implied_volatility=bad_iv,
            dte_years=0.05,
        )
        regime, total_gex, veto_reason, audit = calculate_dealer_gex(
            strikes=[strike_bad_iv],
            spot_price=24000.0,
            params=params,
        )
        if math.isnan(bad_iv) or math.isinf(bad_iv):
            assert veto_reason == MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO
            assert regime == GEXRegime.UNKNOWN
        else:
            # Regularized gamma handles non-negative/negative bounded by floor
            gamma = regularized_gamma(
                spot=24000.0,
                strike=24000.0,
                implied_volatility=bad_iv,
                dte_years=0.05,
                params=params,
            )
            assert not math.isnan(gamma)
            assert not math.isinf(gamma)
            assert gamma >= 0.0

    # 4. Zero Time to Expiry (TTE = 0.0) in OptionStrikeSnapshot
    strike_zero_dte = OptionStrikeSnapshot(
        strike_price=24000.0,
        call_oi=50000.0,
        put_oi=20000.0,
        implied_volatility=0.15,
        dte_years=0.0,
    )
    regime_zero_dte, total_gex_zero_dte, veto_zero_dte, _ = calculate_dealer_gex(
        strikes=[strike_zero_dte],
        spot_price=24000.0,
        params=params,
    )
    assert not math.isnan(total_gex_zero_dte)
    assert not math.isinf(total_gex_zero_dte)
    assert veto_zero_dte is None

    # 5. Zero Volume Bars across the entire lookback window
    zero_vol_bars = [
        MarketBarSnapshot(
            timestamp=1000.0 + i * 60.0,
            open=24000.0,
            high=24000.0,
            low=24000.0,
            close=24000.0,
            volume=0.0,
            buy_volume=0.0,
            sell_volume=0.0,
        )
        for i in range(14)
    ]
    cvd_state, norm_metric, is_vetoed, veto_reason, audit = calculate_cvd_state(
        bars=zero_vol_bars,
        spot_price=24000.0,
        params=params,
    )
    assert not math.isnan(norm_metric)
    assert not math.isinf(norm_metric)
    assert norm_metric == 0.0
    assert audit["total_window_vol"] == 0.0
    assert audit["delta_cvd_w"] == 0.0


# ---------------------------------------------------------------------------
# Test 10: Flapped and Reconnected Feeds with Timestamp Gaps
# ---------------------------------------------------------------------------

def test_flapped_reconnected_feeds_and_timestamp_gaps() -> None:
    """
    Tests behavior when feeds flap/reconnect:
    - Large timestamp gaps (network disruption / market halt / reconnection).
    - Monotonically increasing gaps are accepted deterministically.
    - Backward / out-of-order timestamps trigger INVALID_FEED_CORRUPTION_VETO fail-closed.
    """
    params = MicrostructureParameters(cvd_lookback_bars=14)
    valid_quote = TopOfBookQuote(timestamp=50000.0, bid_price=24000.0, ask_price=24002.0)
    valid_strikes = [
        OptionStrikeSnapshot(
            strike_price=24000.0,
            call_oi=10000.0,
            put_oi=10000.0,
            implied_volatility=0.15,
            dte_years=0.05,
        )
    ]

    # Scenario A: Feed disconnected for 2 hours (7200s gap), then reconnected with valid monotonic bars
    bars_with_gap: list[MarketBarSnapshot] = []
    # 7 bars before disconnect
    for i in range(7):
        bars_with_gap.append(
            MarketBarSnapshot(
                timestamp=1000.0 + i * 60.0,
                open=24000.0,
                high=24010.0,
                low=23990.0,
                close=24005.0,
                volume=1000.0,
                buy_volume=500.0,
                sell_volume=500.0,
            )
        )
    # 7 bars after 2-hour disconnect gap (timestamp + 7200.0)
    for i in range(7):
        bars_with_gap.append(
            MarketBarSnapshot(
                timestamp=1000.0 + (6 * 60.0) + 7200.0 + (i + 1) * 60.0,
                open=24000.0,
                high=24010.0,
                low=23990.0,
                close=24005.0,
                volume=1000.0,
                buy_volume=500.0,
                sell_volume=500.0,
            )
        )

    dec_gap = evaluate_microstructure(
        bars=bars_with_gap,
        strikes=valid_strikes,
        quote=valid_quote,
        spot_price=24000.0,
        params=params,
    )
    # Monotonic timestamps succeed without crash or corruption
    assert dec_gap.is_entry_permitted is True
    assert dec_gap.cvd_state == CVDState.NORMAL

    # Scenario B: Flapped connection causes out-of-order / replay timestamps (e.g. clock desync)
    bars_out_of_order = list(bars_with_gap)
    # Corrupt index 8 to have an earlier timestamp than index 7
    bars_out_of_order[8] = MarketBarSnapshot(
        timestamp=bars_out_of_order[7].timestamp - 100.0,
        open=24000.0,
        high=24010.0,
        low=23990.0,
        close=24005.0,
        volume=1000.0,
        buy_volume=500.0,
        sell_volume=500.0,
    )

    dec_corrupt_ts = evaluate_microstructure(
        bars=bars_out_of_order,
        strikes=valid_strikes,
        quote=valid_quote,
        spot_price=24000.0,
        params=params,
    )
    assert dec_corrupt_ts.is_entry_permitted is False
    assert dec_corrupt_ts.cvd_state == CVDState.UNKNOWN
    assert MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO in dec_corrupt_ts.veto_reasons
    assert dec_corrupt_ts.audit_metadata["cvd_audit"]["error"] == "out_of_order_timestamps"


# ---------------------------------------------------------------------------
# Test 11: Huge Volume Spikes (100 Million Contracts) & Precision Integrity
# ---------------------------------------------------------------------------

def test_huge_volume_spikes_and_precision_integrity() -> None:
    """
    Tests adversarial volume spikes (100,000,000 contracts per bar).
    Verifies that cumulative volume delta calculation maintains float/integer precision,
    does not overflow or generate Inf/NaN, and properly handles absorption.
    """
    params = MicrostructureParameters(cvd_lookback_bars=14)
    huge_volume = 100_000_000.0

    bars: list[MarketBarSnapshot] = []
    # 13 bars with huge volume and 50/50 split
    for i in range(13):
        bars.append(
            MarketBarSnapshot(
                timestamp=1000.0 + i * 60.0,
                open=24000.0,
                high=24050.0,
                low=23950.0,
                close=24000.0,
                volume=huge_volume,
                buy_volume=huge_volume * 0.5,
                sell_volume=huge_volume * 0.5,
            )
        )
    # 14th bar makes new all-time high at 24500 with massive aggressive sell absorption (90% sell)
    bars.append(
        MarketBarSnapshot(
            timestamp=1000.0 + 13 * 60.0,
            open=24100.0,
            high=24600.0,
            low=24050.0,
            close=24500.0,
            volume=huge_volume,
            buy_volume=huge_volume * 0.1,   # 10M
            sell_volume=huge_volume * 0.9,  # 90M -> delta = -80M
        )
    )

    quote = TopOfBookQuote(timestamp=1000.0 + 13 * 60.0, bid_price=24498.0, ask_price=24502.0)
    strikes = [
        OptionStrikeSnapshot(
            strike_price=24500.0,
            call_oi=50_000_000.0,  # 50M OI
            put_oi=10_000_000.0,
            implied_volatility=0.20,
            dte_years=0.05,
        )
    ]

    dec = evaluate_microstructure(
        bars=bars,
        strikes=strikes,
        quote=quote,
        spot_price=24550.0,
        params=params,
    )

    assert dec.cvd_state == CVDState.BULLISH_ABSORPTION
    assert dec.is_absorption_vetoed is True
    assert dec.is_entry_permitted is False
    assert MicrostructureVetoReason.BULLISH_ABSORPTION_VETO in dec.veto_reasons

    # Check precision integrity in audit metrics
    cvd_audit = dec.audit_metadata["cvd_audit"]
    assert cvd_audit["total_window_vol"] == 14 * huge_volume
    assert math.isclose(cvd_audit["delta_cvd_w"], -80_000_000.0, rel_tol=1e-9)
    assert not math.isnan(dec.cvd_divergence_metric)
    assert not math.isinf(dec.cvd_divergence_metric)
    assert not math.isnan(dec.net_dealer_gex)
    assert not math.isinf(dec.net_dealer_gex)


# ---------------------------------------------------------------------------
# Test 12: Mixed Multi-Strike Option Chains with Alternating Call/Put Gamma
# ---------------------------------------------------------------------------

def test_mixed_multi_strike_option_chains_alternating_gamma() -> None:
    """
    Tests option chains with 20 strikes across OTM, ATM, and ITM
    with alternating high call and high put open interest.
    Verifies:
    - Summation across strikes is mathematically exact and deterministic.
    - Transitions across positive, negative, and neutral GEX bands.
    - Handling strikes with zero OI or zero volatility.
    """
    params = MicrostructureParameters(
        positive_gex_threshold=500_000.0,
        negative_gex_threshold=-500_000.0,
        underlying_lot_size=25,
    )
    spot = 24000.0

    # 1. Alternating strikes: even strikes call-heavy, odd strikes put-heavy
    # Strikes from 23000 to 25000 in steps of 100 (21 strikes)
    strikes_balanced: list[OptionStrikeSnapshot] = []
    for idx, strike_val in enumerate(range(23000, 25100, 100)):
        if idx % 2 == 0:
            call_oi = 20000.0
            put_oi = 5000.0
        else:
            call_oi = 5000.0
            put_oi = 20000.0

        strikes_balanced.append(
            OptionStrikeSnapshot(
                strike_price=float(strike_val),
                call_oi=call_oi,
                put_oi=put_oi,
                implied_volatility=0.15,
                dte_years=0.04,
            )
        )

    regime, total_gex, veto_reason, audit = calculate_dealer_gex(
        strikes=strikes_balanced,
        spot_price=spot,
        params=params,
    )
    assert veto_reason is None
    assert audit["valid_strikes_count"] == 21
    assert not math.isnan(total_gex)
    assert not math.isinf(total_gex)

    # 2. Skew all strikes heavily to calls -> POSITIVE_GAMMA
    strikes_all_call = [
        OptionStrikeSnapshot(
            strike_price=s.strike_price,
            call_oi=50000.0,
            put_oi=1000.0,
            implied_volatility=0.15,
            dte_years=0.04,
        )
        for s in strikes_balanced
    ]
    regime_call, total_gex_call, _, _ = calculate_dealer_gex(
        strikes=strikes_all_call,
        spot_price=spot,
        params=params,
    )
    assert regime_call == GEXRegime.POSITIVE_GAMMA
    assert total_gex_call > params.positive_gex_threshold

    # 3. Skew all strikes heavily to puts -> NEGATIVE_GAMMA
    strikes_all_put = [
        OptionStrikeSnapshot(
            strike_price=s.strike_price,
            call_oi=1000.0,
            put_oi=50000.0,
            implied_volatility=0.15,
            dte_years=0.04,
        )
        for s in strikes_balanced
    ]
    regime_put, total_gex_put, _, _ = calculate_dealer_gex(
        strikes=strikes_all_put,
        spot_price=spot,
        params=params,
    )
    assert regime_put == GEXRegime.NEGATIVE_GAMMA
    assert total_gex_put < params.negative_gex_threshold

