import pytest
import os
import json
import time
from unittest.mock import patch, MagicMock

def test_subscription_delta_uses_observed_mutation_interface():
    from core.kite_depth_ws import _apply_subscription_delta
    ws = MagicMock()
    with patch("core.feed.ws_mutation_queue.safe_subscribe_full_mode_observed") as mock_sub, \
         patch("core.feed.ws_mutation_queue.safe_unsubscribe") as mock_unsub, \
         patch("core.kite_depth_ws._can_mutate_ws_subscriptions", return_value=(True, "ok", {})):

        # mock return values (WsMutationResult mock)
        mock_res = MagicMock()
        mock_res.ok = True
        mock_res.applied = True
        mock_res.queued = False
        mock_res.failure_reason = None
        mock_sub.return_value = (mock_res, mock_res)
        mock_unsub.return_value = mock_res

        # A healthy local mutation invokes the application callback only after
        # subscribe and FULL mode have both been confirmed by the adapter.
        def apply_locally(_ws, _tokens, _reason, _now_epoch, on_applied_callback=None, **_kwargs):
            if on_applied_callback:
                on_applied_callback()
            return mock_res, mock_res

        mock_sub.side_effect = apply_locally
        mock_unsub.side_effect = lambda _ws, _tokens, _reason, _now_epoch, on_applied_callback=None: (
            on_applied_callback() if on_applied_callback else None
        ) or mock_res

        _apply_subscription_delta(ws, [123], [456], "test")

        assert mock_sub.call_count == 1
        assert mock_sub.call_args[0][0] == ws
        assert mock_sub.call_args[0][1] == [123]
        assert mock_sub.call_args.kwargs["socket_generation"] is not None
        assert callable(mock_sub.call_args.kwargs["active_generation"])

        assert mock_unsub.call_count == 1
        assert mock_unsub.call_args[0][0] == ws
        assert mock_unsub.call_args[0][1] == [456]

def test_no_live_option_feed_not_triggered_by_single_illiquid_option_gap():
    from core.blocker_lifecycle import evaluate_feed_symbol_blockers, BlockerRegistry
    registry = BlockerRegistry("test")
    evaluate_feed_symbol_blockers(
        registry=registry,
        now_ts=105.0,
        symbol="NIFTY",
        ws_connected=True,
        expected_option_count=1,
        subscribed_option_count=1,
        option_ticks_received_count=10,
        latest_option_tick_ts=100.0,
        latest_option_tick_age_sec=5.0,
        feed_freshness_sec=2.0,
        min_required_count=1,
    )
    keys = [k for k in registry._records.keys() if k[2] == "NO_LIVE_OPTION_FEED"]
    record = registry._records.get(keys[0]) if keys else None
    assert record is None or not record.active

def test_no_option_ticks_post_connection_can_still_trigger_no_live_option_feed():
    from core.blocker_lifecycle import evaluate_feed_symbol_blockers, BlockerRegistry
    registry = BlockerRegistry("test")
    evaluate_feed_symbol_blockers(
        registry=registry,
        now_ts=105.0,
        symbol="NIFTY",
        ws_connected=True,
        expected_option_count=1,
        subscribed_option_count=1,
        option_ticks_received_count=0,
        latest_option_tick_ts=None,
        latest_option_tick_age_sec=None,
        feed_freshness_sec=2.0,
        min_required_count=1,
    )
    keys = [k for k in registry._records.keys() if k[2] == "NO_LIVE_OPTION_FEED"]
    record = registry._records.get(keys[0]) if keys else None
    assert record is not None and record.active

