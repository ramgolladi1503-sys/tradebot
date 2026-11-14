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

def test_midday_phase_b_td_touch_triggers_entry():
    """Prove that Phase B (10:45 - 13:30) triggers TD rejection drive toward RP1."""
    adapter = InMemorySentinelAdapter()
    advisor = SentinelLiveStreamAdvisor(adapter=adapter, enable_stdout=False)
    
    advisor.prior_day_levels["NIFTY"] = PriorDayReferenceLevels(
        index_name="NIFTY", pdh=25500.0, pdl=25300.0, pdc=25400.0, session_date=date(2026, 11, 9), verified=True, atr_20=200.0
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
    
    # Bar 1 at 11:25 tests TD at 25402
    advisor.bars_5m_history["NIFTY"] = [
        {"open": 25380.0, "high": 25402.0, "low": 25375.0, "close": 25390.0, "volume": 1000, "time": dt_time(11, 25), "timestamp_ms": 1000, "epoch_5min": 1},
    ]
    
    # Bar 2 at 11:30 closes bearish at 25392 confirming hold below TD
    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=25395.0,
        bar_high=25398.0,
        bar_low=25385.0,
        bar_close=25392.0,
        bar_volume=1000.0,
        bar_time=dt_time(11, 30), # Midday Phase B
        timestamp_ms=2000,
        epoch_5min=2,
    )
    
    assert sig is not None
    assert sig.is_active is True
    assert sig.action == "BUY_PUT"
    assert sig.direction == "PE"
    assert sig.setup_reason == "TD_PULLBACK_REENTRY_BEAR_CONFIRMED_2BAR"


def test_sensex_otm_slingshot_avoids_false_exhaustion_veto():
    """Prove that SENSEX OptionMate RBFN measures displacement against Trend Decider,
    preventing genuine OTM Slingshot PE strikes (< 250 LTP) from false EXHAUSTED_EXPANSION vetoes.
    """
    from core.sentinel_live_stream_advisor import UpstoxLevel5DepthRecord, CachedRBFNAuctionSignal
    from strategies.sensex_optionmate_rbfn_strategy import SensexOptionMateGrid
    
    adapter = InMemorySentinelAdapter()
    advisor = SentinelLiveStreamAdvisor(adapter=adapter, enable_stdout=False)
    
    advisor.prior_day_levels["SENSEX"] = PriorDayReferenceLevels(
        index_name="SENSEX", pdh=81339.41, pdl=80519.31, pdc=81106.65, session_date=date(2026, 11, 9), verified=True, atr_20=805.64
    )
    
    grid = SensexOptionMateGrid(
        date="2026-11-11",
        spot_open=82520.40,
        prev_close=81106.65,
        atr_14=805.64,
        vix=14.0,
        trend_decider=82500.0,
        rp1_upper=82900.0,
        rp2_upper=83300.0,
        rp1_lower=82100.0,
        rp2_lower=81700.0,
        target_call_strike=83300.0,
        target_put_strike=81700.0,
        sustainable_price_anchor=340.0,
        dte=2,
    )
    advisor.cached_rbfn_grids["SENSEX"] = grid
    advisor.rbfn_grids_frozen["SENSEX"] = True
    
    advisor.cached_rbfn_signals["SENSEX"] = CachedRBFNAuctionSignal(
        timestamp_ms=1000,
        index_name="SENSEX",
        action="BUY_PUT",
        direction="PE",
        target_strike=81400.0,
        target_pts=50.0,
        sl_pts=35.0,
        setup_reason="TD_PULLBACK_REENTRY_BEAR_CONFIRMED_2BAR",
        trade_phase="MIDDAY_REVERSAL",
        bar_time=dt_time(13, 25),
        is_active=True,
    )
    
    tick = UpstoxLevel5DepthRecord(
        token="BSE_FO|81400PE",
        symbol="SENSEX 81400 PE 12 NOV 26",
        exchange_timestamp_ms=2000,
        ingress_monotonic_ns=0,
        ingress_wall_utc="2026-11-11T13:25:00Z",
        sequence_id=1,
        ltp=199.80,
        volume=10000,
        open_interest=500000,
        bid_p1=199.50, bid_q1=1000, bid_o1=5,
        bid_p2=199.40, bid_q2=1000, bid_o2=5,
        bid_p3=199.30, bid_q3=1000, bid_o3=5,
        bid_p4=199.20, bid_q4=1000, bid_o4=5,
        bid_p5=199.10, bid_q5=1000, bid_o5=5,
        ask_p1=200.10, ask_q1=1000, ask_o1=5,
        ask_p2=200.20, ask_q2=1000, ask_o2=5,
        ask_p3=200.30, ask_q3=1000, ask_o3=5,
        ask_p4=200.40, ask_q4=1000, ask_o4=5,
        ask_p5=200.50, ask_q5=1000, ask_o5=5,
    )
    adapter.on_depth(tick)
    
    advisor.spots["SENSEX"] = 81995.2
    advisor.spots_ts_ms["SENSEX"] = 2000
    advisor.on_depth(tick)
    
    recent_vetoes = [v for v in advisor.journal.veto_history if v.symbol == "SENSEX 81400 PE 12 NOV 26"]
    exhaustion_vetoes = [v for v in recent_vetoes if v.veto_reason == "VOLATILITY_EXHAUSTED"]
    assert len(exhaustion_vetoes) == 0, f"False exhaustion veto triggered: {exhaustion_vetoes}"
