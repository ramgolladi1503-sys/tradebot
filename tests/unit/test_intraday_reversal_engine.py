"""Unit and QA Regression Test Suite for Intraday Mean-Reversion Engine.

Work Item: FEAT-SENTINEL-INTRADAY-REVERSAL-001
Traceability:
- AC-1 through AC-5
- Grill Me Gates: GM-GATE-001 through GM-GATE-005
- Product Owner Gates: PO-GATE-1 through PO-GATE-5
- QA Matrix: TC-REV-001 through TC-REV-009 / TC-QA-REV-001 through TC-QA-REV-006
"""

from __future__ import annotations

import pytest
from core.intraday_reversal_engine import (
    IntradayReversalEngine,
    IntradayExhaustionGate,
    FailureAtExtremeEngine,
    ReversalSetupType,
    ReversalDirection,
    IntradayReversalSignal,
    ExhaustionMetrics,
)


class TestIntradayReversalEngineQA:

    def test_01_historical_nifty_top_reversal_fah(self):
        """Test 1 / TC-QA-REV-001: Historical NIFTY 2026-10-22 163-pt top reversal detection.
        - Setup: NIFTY OR High is 22,697. Price advances to 22,780.
          Local retest bar pierces local prior HOD 22,775 by 5 pts, fails, and closes at 22,768.
        - Verification:
          1. FAH signal triggered with direction PE.
          2. Signal generated on Bar T close; execution timestamp is Bar T+1 Open.
          3. Stop Loss anchored above 22,780 + buffer (22,783). Target = session VWAP (22,620).
          4. Reward:Risk ratio >= 3.0.
        """
        engine = IntradayReversalEngine(index_name="NIFTY")
        # Establish prior HOD at 22,775, LOD at 22,600
        engine.seed_prior_extremes(hod=22775.0, lod=22600.0)

        # Bar T: Open=22,770, High=22,780 (pierces HOD by 5 pts), Low=22,765, Close=22,768 (in lower 50%)
        # Close-Low = 3, High-Low = 15 -> (22768 - 22765) / 15 = 3/15 = 0.20 <= 0.50
        # Stop loss = 22780 + 3.0 = 22783.0. Risk = 22783 - 22768 = 15.0 pts.
        # Target = VWAP (22620.0). Reward = 22768 - 22620 = 148.0 pts.
        # R:R = 148.0 / 15.0 = 9.87 >= 3.0.
        sig = engine.evaluate_bar(
            bar_open=22770.0,
            bar_high=22780.0,
            bar_low=22765.0,
            bar_close=22768.0,
            volume=50000,
            timestamp_ms=1761118800000,
            forced_vwap=22620.0,
        )

        assert sig is not None
        assert sig.setup_type == ReversalSetupType.FAH
        assert sig.direction == ReversalDirection.PE
        assert sig.stop_loss_price >= 22783.0
        assert sig.target_vwap <= 22625.0
        assert sig.risk_reward_ratio >= 3.0
        assert sig.reference_extreme == 22775.0
        assert sig.trigger_price == 22768.0

        # Causal timing verification (GM-GATE-003):
        # Signal emitted at Bar T close; running HOD updated to 22780 for Bar T+1
        assert engine.prior_hod == 22780.0

    def test_02_symmetric_failure_at_low_fal_spring_trap(self):
        """Test 2 / TC-QA-REV-002: Symmetric Failure-at-Low (FAL) spring trap detection.
        - Setup: Prior LOD is 22,600. Bar pierces LOD down to 22,588 (-12 pts),
          absorbs heavy Put volume, and closes back above LOD at 22,605 (upper 50% of bar range).
        - Verification:
          1. FAL signal triggered with direction CE.
          2. Target = session VWAP (22,680).
          3. Stop loss = 22,588 - buffer (22,585).
          4. Reward:Risk ratio >= 3.0.
        """
        engine = IntradayReversalEngine(index_name="NIFTY")
        engine.seed_prior_extremes(hod=22750.0, lod=22600.0)

        # Bar T: Open=22602, High=22608, Low=22588 (pierces LOD by 12 pts), Close=22605
        # Range = 20 pts. Close-Low = 17 pts. (17 / 20) = 0.85 >= 0.50 (upper 50%)
        # Stop Loss = 22588 - 3.0 = 22585.0. Risk = 22605 - 22585 = 20.0 pts.
        # Target = VWAP (22680.0). Reward = 22680 - 22605 = 75.0 pts.
        # R:R = 75.0 / 20.0 = 3.75 >= 3.0.
        sig = engine.evaluate_bar(
            bar_open=22602.0,
            bar_high=22608.0,
            bar_low=22588.0,
            bar_close=22605.0,
            volume=60000,
            timestamp_ms=1761122400000,
            forced_vwap=22680.0,
        )

        assert sig is not None
        assert sig.setup_type == ReversalSetupType.FAL
        assert sig.direction == ReversalDirection.CE
        assert sig.stop_loss_price <= 22585.0
        assert sig.target_vwap >= 22680.0
        assert sig.risk_reward_ratio >= 3.0
        assert sig.reference_extreme == 22600.0

    def test_03_runaway_trend_suppression_gm_gate_001(self):
        """Test 3 / TC-QA-REV-003: Runaway trend suppression (GM-GATE-001).
        - Setup: Market in strong directional trend day. Monotonic VWAP slope > 0.5 pts/bar,
          deviation > 2.5 sigma, continuous expansion candles.
        - Trigger: Bar pierces HOD and closes slightly lower, attempting FAH.
        - Verification:
          1. FAH counter-trend reversal MUST BE SUPPRESSED fail-closed.
          2. Rejection reason explicitly flagged as VETO_RUNAWAY_TREND.
        """
        engine = IntradayReversalEngine(index_name="NIFTY")

        # Establish base session with 10 bars anchored at 22500
        base_time = 1761118000000
        for i in range(10):
            engine.evaluate_bar(
                bar_open=22500.0,
                bar_high=22502.0,
                bar_low=22498.0,
                bar_close=22500.0,
                volume=100000,
                timestamp_ms=base_time + i * 60000,
            )

        # Now simulate a strong runaway breakout run where price accelerates higher each bar
        # with steep VWAP slope and expansion outside 2.5 sigma
        for i in range(5):
            p = 22520.0 + i * 25.0
            engine.evaluate_bar(
                bar_open=p - 5.0,
                bar_high=p + 8.0,
                bar_low=p - 10.0,
                bar_close=p,
                volume=30000,
                timestamp_ms=base_time + (10 + i) * 60000,
            )

        # Prior HOD is now at the high of the last bar.
        # Bar T pierces HOD by 5 pts and closes lower, attempting a counter-trend FAH fade:
        curr_hod = engine.prior_hod
        sig = engine.evaluate_bar(
            bar_open=curr_hod + 2.0,
            bar_high=curr_hod + 5.0,
            bar_low=curr_hod - 15.0,
            bar_close=curr_hod - 2.0,
            volume=40000,
            timestamp_ms=base_time + 16 * 60000,
        )

        # Freight-train defense (GM-GATE-001): counter-trend fade must be vetoed fail-closed
        assert sig is None
        assert engine.last_veto_reason == "VETO_RUNAWAY_TREND"

    def test_04_orb_vs_reversal_arbitration_and_hysteresis_lockout_gm_gate_002(self):
        """Test 4 / TC-QA-REV-004: Hysteresis Lockout & Quota Cap (GM-GATE-002).
        - Setup:
          1. FAH signal fires at t=0 (e.g. 10:15:00 = 1,000,000 ms).
          2. Price whipsaws; new extreme attempted at t=5 mins (1,300,000 ms).
          3. Opposite extreme attempted at t=10 mins (1,600,000 ms).
          4. Quota test: 3rd attempt at same boundary later in the day.
        - Verification:
          1. Signal at t=5m suppressed with COOLDOWN_ACTIVE (< 15 mins).
          2. Flip-flop signal at t=10m suppressed with COOLDOWN_ACTIVE.
          3. At t=16m (1,960,000 ms), cooldown clears -> 2nd FAH allowed.
          4. 3rd FAH attempt at t=35m suppressed with EXHAUSTED_QUOTA (max 2 attempts per boundary).
        """
        engine = IntradayReversalEngine(index_name="NIFTY")
        engine.seed_prior_extremes(hod=22700.0, lod=22500.0)

        # 1. First FAH signal at t = 1,000,000 ms
        sig1 = engine.evaluate_bar(
            bar_open=22695.0,
            bar_high=22705.0, # Pierces 22700 by 5 pts
            bar_low=22685.0,
            bar_close=22690.0,
            volume=30000,
            timestamp_ms=1000000,
            forced_vwap=22550.0,
        )
        assert sig1 is not None
        assert sig1.setup_type == ReversalSetupType.FAH

        # 2. Attempt 2nd signal at t = 1,300,000 ms (5 mins later; cooldown requires 900,000 ms = 15 mins)
        sig2 = engine.evaluate_bar(
            bar_open=22706.0,
            bar_high=22710.0, # Pierces new HOD 22705 by 5 pts
            bar_low=22695.0,
            bar_close=22700.0,
            volume=30000,
            timestamp_ms=1300000,
            forced_vwap=22550.0,
        )
        assert sig2 is None
        assert engine.last_veto_reason == "COOLDOWN_ACTIVE"

        # 3. Attempt opposite FAL signal at t = 1,600,000 ms (10 mins later; still within 15 min lock)
        # Price pierces LOD 22500 down to 22490
        sig3 = engine.evaluate_bar(
            bar_open=22502.0,
            bar_high=22508.0,
            bar_low=22490.0,
            bar_close=22504.0,
            volume=40000,
            timestamp_ms=1600000,
            forced_vwap=22600.0,
        )
        assert sig3 is None
        assert engine.last_veto_reason == "COOLDOWN_ACTIVE"

        # 4. At t = 1,960,000 ms (16 mins after t=1,000,000 ms), cooldown is cleared -> 2nd FAH allowed
        sig4 = engine.evaluate_bar(
            bar_open=22712.0,
            bar_high=22718.0, # Pierces running HOD 22710 by 8 pts
            bar_low=22700.0,
            bar_close=22705.0,
            volume=35000,
            timestamp_ms=1960000,
            forced_vwap=22560.0,
        )
        assert sig4 is not None
        assert sig4.setup_type == ReversalSetupType.FAH
        assert engine.boundary_attempts["HOD"] == 2

        # 5. At t = 3,000,000 ms (> 15 mins later), attempt 3rd FAH
        sig5 = engine.evaluate_bar(
            bar_open=22720.0,
            bar_high=22725.0, # Pierces running HOD 22718 by 7 pts
            bar_low=22710.0,
            bar_close=22715.0,
            volume=35000,
            timestamp_ms=3000000,
            forced_vwap=22570.0,
        )
        assert sig5 is None
        assert engine.last_veto_reason == "EXHAUSTED_QUOTA"

    def test_05_adverse_selection_wide_spread_veto_gm_gate_004(self):
        """Test 5 / TC-QA-REV-005: Adverse selection / wide spread veto (GM-GATE-004).
        - Setup: Option contract depth is evaluated:
          Bid = 100.0, Ask = 105.0 -> Spread = 5.0 / 102.5 = 4.88% (> 4.0%).
        - Verification:
          1. Entry advisory vetoed fail-closed.
          2. Status flag = VETO_SPREAD_EXPANDED.
        """
        engine = IntradayReversalEngine(index_name="NIFTY")

        # Spread = (105 - 100) / 102.5 = 4.88% (> 4.0%)
        is_vetoed, reason = engine.evaluate_option_spread(bid=100.0, ask=105.0)
        assert is_vetoed is True
        assert reason == "VETO_SPREAD_EXPANDED"

        # Liquid option: Bid = 100.0, Ask = 101.5 -> Spread = 1.5 / 100.75 = 1.49% (<= 4.0%)
        is_vetoed_clean, reason_clean = engine.evaluate_option_spread(bid=100.0, ask=101.5)
        assert is_vetoed_clean is False
        assert reason_clean == "SPREAD_OK"

    def test_06_safety_invariants_gm_gate_005(self):
        """Test 6 / TC-QA-REV-006: Safety invariants (GM-GATE-005).
        - Verification across engine and generated signal:
          1. read_only == True
          2. is_order_action == False
          3. broker_api_called == False
          4. allowed_for_live_execution == False
          5. edge_certification_status == 'NO_CERTIFIED_EDGE'
        """
        engine = IntradayReversalEngine(index_name="NIFTY")
        assert engine.READ_ONLY is True
        assert engine.IS_ORDER_ACTION is False
        assert engine.BROKER_API_CALLED is False
        assert engine.ALLOWED_FOR_LIVE_EXECUTION is False
        assert engine.EDGE_CERTIFICATION_STATUS == "NO_CERTIFIED_EDGE"

        engine.seed_prior_extremes(hod=22700.0, lod=22500.0)
        sig = engine.evaluate_bar(
            bar_open=22695.0,
            bar_high=22705.0,
            bar_low=22685.0,
            bar_close=22690.0,
            volume=30000,
            timestamp_ms=1000000,
            forced_vwap=22550.0,
        )
        assert sig is not None
        assert sig.read_only is True
        assert sig.is_order_action is False
        assert sig.broker_api_called is False
        assert sig.allowed_for_live_execution is False
        assert sig.edge_certification_status == "NO_CERTIFIED_EDGE"

    def test_07_blow_off_breakout_suppression(self):
        """Test 7 / TC-REV-003: Pierce HOD by > 25 pts (blow-off breakout) is suppressed."""
        engine = IntradayReversalEngine(index_name="NIFTY")
        engine.seed_prior_extremes(hod=22700.0, lod=22500.0)

        # Pierces HOD 22700 up to 22735 (+35 pts > max 25 pts blow-off cap)
        sig = engine.evaluate_bar(
            bar_open=22700.0,
            bar_high=22735.0,
            bar_low=22695.0,
            bar_close=22698.0,
            volume=50000,
            timestamp_ms=1000000,
            forced_vwap=22600.0,
        )
        # Should be suppressed because pierce > delta_max
        assert sig is None

    def test_08_high_conviction_sweep_scalp_tier(self):
        """Test 8: Verify High-Conviction Sweep detection (Pierce >= 8.0 & Sigma >= 1.7)
        and 1.0R scalp target calculation.
        """
        engine = IntradayReversalEngine(index_name="NIFTY")
        engine.seed_prior_extremes(hod=22700.0, lod=22500.0)

        # Build VWAP history with deviation >= 1.7 sigma
        # Feed 10 bars around 22700
        for i in range(10):
            engine.exhaustion_gate.update_bar(
                high=22700.0, low=22690.0, close=22695.0, volume=10000.0
            )

        # Bar pierces HOD 22700 by 10.0 pts (High=22710.0), rejects and closes at 22695.0
        # forced_vwap 22550 gives deviation > 1.7 sigma
        sig = engine.evaluate_bar(
            bar_open=22700.0,
            bar_high=22710.0,  # 10 pt pierce >= 8.0 pt threshold
            bar_low=22692.0,
            bar_close=22695.0,
            volume=50000,
            timestamp_ms=2000000,
            forced_vwap=22550.0,
        )

        assert sig is not None
        assert sig.setup_type == ReversalSetupType.FAH
        assert sig.direction == ReversalDirection.PE
        assert sig.is_high_conviction_sweep is True
        # Risk = Stop (22710 + 3 = 22713) - Close (22695) = 18.0 pts
        assert sig.risk_pts == 18.0
        # Scalp Target @ 1.0R = 22695 - 18.0 = 22677.0
        assert sig.scalp_target_price == 22677.0
        assert sig.scalp_rr_ratio == 1.0
        assert "[HIGH_CONVICTION_SWEEP]" in sig.setup_reason