def test_stale_option_ltp_blocks_candidate_execution_without_triggering_no_live_option_feed():
    from core.blocker_lifecycle import evaluate_feed_symbol_blockers, BlockerRegistry
    from core.opportunity_engine import build_opportunity_score
    registry = BlockerRegistry("test")

    # 1. Show NO_LIVE_OPTION_FEED does NOT trigger for 10s gap
    evaluate_feed_symbol_blockers(
        registry=registry,
        now_ts=100.0,
        symbol="NIFTY",
        ws_connected=True,
        expected_option_count=1,
        subscribed_option_count=1,
        option_ticks_received_count=10,
        latest_option_tick_ts=90.0,
        latest_option_tick_age_sec=10.0,
        feed_freshness_sec=2.0,
        min_required_count=1,
    )
    keys = [k for k in registry._records.keys() if k[2] == "NO_LIVE_OPTION_FEED"]
    record_live = registry._records.get(keys[0]) if keys else None
    assert record_live is None or not record_live.active

    # 2. Show stale quote blocks execution in opportunity engine
    candidate = {
        "symbol": "NIFTY",
        "execution_allowed": True,
        "tradable": True,
        "execution_entry": 100.0,
        "execution_entry_status": "executable",
        "risk_budget_ok": True,
        "risk_budget_reason": "ok",
        "fresh_quote_ok": False, # This makes it stale
        "primary_blocker": "stale_quote" # Sometimes explicitly passed
    }
    score_out = build_opportunity_score(candidate)

    assert score_out["candidate_class"] != "EXECUTABLE"
    assert score_out.get("primary_blocker") == "stale_quote"

def test_rest_recovery_forces_advisory_only_in_production_engine():
    from core.opportunity_engine import _base_execution_truth

    candidate = {
        "symbol": "NIFTY",
        "execution_allowed": True,
        "tradable": True,
        "execution_entry": 100.0,
        "execution_entry_status": "executable",
        "source_flags": {"quote_source": "REST_RECOVERY"}
    }

    truth = _base_execution_truth(candidate)

    assert truth["execution_truth"] is False
    assert candidate["execution_allowed"] is False
    assert candidate["mode"] == "advisory_only"

def test_recovered_fallback_forces_advisory_only_in_production_engine():
    from core.opportunity_engine import _base_execution_truth

    candidate = {
        "symbol": "NIFTY",
        "execution_allowed": True,
        "tradable": True,
        "execution_entry": 100.0,
        "execution_entry_status": "executable",
        "source_flags": {"recovered_fallback": True}
    }

    truth = _base_execution_truth(candidate)

    assert truth["execution_truth"] is False
    assert candidate["execution_allowed"] is False
    assert candidate["mode"] == "advisory_only"


def test_wi09_gate1_spread_guard_null_or_none_or_non_positive_quote():
    from core.spread_guardrails import SpreadGuardrailState
    guard = SpreadGuardrailState()

    # Null input
    r1 = guard.validate_quote(None, 100.0)
    assert r1.passed is False
    assert r1.reason == "INVALID_QUOTE_NULL"

    # Non-numeric
    r2 = guard.validate_quote("invalid", 100.0)
    assert r2.passed is False
    assert r2.reason == "INVALID_QUOTE_NON_NUMERIC"

    # Non-positive
    r3 = guard.validate_quote(0.0, 100.0)
    assert r3.passed is False
    assert r3.reason == "INVALID_QUOTE_NON_POSITIVE"

    r4 = guard.validate_quote(-5.0, 100.0)
    assert r4.passed is False
    assert r4.reason == "INVALID_QUOTE_NON_POSITIVE"


def test_wi09_gate2_spread_guard_crossed_quote():
    from core.spread_guardrails import SpreadGuardrailState
    guard = SpreadGuardrailState()
    r = guard.validate_quote(105.0, 100.0)
    assert r.passed is False
    assert r.reason == "CROSSED_QUOTE_BID_GT_ASK"


def test_wi09_gate3_excessive_and_valid_spread_threshold():
    from core.spread_guardrails import SpreadGuardrailState
    guard = SpreadGuardrailState(max_spread_bps=50.0) # 0.5% max

    # Spread = 2.0 on midpoint 100.0 -> 200 bps (> 50 bps)
    r_bad = guard.validate_quote(99.0, 101.0)
    assert r_bad.passed is False
    assert r_bad.reason == "SPREAD_EXCEEDS_MAX_BPS"
    assert r_bad.spread_bps == pytest.approx(200.0)

    # Spread = 0.2 on midpoint 100.0 -> 20 bps (<= 50 bps)
    r_good = guard.validate_quote(99.9, 100.1)
    assert r_good.passed is True
    assert r_good.reason in ("PASSED", "INITIALIZED_BASELINE")
    assert r_good.spread_bps == pytest.approx(20.0)


