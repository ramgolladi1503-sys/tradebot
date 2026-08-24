from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from research.vwap_auction_state_v1.model import (
    AuctionState,
    Bar,
    DEFAULT_CONFIG,
    FeatureSnapshot,
    OptionQuote,
    SetupType,
    compute_causal_features,
    detect_signal,
    max_lots_by_total_premium_risk,
    next_bar_long_entry,
    robustness_lattice,
    select_option_contract,
)


def bar(i, close, *, high=None, low=None, ts0=None):
    ts0 = ts0 or datetime(2026, 8, 24, 9, 15)
    high = close + 0.5 if high is None else high
    low = close - 0.5 if low is None else low
    return Bar(ts=ts0 + timedelta(minutes=i), open=close - 0.1, high=high, low=low, close=close, volume=1000 + i)


def feat(i, *, state=AuctionState.TRANSITION, z=0.0, zh=None, zl=None, vwap=100.0, sigma=10.0, atr=2.0):
    ts = datetime(2026, 8, 24, 10, 0) + timedelta(minutes=i)
    return FeatureSnapshot(
        ts=ts,
        vwap=vwap,
        sigma=sigma,
        atr=atr,
        z_close=z,
        z_high=z if zh is None else zh,
        z_low=z if zl is None else zl,
        efficiency=0.5,
        slope_atr=0.0,
        outside_up_fraction=0.0,
        outside_down_fraction=0.0,
        inside_fraction=1.0,
        vwap_crossings=2,
        state=state,
    )


def test_true_volume_is_mandatory():
    bad = Bar(datetime(2026, 8, 24, 9, 15), 100, 101, 99, 100, 100, "UNIT_WEIGHT_PROXY")
    with pytest.raises(ValueError, match="authoritative"):
        compute_causal_features([bad])


def test_causal_vwap_uses_real_volume():
    bars = [
        Bar(datetime(2026, 8, 24, 9, 15), 99, 101, 99, 100, 100, "FUTURES_AUTHORITATIVE"),
        Bar(datetime(2026, 8, 24, 9, 16), 109, 111, 109, 110, 300, "FUTURES_AUTHORITATIVE"),
    ]
    f = compute_causal_features(bars, replace(DEFAULT_CONFIG, min_bars=20))
    tp0 = (101 + 99 + 100) / 3
    tp1 = (111 + 109 + 110) / 3
    assert f[-1].vwap == pytest.approx((tp0 * 100 + tp1 * 300) / 400)


def test_up_trend_can_be_classified_as_discovery():
    bars = []
    for i in range(40):
        close = 100 + i * 0.6
        bars.append(bar(i, close, high=close + 0.2, low=close - 0.2))
    f = compute_causal_features(bars)
    assert f[-1].state == AuctionState.UP_DISCOVERY


def test_failed_up_discovery_emits_buy_put():
    bars = [bar(i, 105 + i * 0.4) for i in range(7)]
    bars[-1] = bar(6, 107.0, high=107.4, low=106.6)
    bars[3] = bar(3, 108.5, high=109.0, low=108.0)
    features = [feat(i, z=.2) for i in range(7)]
    features[3] = feat(3, state=AuctionState.UP_DISCOVERY, z=1.2)
    features[-1] = feat(6, state=AuctionState.TRANSITION, z=.7, vwap=100, sigma=10, atr=2)
    s = detect_signal(bars, features)
    assert s is not None
    assert s.setup_type == SetupType.FAILED_DISCOVERY_RETURN_TO_VALUE
    assert s.direction == "BUY_PUT"
    assert s.reward_risk >= 1.5
    assert s.option_type == "PE"
    assert not s.allowed_for_live_execution


def test_discovery_pullback_continuation_emits_buy_call():
    bars = [bar(i, 100 + i) for i in range(5)]
    bars[-3] = bar(2, 110, high=111, low=109)
    bars[-2] = bar(3, 108, high=109, low=106)
    bars[-1] = bar(4, 111, high=112, low=109)
    features = [feat(i, z=0.0) for i in range(5)]
    features[-3] = feat(2, state=AuctionState.UP_DISCOVERY, z=1.3, zl=1.1)
    features[-2] = feat(3, state=AuctionState.TRANSITION, z=.8, zl=1.2)
    features[-1] = feat(4, state=AuctionState.UP_DISCOVERY, z=1.1, zl=1.0)
    s = detect_signal(bars, features)
    assert s is not None
    assert s.setup_type == SetupType.DISCOVERY_CONTINUATION
    assert s.direction == "BUY_CALL"
    assert s.reward_risk == pytest.approx(DEFAULT_CONFIG.continuation_target_r)


