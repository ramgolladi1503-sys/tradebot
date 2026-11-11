import pytest
from datetime import datetime, date, time as dt_time
from core.sentinel_live_stream_advisor import SentinelLiveStreamAdvisor, PriorDayReferenceLevels
from strategies.optionmate_rbfn_strategy import OptionMateGrid
from core.sentinel_inmem_adapter import InMemorySentinelAdapter
from core.sentinel_option_strike_resolver import SentinelOptionStrikeResolver

def test_full_chain_otm_strike_selection():
    """Prove that with full option chain in adapter, resolve_mode5_strike picks the true OTM Slingshot strike."""
    quotes = [
        {"symbol": "NIFTY 25300 PE 17 NOV 26", "strike": 25300, "ltp": 207.6, "direction": "PE"}, # ATM / high premium
        {"symbol": "NIFTY 25200 PE 17 NOV 26", "strike": 25200, "ltp": 155.0, "direction": "PE"},
        {"symbol": "NIFTY 25100 PE 17 NOV 26", "strike": 25100, "ltp": 110.0, "direction": "PE"},
        {"symbol": "NIFTY 25000 PE 17 NOV 26", "strike": 25000, "ltp": 75.0, "direction": "PE"},  # OTM in accumulation band
    ]
    anchor = 120.0 # Target band = [60, 90], mid = 75.0
    res = SentinelOptionStrikeResolver.resolve_mode5_strike("NIFTY", "PE", anchor, 25000, quotes)
    assert res.target_strike == 25000.0
    assert res.selected_premium == 75.0
    assert res.selection_mode == "PREMIUM_PROXIMITY_BAND"

def test_midway_no_mans_land_vetoed():
    """Prove that simulated ticks midway between TD and RP1 without testing TD are vetoed."""
    adapter = InMemorySentinelAdapter()
    advisor = SentinelLiveStreamAdvisor(adapter=adapter, enable_stdout=False)
    
    advisor.prior_day_levels["NIFTY"] = PriorDayReferenceLevels(index_name="NIFTY", 
        pdh=25500.0, pdl=25300.0, pdc=25400.0, session_date=date(2026, 11, 9), verified=True, atr_20=200.0
    )
    
    grid = OptionMateGrid(
        date="2026-11-11",
        spot_open=25400.0,
        trend_decider=25400.0,
        rp1_upper=25550.0,
        rp2_upper=25700.0,
        rp1_lower=25250.0,
        rp2_lower=25100.0,
        call_strike=25550.0,
        put_strike=25250.0,
        recommended_bias="RANGE",
        target_strike=25550.0,
    )
    advisor.cached_rbfn_grids["NIFTY"] = grid
    advisor.rbfn_grids_frozen["NIFTY"] = True
    
    # Pre-populate bar 1: low only 25310, high 25345 (well away from TD 25400)
    advisor.bars_5m_history["NIFTY"] = [
        {"open": 25330.0, "high": 25345.0, "low": 25310.0, "close": 25325.0, "volume": 1000, "time": dt_time(10, 0), "timestamp_ms": 1000, "epoch_5min": 1},
    ]
    
    # Bar 2 closes at 10:05 midway at 25330 without touching TD
    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=25325.0,
        bar_high=25340.0,
        bar_low=25300.0,
        bar_close=25330.0,
        bar_volume=1000.0,
        bar_time=dt_time(10, 5),
        timestamp_ms=2000,
        epoch_5min=2,
    )
    
    assert sig is not None
    assert sig.is_active is False
    assert sig.setup_reason == "NO_CONFIRMED_TD_TEST_OR_MIDWAY"
    assert sig.action == "ABSTAIN"

def test_valid_2bar_td_touch_triggers_entry():
    """Prove that touching TD with 2-bar confirmation triggers entry."""
    adapter = InMemorySentinelAdapter()
    advisor = SentinelLiveStreamAdvisor(adapter=adapter, enable_stdout=False)
    
    advisor.prior_day_levels["NIFTY"] = PriorDayReferenceLevels(index_name="NIFTY", 
        pdh=25500.0, pdl=25300.0, pdc=25400.0, session_date=date(2026, 11, 9), verified=True, atr_20=200.0
    )
    
    grid = OptionMateGrid(
        date="2026-11-11",
        spot_open=25400.0,
        trend_decider=25400.0,
        rp1_upper=25550.0,
        rp2_upper=25700.0,
        rp1_lower=25250.0,
        rp2_lower=25100.0,
        call_strike=25550.0,
        put_strike=25250.0,
        recommended_bias="RANGE",
        target_strike=25550.0,
    )
    advisor.cached_rbfn_grids["NIFTY"] = grid
    advisor.rbfn_grids_frozen["NIFTY"] = True
    
    # Bar 1 tests TD at 25402 (within 5 pts of TD 25400)
    advisor.bars_5m_history["NIFTY"] = [
        {"open": 25380.0, "high": 25402.0, "low": 25375.0, "close": 25390.0, "volume": 1000, "time": dt_time(10, 0), "timestamp_ms": 1000, "epoch_5min": 1},
    ]
    
    # Bar 2 closes at 10:05 confirming rejection at TD (close 25392 <= open 25395 and <= TD 25400)
    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=25395.0,
        bar_high=25398.0,
        bar_low=25385.0,
        bar_close=25392.0,
        bar_volume=1000.0,
        bar_time=dt_time(10, 5),
        timestamp_ms=2000,
        epoch_5min=2,
    )
    
    assert sig is not None
    assert sig.is_active is True
    assert sig.action == "BUY_PUT"
    assert sig.direction == "PE"
    assert sig.setup_reason == "TD_PULLBACK_REENTRY_BEAR_CONFIRMED_2BAR"