def test_wi09_gate4_midpoint_jump_rejection_and_baseline_isolation():
    from core.spread_guardrails import SpreadGuardrailState
    guard = SpreadGuardrailState(max_jump_pct=2.0)

    # Tick 1: Initialize baseline at 100.0
    r1 = guard.validate_quote(99.95, 100.05)
    assert r1.passed is True
    assert guard.last_accepted_midpoint == pytest.approx(100.0)

    # Tick 2: Sudden jump to 108.0 (+8% > 2%)
    r2 = guard.validate_quote(107.95, 108.05)
    assert r2.passed is False
    assert r2.reason == "MIDPOINT_JUMP_EXCEEDS_MAX_PCT"
    # CRITICAL: Baseline remains strictly isolated and uncorrupted at 100.0!
    assert guard.last_accepted_midpoint == pytest.approx(100.0)

    # Tick 3: Normal tick near baseline (100.5)
    r3 = guard.validate_quote(100.45, 100.55)
    assert r3.passed is True
    assert r3.reason == "PASSED"
    assert guard.last_accepted_midpoint == pytest.approx(100.5)


def test_wi09_gate5_causal_resynchronization_after_k_consistent_ticks():
    from core.spread_guardrails import SpreadGuardrailState
    guard = SpreadGuardrailState(max_jump_pct=2.0, recovery_k_ticks=3, cluster_tolerance_pct=0.5)

    # Tick 1: Baseline at 100.0
    guard.validate_quote(99.95, 100.05)
    assert guard.last_accepted_midpoint == pytest.approx(100.0)

    # Genuine market gap: Price jumps to 110.0 and stays there for K=3 ticks
    g1 = guard.validate_quote(109.95, 110.05) # Midpoint 110.0, jump 10%
    assert g1.passed is False
    assert g1.in_recovery is True
    assert g1.recovery_count == 1
    assert guard.last_accepted_midpoint == pytest.approx(100.0)

    g2 = guard.validate_quote(110.05, 110.15) # Midpoint 110.1, consistent with cluster
    assert g2.passed is False
    assert g2.in_recovery is True
    assert g2.recovery_count == 2
    assert guard.last_accepted_midpoint == pytest.approx(100.0)

    g3 = guard.validate_quote(110.00, 110.10) # Midpoint 110.05, 3rd consistent tick -> Causal recovery!
    assert g3.passed is True
    assert g3.reason == "BASELINE_RESYNCHRONIZED_AFTER_K_TICKS"
    assert guard.last_accepted_midpoint == pytest.approx(110.05)


def test_wi09_gate6_candidate_safety_integration_forces_advisory_only():
    from core.spread_guardrails import SpreadGuardrailState, apply_spread_guard_to_candidate
    guard = SpreadGuardrailState()

    # Inadmissible quote (excessive spread)
    res = guard.validate_quote(10.0, 50.0)
    assert res.passed is False

    candidate = {
        "symbol": "NIFTY",
        "execution_allowed": True,
        "mode": "live",
        "candidate_class": "EXECUTABLE",
    }

    updated = apply_spread_guard_to_candidate(candidate, res)
    assert updated["execution_allowed"] is False
    assert updated["mode"] == "advisory_only"
    assert "spread_guardrail:SPREAD_EXCEEDS_MAX_BPS" in updated["primary_blocker"]
    assert updated["spread_guard_audit"]["passed"] is False
    assert updated["spread_guard_audit"]["read_only"] is True
    assert updated["spread_guard_audit"]["is_order_action"] is False