def test_balance_extreme_reversion_emits_buy_put_only_when_rr_is_good():
    bars = [bar(i, 100) for i in range(4)]
    bars[-1] = bar(3, 114, high=120, low=113)
    features = [feat(i, z=0.0) for i in range(4)]
    features[-2] = feat(2, state=AuctionState.BALANCE, z=.1)
    features[-1] = feat(3, state=AuctionState.TRANSITION, z=1.4, zh=2.0, vwap=100, sigma=10, atr=2)
    s = detect_signal(bars, features)
    assert s is not None
    assert s.setup_type == SetupType.BALANCE_EXTREME_REVERSION
    assert s.direction == "BUY_PUT"
    assert s.structural_target == 100


def test_contract_selection_is_buy_only_liquid_near_atm_and_causal():
    ts = datetime(2026, 8, 24, 10, 30)
    bars = [bar(i, 100 + i) for i in range(5)]
    bars[-3] = bar(2, 110, high=111, low=109)
    bars[-2] = bar(3, 108, high=109, low=106)
    bars[-1] = bar(4, 111, high=112, low=109)
    features = [feat(i, z=0.0) for i in range(5)]
    features[-3] = feat(2, state=AuctionState.UP_DISCOVERY, z=1.3, zl=1.1)
    features[-2] = feat(3, state=AuctionState.TRANSITION, z=.8, zl=1.2)
    features[-1] = replace(feat(4, state=AuctionState.UP_DISCOVERY, z=1.1, zl=1.0), ts=ts)
    bars[-1] = replace(bars[-1], ts=ts)
    signal = detect_signal(bars, features)
    assert signal and signal.direction == "BUY_CALL"
    quotes = [
        OptionQuote(ts - timedelta(seconds=15), "NIFTY_CE_111", "CE", 111, date(2026, 8, 27), 100, 101, 500, 5000),
        OptionQuote(ts - timedelta(seconds=15), "NIFTY_CE_115", "CE", 115, date(2026, 8, 27), 80, 81, 500, 5000),
        OptionQuote(ts - timedelta(seconds=15), "NIFTY_PE_111", "PE", 111, date(2026, 8, 27), 90, 91, 500, 5000),
    ]
    selected = select_option_contract(signal, quotes, underlying_price=112)
    assert selected is not None
    assert selected.symbol == "NIFTY_CE_111"
    future = quotes + [OptionQuote(ts + timedelta(minutes=1), "NIFTY_CE_111", "CE", 111, date(2026, 8, 27), 102, 103, 600, 5200)]
    fill = next_bar_long_entry(signal, selected, future)
    assert fill is not None
    assert fill.price == 103
    assert fill.ts > signal.ts


def test_zero_dte_is_separate_and_disabled_by_default():
    from research.vwap_auction_state_v1.model import SignalIntent

    ts = datetime(2026, 8, 24, 10, 30)
    signal = SignalIntent(ts, "BUY_CALL", SetupType.DISCOVERY_CONTINUATION, AuctionState.UP_DISCOVERY, 100, 99, 102, 2, "x")
    q = OptionQuote(ts - timedelta(seconds=1), "NIFTY0DTE", "CE", 100, date(2026, 8, 24), 10, 10.1, 100, 1000)
    assert select_option_contract(signal, [q], 100) is None


def test_total_premium_risk_never_exceeds_five_percent():
    lots = max_lots_by_total_premium_risk(account_equity=200_000, option_ask=100)
    assert lots == 1
    assert lots * DEFAULT_CONFIG.lot_size * 100 <= 200_000 * 0.05
    assert (lots + 1) * DEFAULT_CONFIG.lot_size * 100 > 200_000 * 0.05


def test_robustness_lattice_is_small_unique_and_predeclared():
    variants = robustness_lattice()
    assert len(variants) == 9
    assert variants[0][0] == "base"
    assert len({name for name, _ in variants}) == 9
