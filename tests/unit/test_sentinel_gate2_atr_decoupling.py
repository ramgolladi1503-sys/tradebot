"""Unit tests for Sentinel Mode 5 Gate 2 ATR Decoupling and Fail-Closed Prior Day Levels.

Specification: RFC-2026-11-04-HERMES-GATE2-ATR-DECOUPLING
Pipeline: Hermes Architecture -> GSD Scoped Execution

Verifies:
1. test_unseeded_prior_levels_emits_fail_closed_veto:
   Unseeded prior day levels result in CachedRBFNAuctionSignal with action="ABSTAIN",
   is_active=False, is_vetoed=True, veto_reason="UNSEEDED_PRIOR_DAY_LEVELS",
   trade_phase="UNSEEDED", setup_reason="UNSEEDED_PRIOR_DAY_LEVELS".
2. test_macro_daily_atr_decoupled_from_micro_intraday_atr:
   Wall observer micro ATR (e.g. 85.0 pts) does NOT contaminate Gate 2 hurdle checks;
   seeding SENSEX prior day range/ATR at 550.0 pts passes Gate 2 min_atr hurdle (450.0).
3. test_bounded_prior_day_atr_proxy:
   When atr_20 is None or <= 0, seed_prior_day_levels calculates pdr = pdh - pdl and clamps
   with INDEX_ATR_BOUNDS across SENSEX (450-900), BANKNIFTY (300-650), and NIFTY (130-300).
4. test_invalid_prior_day_levels_fail_closed:
   If pdh <= pdl or pdl <= 0, seed_prior_day_levels returns False and verified=False,
   causing _on_5m_bar_close to emit UNSEEDED_PRIOR_DAY_LEVELS veto.
"""

from datetime import date, time as dt_time
import pytest

from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    PriorDayReferenceLevels,
)


def test_unseeded_prior_levels_emits_fail_closed_veto():
    """Unseeded prior day levels must fail-closed and emit an UNSEEDED veto signal."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    
    # Do not seed prior day levels for SENSEX
    assert not advisor.prior_day_levels["SENSEX"].verified

    sig = advisor._on_5m_bar_close(
        index_name="SENSEX",
        bar_open=75000.0,
        bar_high=75600.0,
        bar_low=74950.0,
        bar_close=75550.0,
        bar_volume=1000.0,
        bar_time=dt_time(9, 20),
        timestamp_ms=1793188800000,
        epoch_5min=5977296,
    )

    assert sig is not None
    assert sig.action == "ABSTAIN"
    assert sig.is_active is False
    assert sig.is_vetoed is True
    assert sig.veto_reason == "UNSEEDED_PRIOR_DAY_LEVELS"
    assert sig.setup_reason == "UNSEEDED_PRIOR_DAY_LEVELS"
    assert sig.trade_phase == "UNSEEDED"
    assert advisor.cached_rbfn_signals["SENSEX"] == sig


def test_macro_daily_atr_decoupled_from_micro_intraday_atr():
    """Micro intraday ATR (e.g. 85.0 pts) on WallObserver must NEVER trigger Gate 2 hurdle veto."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    
    # Seed SENSEX macro daily ATR as 550.0 (hurdle is 450.0)
    advisor.seed_prior_day_levels(
        index_name="SENSEX",
        pdh=75600.0,
        pdl=75050.0,
        pdc=75500.0,
        session_date=date(2026, 11, 3),
        atr_20=550.0,
    )
    assert advisor.prior_day_levels["SENSEX"].verified
    assert advisor.prior_day_levels["SENSEX"].atr_20 == 550.0

    # Contaminate wall observer micro ATR with 85.0 pts (< 450.0 hurdle)
    wall_obs = advisor.wall_observers["SENSEX"]
    wall_obs.atr_pts = 85.0

    # 09:20 bar close: strong bullish expansion candle with large range to clear compression
    sig = advisor._on_5m_bar_close(
        index_name="SENSEX",
        bar_open=75000.0,
        bar_high=75600.0,
        bar_low=74950.0,
        bar_close=75550.0,
        bar_volume=5000.0,
        bar_time=dt_time(9, 20),
        timestamp_ms=1793188800000,
        epoch_5min=5977296,
    )

    assert sig is not None
    # Must NOT be vetoed by GATE_2_FRICTIONAL_HURDLE
    assert sig.veto_reason != "GATE_2_FRICTIONAL_HURDLE"
    assert sig.setup_reason != "GATE_2_FRICTIONAL_HURDLE"
    # SENSEX min_atr hurdle is 450.0. If micro ATR (85.0) had been used, it would be vetoed!
    # With macro_daily_atr = 550.0, it clears the hurdle.