def test_wi10_gate1_deterministic_atm_strike_rounding():
    from core.option_chain import infer_atm_strike_decimal
    # Exact halfway tie-break: 24825 on 50 pt step -> Decimal ROUND_HALF_UP to 24850.0
    res_half = infer_atm_strike_decimal(24825.0, 50.0)
    assert res_half == 24850.0

    # Just below halfway: 24824.9 -> 24800.0
    res_below = infer_atm_strike_decimal(24824.9, 50.0)
    assert res_below == 24800.0

    # Non-positive or None input fails closed
    assert infer_atm_strike_decimal(None, 50.0) is None
    assert infer_atm_strike_decimal(24800.0, None) is None
    assert infer_atm_strike_decimal(-100.0, 50.0) is None


def test_wi10_gate2_gap_aware_ordinal_strike_window_selection():
    from core.option_chain import compute_gap_aware_strike_window
    # Available strikes with missing intermediate strike 24900
    available = [24600.0, 24700.0, 24800.0, 25000.0, 25100.0]

    # Spot 24800, strikes_around=2 -> Should pick 2 below (24600, 24700), ATM (24800), and 2 above (25000, 25100)
    window = compute_gap_aware_strike_window(
        spot=24800.0,
        available_strikes=available,
        step=50.0,
        strikes_around=2,
    )
    assert window == [24600.0, 24700.0, 24800.0, 25000.0, 25100.0]


def test_wi10_gate3_unlisted_atm_strike_tie_breaks_to_higher_rung():
    from core.option_chain import compute_gap_aware_strike_window
    # Exact ATM 24850 is not listed
    available = [24700.0, 24800.0, 24900.0, 25000.0]

    # Spot 24850 -> nearest strikes are 24800 and 24900. Deterministic tie-break anchors to higher 24900
    window = compute_gap_aware_strike_window(
        spot=24850.0,
        available_strikes=available,
        step=50.0,
        strikes_around=1,
    )
    assert 24900.0 in window
    assert window == [24800.0, 24900.0, 25000.0]


def test_wi10_gate4_strike_window_hysteresis_anti_churn():
    from core.option_chain import StrikeWindowHysteresisState
    state = StrikeWindowHysteresisState(hysteresis_pct=0.20)

    # Initial state should always recenter
    assert state.should_recenter(spot=24800.0, step=50.0) is True
    state.update(24800.0)

    # Boundary oscillation within threshold (50 * 1.2 = 60 pts)
    # Spot moves to 24840 (+40 pts < 60) -> should NOT recenter
    assert state.should_recenter(spot=24840.0, step=50.0) is False

    # Spot moves to 24870 (+70 pts >= 60) -> should recenter
    assert state.should_recenter(spot=24870.0, step=50.0) is True


# ---------------------------------------------------------------------------
# WI-13 Invariant Proof Gates: Volatility Regime Shift & Tick Spike Calibration
# ---------------------------------------------------------------------------

from core.spread_guardrails import (
    VolatilityCalibrator,
    VolatilityRegime,
    SpreadGuardrail,
)


def _generate_mock_closed_bars(count: int, base_price: float = 24800.0, step_delta: float = 1.0, end_epoch: float = 1700000000.0):
    bars = []
    for i in range(count):
        price = base_price + (i * step_delta)
        bars.append({
            "close": price,
            "ltp": price,
            "close_epoch": end_epoch - (count - i) * 60.0,
            "ts_epoch": end_epoch - (count - i) * 60.0,
        })
    return bars


def test_wi13_gate1_insufficient_vol_data_fails_closed():
    """Missing or insufficient historical closed bars fails closed with INSUFFICIENT_VOL_DATA (I-5)."""
    guard = SpreadGuardrail()
    # Case 1: None bars
    res1 = guard.evaluate(bid=100.0, ask=100.2, ltp=100.1, historical_closed_bars=None)
    assert res1.passed is False
    assert res1.reason == "INSUFFICIENT_VOL_DATA"
    assert res1.regime_state.is_sufficient_history is False

    # Case 2: Only 10 bars (< MIN_REQUIRED_BARS=20)
    bars_10 = _generate_mock_closed_bars(10)
    res2 = guard.evaluate(bid=100.0, ask=100.2, ltp=100.1, historical_closed_bars=bars_10)
    assert res2.passed is False
    assert res2.reason == "INSUFFICIENT_VOL_DATA"


