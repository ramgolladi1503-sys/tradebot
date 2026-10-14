"""Asset Profile Specification Contract for Multi-Asset Sentinel Architecture.

Preserves trading safety invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False

Provides immutable asset parameters so NIFTY and SENSEX scale mathematically
without hardcoding numbers or disturbing the baseline NIFTY execution engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class AssetProfile:
    ticker: str
    index_instrument_key: str
    fo_exchange_prefix: str
    strike_step: int
    target_scalp_pts: float
    target_runner_pts: float
    initial_sl_pts: float
    ratchet_trigger_pts: float
    ratchet_lock_pts: float
    breakeven_trigger_pts: float
    breakeven_lock_pts: float
    or_min_expansion_width: float
    macro_exhaustion_cap_pts: float
    max_spread_pct: float
    weekly_expiry_day_of_week: int  # 1 = Tuesday (NIFTY), 3 = Thursday (SENSEX)
    lot_size: int = 10


ASSET_REGISTRY: Dict[str, AssetProfile] = {
    "NIFTY": AssetProfile(
        ticker="NIFTY",
        index_instrument_key="NSE_INDEX|Nifty 50",
        fo_exchange_prefix="NSE_FO",
        strike_step=50,
        target_scalp_pts=15.0,
        target_runner_pts=30.0,
        initial_sl_pts=12.0,
        ratchet_trigger_pts=8.0,
        ratchet_lock_pts=4.0,
        breakeven_trigger_pts=12.0,
        breakeven_lock_pts=1.0,
        or_min_expansion_width=70.0,
        macro_exhaustion_cap_pts=300.0,
        max_spread_pct=0.04,
        weekly_expiry_day_of_week=1,  # Tuesday
        lot_size=75,
    ),
    "SENSEX": AssetProfile(
        ticker="SENSEX",
        index_instrument_key="BSE_INDEX|SENSEX",
        fo_exchange_prefix="BSE_FO",
        strike_step=100,
        target_scalp_pts=46.0,
        target_runner_pts=85.0,
        initial_sl_pts=30.0,
        ratchet_trigger_pts=25.0,
        ratchet_lock_pts=12.0,
        breakeven_trigger_pts=40.0,
        breakeven_lock_pts=3.0,
        or_min_expansion_width=300.0,
        macro_exhaustion_cap_pts=1100.0,
        max_spread_pct=0.05,
        weekly_expiry_day_of_week=3,  # Thursday
        lot_size=10,
    ),
}


def get_asset_profile(ticker: Optional[str] = None) -> AssetProfile:
    """Retrieve immutable asset profile. Defaults safely to NIFTY."""
    if not ticker:
        return ASSET_REGISTRY["NIFTY"]
    clean_ticker = ticker.strip().upper()
    return ASSET_REGISTRY.get(clean_ticker, ASSET_REGISTRY["NIFTY"])
