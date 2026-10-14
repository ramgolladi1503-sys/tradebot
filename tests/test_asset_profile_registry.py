"""Proof tests for AssetProfile contract and SENSEX mathematical scaling invariants."""
from __future__ import annotations

import pytest
from core.asset_profile_registry import ASSET_REGISTRY, get_asset_profile, AssetProfile


def test_asset_profile_defaults_safely_to_nifty():
    """Verify default fallback is always NIFTY (zero regression risk)."""
    p_none = get_asset_profile(None)
    assert p_none.ticker == "NIFTY"
    assert p_none.strike_step == 50
    assert p_none.target_scalp_pts == 15.0

    p_empty = get_asset_profile("")
    assert p_empty.ticker == "NIFTY"

    p_unknown = get_asset_profile("UNKNOWN_ASSET")
    assert p_unknown.ticker == "NIFTY"


def test_nifty_profile_invariants():
    """Verify NIFTY profile preserves exact operational constants."""
    nifty = get_asset_profile("NIFTY")
    assert nifty.ticker == "NIFTY"
    assert nifty.index_instrument_key == "NSE_INDEX|Nifty 50"
    assert nifty.fo_exchange_prefix == "NSE_FO"
    assert nifty.strike_step == 50
    assert nifty.target_scalp_pts == 15.0
    assert nifty.target_runner_pts == 30.0
    assert nifty.initial_sl_pts == 12.0
    assert nifty.ratchet_trigger_pts == 8.0
    assert nifty.ratchet_lock_pts == 4.0
    assert nifty.breakeven_trigger_pts == 12.0
    assert nifty.breakeven_lock_pts == 1.0
    assert nifty.or_min_expansion_width == 70.0
    assert nifty.macro_exhaustion_cap_pts == 300.0
    assert nifty.max_spread_pct == 0.04
    assert nifty.weekly_expiry_day_of_week == 1  # Tuesday


def test_sensex_profile_mathematical_scaling():
    """Verify SENSEX profile scales proportionally (approx 3.25x) with BSE grid."""
    sensex = get_asset_profile("SENSEX")
    assert sensex.ticker == "SENSEX"
    assert sensex.index_instrument_key == "BSE_INDEX|SENSEX"
    assert sensex.fo_exchange_prefix == "BSE_FO"
    assert sensex.strike_step == 100
    assert sensex.target_scalp_pts == 50.0
    assert sensex.target_runner_pts == 100.0
    assert sensex.initial_sl_pts == 40.0
    assert sensex.ratchet_trigger_pts == 25.0
    assert sensex.ratchet_lock_pts == 12.0
    assert sensex.breakeven_trigger_pts == 40.0
    assert sensex.breakeven_lock_pts == 3.0
    assert sensex.or_min_expansion_width == 220.0
    assert sensex.macro_exhaustion_cap_pts == 950.0
    assert sensex.max_spread_pct == 0.05
    assert sensex.weekly_expiry_day_of_week == 3  # Thursday


def test_asset_profiles_are_immutable():
    """Verify that AssetProfile is a frozen dataclass preventing runtime mutation."""
    nifty = get_asset_profile("NIFTY")
    with pytest.raises(Exception):
        nifty.target_scalp_pts = 999.0