def test_wi13_gate2_hard_max_cap_immovable_ceiling():
    """Extreme volatility expansion scales multiplier but is strictly clamped at HARD_MAX_CAP_BPS=150.0 (I-1)."""
    guard = SpreadGuardrail()
    # High volatility bars with large delta jumps
    bars = []
    base = 24000.0
    for i in range(25):
        # alternate +200, -200 to generate extreme realized vol
        p = base + (200.0 if i % 2 == 0 else -200.0)
        bars.append({"close": p, "close_epoch": 1700000000.0 - (25 - i) * 60.0})

    # Base cap is 120.0 bps, regime multiplier maxes at 1.5 -> 120 * 1.5 = 180.0 bps,
    # but HARD_MAX_CAP_BPS = 150.0 bps, so effective cap MUST be clamped to 150.0!
    res = guard.evaluate(
        bid=100.0,
        ask=101.4,  # spread = 1.4 / 100.7 * 10000 = 139 bps (< 150) -> passed
        ltp=100.7,
        historical_closed_bars=bars,
        base_cap_bps=120.0,
    )
    assert res.effective_max_spread_bps == 150.0
    assert res.passed is True
    assert res.reason == "SPREAD_WITHIN_DYNAMIC_CAP"

    # Spread at 155 bps (> 150 cap) must fail!
    res_fail = guard.evaluate(
        bid=100.0,
        ask=101.6,  # spread ~ 158 bps (> 150) -> fails
        ltp=100.8,
        historical_closed_bars=bars,
        base_cap_bps=120.0,
    )
    assert res_fail.passed is False
    assert res_fail.reason == "SPREAD_EXCEEDS_DYNAMIC_CAP"


def test_wi13_gate3_single_tick_spike_quarantined_from_volatility():
    """Outlier price print (> 3.5 sigma) is quarantined and filtered without cluster confirmation (I-2)."""
    calibrator = VolatilityCalibrator()
    # Normal distribution with mean=100.0, std=1.0
    # Single spike tick at 110.0 (+10 sigma)
    res = calibrator.evaluate_tick(
        tick_price=110.0,
        rolling_mean=100.0,
        rolling_std=1.0,
        consecutive_outside_count=0,
    )
    assert res.is_spike is True
    assert res.quarantined is True
    assert res.is_cluster is False
    assert res.filtered_price == 100.0  # substituted with rolling mean to prevent variance contamination!
    assert res.deviation_sigma == 10.0


def test_wi13_gate4_multi_tick_cluster_confirms_valid_displacement():
    """When consecutive ticks (>= 3) sustain the displacement, it is accepted as a valid cluster move (I-4)."""
    calibrator = VolatilityCalibrator()
    # 3 consecutive prints at 105.0 (+5 sigma)
    res = calibrator.evaluate_tick(
        tick_price=105.0,
        rolling_mean=100.0,
        rolling_std=1.0,
        consecutive_outside_count=3,
    )
    assert res.is_spike is False
    assert res.is_cluster is True
    assert res.quarantined is False
    assert res.filtered_price == 105.0  # confirmed price accepted!


def test_wi13_gate5_causal_no_unclosed_tick_lookahead():
    """Historical bars with future timestamps (> now_ts) are rejected to preserve strict causal invariance (I-3)."""
    guard = SpreadGuardrail()
    now_epoch = 1700000000.0
    # Generate bars where the last bar has timestamp into the future (now_epoch + 60.0)
    bars = _generate_mock_closed_bars(25, end_epoch=now_epoch + 120.0)
    res = guard.evaluate(
        bid=100.0,
        ask=100.2,
        ltp=100.1,
        historical_closed_bars=bars,
        now_ts=now_epoch,
    )
    assert res.passed is False
    assert res.reason == "INSUFFICIENT_VOL_DATA"
    assert res.regime_state.is_sufficient_history is False