def test_bounded_prior_day_atr_proxy():
    """When atr_20 is omitted or <= 0, PDR is clamped into index-specific bounds."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)

    # 1. SENSEX: Bounds are (450.0, 900.0)
    # Sub-floor case: PDR = 200.0 -> clamped to 450.0
    advisor.seed_prior_day_levels("SENSEX", pdh=75200.0, pdl=75000.0, pdc=75100.0, atr_20=None)
    assert advisor.prior_day_levels["SENSEX"].atr_20 == 450.0

    # Above-ceiling case: PDR = 1200.0 -> clamped to 900.0
    advisor.seed_prior_day_levels("SENSEX", pdh=76200.0, pdl=75000.0, pdc=75500.0, atr_20=0.0)
    assert advisor.prior_day_levels["SENSEX"].atr_20 == 900.0

    # In-band case: PDR = 600.0 -> resolved to 600.0
    advisor.seed_prior_day_levels("SENSEX", pdh=75600.0, pdl=75000.0, pdc=75400.0)
    assert advisor.prior_day_levels["SENSEX"].atr_20 == 600.0

    # 2. BANKNIFTY: Bounds are (300.0, 650.0)
    # Sub-floor: PDR = 150.0 -> clamped to 300.0
    advisor.seed_prior_day_levels("BANKNIFTY", pdh=50150.0, pdl=50000.0, pdc=50100.0)
    assert advisor.prior_day_levels["BANKNIFTY"].atr_20 == 300.0

    # Above-ceiling: PDR = 800.0 -> clamped to 650.0
    advisor.seed_prior_day_levels("BANKNIFTY", pdh=50800.0, pdl=50000.0, pdc=50500.0)
    assert advisor.prior_day_levels["BANKNIFTY"].atr_20 == 650.0

    # 3. NIFTY: Bounds are (130.0, 300.0)
    # Sub-floor: PDR = 50.0 -> clamped to 130.0
    advisor.seed_prior_day_levels("NIFTY", pdh=24050.0, pdl=24000.0, pdc=24020.0)
    assert advisor.prior_day_levels["NIFTY"].atr_20 == 130.0

    # Above-ceiling: PDR = 450.0 -> clamped to 300.0
    advisor.seed_prior_day_levels("NIFTY", pdh=24450.0, pdl=24000.0, pdc=24200.0)
    assert advisor.prior_day_levels["NIFTY"].atr_20 == 300.0


def test_invalid_prior_day_levels_fail_closed():
    """Invalid prior day levels (pdh <= pdl or pdl <= 0) must be rejected and fail closed."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)

    # Inverted PDH/PDL: pdh < pdl
    seeded = advisor.seed_prior_day_levels("SENSEX", pdh=74000.0, pdl=75000.0, pdc=74500.0)
    assert seeded is False
    assert not advisor.prior_day_levels["SENSEX"].verified

    # Signal evaluation on unverified levels must emit UNSEEDED_PRIOR_DAY_LEVELS
    sig = advisor._on_5m_bar_close(
        index_name="SENSEX",
        bar_open=75000.0,
        bar_high=75600.0,
        bar_low=74950.0,
        bar_close=75550.0,
        bar_volume=1000.0,
        bar_time=dt_time(9, 20),
        timestamp_ms=1793188800000,
        epoch_5min=5977296,
    )
    assert sig is not None
    assert sig.action == "ABSTAIN"
    assert sig.is_active is False
    assert sig.is_vetoed is True
    assert sig.veto_reason == "UNSEEDED_PRIOR_DAY_LEVELS"
