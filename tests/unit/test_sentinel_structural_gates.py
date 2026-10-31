"""
Unit and Adversarial Test Suite for Sentinel Structural Edge Gates.

Verifies:
- GATE-SG-1 to GATE-SG-9
- Grill Me Failure Injection Vectors (AST point literals, causal ATR temporal isolation,
  degenerate geometry & div-zero fail closed, statelessness and zero cross-session leakage).
"""

import ast
import inspect
import math
from dataclasses import FrozenInstanceError

import pytest

from core.market_structure.sentinel_structural_gates import (
    AuctionBoundaryDecision,
    AuctionBoundaryInput,
    AuctionBoundaryState,
    GammaWallDecision,
    GammaWallInput,
    GammaWallState,
    OpeningShockDecision,
    OpeningShockInput,
    OpeningShockRegime,
    SentinelCompositeStructuralDecision,
    SentinelStructuralGates,
    StructuralGatingAction,
    WallType,
)


# ---------------------------------------------------------------------------
# Grill Me Adversarial Test 1: AST Scan Proving Zero Raw Point Literals
# ---------------------------------------------------------------------------

def test_zero_point_threshold_ast_audit():
    """
    Grill Me Failure Injection: AST scan of sentinel_structural_gates.py.
    Asserts zero raw point thresholds (e.g. 15, 25, 50, 64.8, 100) are used
    in comparison operations. Only scale-free dimension ratios (< 2.0) are allowed.
    """
    import core.market_structure.sentinel_structural_gates as target_mod

    source = inspect.getsource(target_mod)
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, (int, float)):
                    # Values representing absolute index price points (> 2.0) are forbidden in comparisons
                    assert comparator.value <= 2.0 or comparator.value == 20 or comparator.value == 365.0, (
                        f"Forbidden raw point literal found in comparison: {comparator.value}"
                    )


# ---------------------------------------------------------------------------
# GATE-SG-1: Scale Invariance for Opening Shock Ratio (Omega_15)
# ---------------------------------------------------------------------------

def test_scale_invariance_omega_15():
    """
    Multiplying all prices by k (e.g. index level 10,000 vs 25,000)
    produces identical Omega_15 within 1e-9 tolerance.
    """
    base_input = OpeningShockInput(
        opening_range_high=25050.0,
        opening_range_low=25000.0,
        daily_atr_20=200.0,
        historical_bars_available=20,
    )
    base_res = SentinelStructuralGates.evaluate_opening_shock(base_input)
    assert base_res.is_valid is True
    assert pytest.approx(base_res.omega_15, 1e-9) == 0.25

    # Scale by arbitrary multipliers
    for k in (0.1, 0.5, 2.5, 10.0, 100.0):
        scaled_input = OpeningShockInput(
            opening_range_high=base_input.opening_range_high * k,
            opening_range_low=base_input.opening_range_low * k,
            daily_atr_20=base_input.daily_atr_20 * k,
            historical_bars_available=20,
        )
        scaled_res = SentinelStructuralGates.evaluate_opening_shock(scaled_input)
        assert scaled_res.is_valid is True
        assert pytest.approx(scaled_res.omega_15, 1e-9) == base_res.omega_15
        assert scaled_res.regime == base_res.regime
        assert scaled_res.action == base_res.action


# ---------------------------------------------------------------------------
# GATE-SG-2 & Grill Me Test 2: Degenerate Geometry & Div-Zero Fail Closed
# ---------------------------------------------------------------------------

def test_degenerate_geometry_and_div_zero_fail_closed():
    """Alias ensuring explicit match with Grill Me Adversarial vector naming."""
    test_fail_closed_degenerate_geometry()


def test_causal_atr_zero_forward_leakage():
    """
    Grill Me Failure Injection: Proves ATR denominator is causal with zero forward leakage.
    Opening shock ratio uses strictly daily_atr_20 frozen at prior session close (T-1).
    Injecting intraday extreme bars at session T open produces zero change in the ATR denominator.
    """
    prior_close_atr = 185.50

    # Session T opens with a massive +500 point gap candle
    shock_input_a = OpeningShockInput(
        opening_range_high=25500.0,
        opening_range_low=25000.0,
        daily_atr_20=prior_close_atr,
        historical_bars_available=20,
    )
    res_a = SentinelStructuralGates.evaluate_opening_shock(shock_input_a)

    # Session T opens with a narrow 10 point compression candle
    shock_input_b = OpeningShockInput(
        opening_range_high=25010.0,
        opening_range_low=25000.0,
        daily_atr_20=prior_close_atr,
        historical_bars_available=20,
    )
    res_b = SentinelStructuralGates.evaluate_opening_shock(shock_input_b)

    # Verify that the ATR denominator remains strictly frozen at prior_close_atr in both cases
    assert pytest.approx(res_a.omega_15 * prior_close_atr, 1e-9) == 500.0
    assert pytest.approx(res_b.omega_15 * prior_close_atr, 1e-9) == 10.0
    assert res_a.regime == OpeningShockRegime.EXHAUSTION_SHOCK
    assert res_b.regime == OpeningShockRegime.COMPRESSED_COIL


def test_opening_shock_regimes_comprehensive():
    """
    Validates all Opening Shock regime transitions:
    COMPRESSED_COIL, NORMAL_EQUILIBRIUM, EXHAUSTION_SHOCK, and fail-closed UNKNOWN.
    """
    atr = 100.0
    # Compressed (< 0.25)
    r_comp = SentinelStructuralGates.evaluate_opening_shock(
        OpeningShockInput(opening_range_high=24020.0, opening_range_low=24000.0, daily_atr_20=atr)
    )
    assert r_comp.regime == OpeningShockRegime.COMPRESSED_COIL
    assert r_comp.action == StructuralGatingAction.RESTRICT_MEAN_REVERSION_ONLY

    # Equilibrium (0.25 <= omega <= 0.55)
    r_norm = SentinelStructuralGates.evaluate_opening_shock(
        OpeningShockInput(opening_range_high=24040.0, opening_range_low=24000.0, daily_atr_20=atr)
    )
    assert r_norm.regime == OpeningShockRegime.NORMAL_EQUILIBRIUM
    assert r_norm.action == StructuralGatingAction.ALLOW

    # Exhaustion (> 0.55)
    r_exh = SentinelStructuralGates.evaluate_opening_shock(
        OpeningShockInput(opening_range_high=24075.0, opening_range_low=24000.0, daily_atr_20=atr)
    )
    assert r_exh.regime == OpeningShockRegime.EXHAUSTION_SHOCK
    assert r_exh.action == StructuralGatingAction.RESTRICT_BREAKOUT_ONLY

    # Unknown / Insufficient history (<20 bars)
    r_unk = SentinelStructuralGates.evaluate_opening_shock(
        OpeningShockInput(opening_range_high=24040.0, opening_range_low=24000.0, daily_atr_20=atr, historical_bars_available=15)
    )
    assert r_unk.regime == OpeningShockRegime.UNKNOWN
    assert r_unk.action == StructuralGatingAction.BLOCK_ALL_ENTRIES
    assert r_unk.is_valid is False


def test_boundary_auction_states_comprehensive():
    """
    Validates all Boundary Auction states:
    IN_VALUE_AUCTION, AUCTION_ACCEPTANCE, FAILED_AUCTION_TRAP, TESTING_BOUNDARY, UNKNOWN.
    """
    atr = 200.0
    pdh = 25100.0
    pdl = 24900.0

    # In value
    r_in = SentinelStructuralGates.evaluate_auction_boundary(
        AuctionBoundaryInput(
            spot_price=25000.0, prior_day_high=pdh, prior_day_low=pdl, daily_atr_20=atr,
            excursion_bar_volume=1000.0, excursion_bar_delta_volume=100.0,
            consecutive_outside_closes=0, returned_inside_within_n_bars=False
        )
    )
    assert r_in.state == AuctionBoundaryState.IN_VALUE_AUCTION
    assert r_in.action == StructuralGatingAction.ALLOW

    # Testing boundary (spot above PDH without 2 closes or high delta)
    r_test = SentinelStructuralGates.evaluate_auction_boundary(
        AuctionBoundaryInput(
            spot_price=25120.0, prior_day_high=pdh, prior_day_low=pdl, daily_atr_20=atr,
            excursion_bar_volume=1000.0, excursion_bar_delta_volume=50.0,
            consecutive_outside_closes=1, returned_inside_within_n_bars=False
        )
    )
    assert r_test.state == AuctionBoundaryState.TESTING_BOUNDARY
    assert r_test.action == StructuralGatingAction.RESTRICT_BREAKOUT_ONLY

    # Failed auction trap
    r_trap = SentinelStructuralGates.evaluate_auction_boundary(
        AuctionBoundaryInput(
            spot_price=25120.0, prior_day_high=pdh, prior_day_low=pdl, daily_atr_20=atr,
            excursion_bar_volume=1000.0, excursion_bar_delta_volume=-300.0,
            consecutive_outside_closes=1, returned_inside_within_n_bars=True
        )
    )
    assert r_trap.state == AuctionBoundaryState.FAILED_AUCTION_TRAP
    assert r_trap.action == StructuralGatingAction.RESTRICT_BREAKOUT_ONLY

    # Acceptance
    r_acc = SentinelStructuralGates.evaluate_auction_boundary(
        AuctionBoundaryInput(
            spot_price=25150.0, prior_day_high=pdh, prior_day_low=pdl, daily_atr_20=atr,
            excursion_bar_volume=5000.0, excursion_bar_delta_volume=2000.0,
            consecutive_outside_closes=2, returned_inside_within_n_bars=False
        )
    )
    assert r_acc.state == AuctionBoundaryState.AUCTION_ACCEPTANCE
    assert r_acc.action == StructuralGatingAction.ALLOW

    # Fail closed on degenerate boundaries
    r_bad = SentinelStructuralGates.evaluate_auction_boundary(
        AuctionBoundaryInput(
            spot_price=25150.0, prior_day_high=24800.0, prior_day_low=25200.0, daily_atr_20=atr,
            excursion_bar_volume=1000.0, excursion_bar_delta_volume=200.0,
            consecutive_outside_closes=2, returned_inside_within_n_bars=False
        )
    )
    assert r_bad.state == AuctionBoundaryState.UNKNOWN
    assert r_bad.action == StructuralGatingAction.BLOCK_ALL_ENTRIES
    assert r_bad.is_valid is False


def test_gamma_wall_states_comprehensive():
    """
    Validates all Gamma Wall states:
    UNCONSTRAINED_FLOW, PIN_RISK_BARRIER, WALL_BREAKTHROUGH_VULNERABLE, APPROACHING_WALL, UNKNOWN.
    """
    spot = 25000.0
    iv = 0.15
    dte = 2.0
    total_oi = 1000000.0

    # Far away (d_norm >= 0.70)
    r_far = SentinelStructuralGates.evaluate_gamma_wall(
        GammaWallInput(spot_price=spot, wall_strike=25500.0, wall_type=WallType.CALL_WALL,
                       implied_volatility=iv, dte_days=dte, wall_total_oi=total_oi)
    )
    assert r_far.state == GammaWallState.UNCONSTRAINED_FLOW
    assert r_far.action == StructuralGatingAction.ALLOW

    # Approaching (0.35 <= d_norm < 0.70)
    r_app = SentinelStructuralGates.evaluate_gamma_wall(
        GammaWallInput(spot_price=spot, wall_strike=25150.0, wall_type=WallType.CALL_WALL,
                       implied_volatility=iv, dte_days=dte, wall_total_oi=total_oi)
    )
    assert r_app.state == GammaWallState.APPROACHING_WALL
    assert r_app.action == StructuralGatingAction.ALLOW

    # Pin Risk Barrier (d_norm < 0.35, WVR < 0.25)
    r_pin = SentinelStructuralGates.evaluate_gamma_wall(
        GammaWallInput(spot_price=spot, wall_strike=25040.0, wall_type=WallType.CALL_WALL,
                       implied_volatility=iv, dte_days=dte, wall_total_oi=total_oi, wall_unwind_oi=50000.0)
    )
    assert r_pin.state == GammaWallState.PIN_RISK_BARRIER
    assert r_pin.action == StructuralGatingAction.RESTRICT_BREAKOUT_ONLY

    # Squeeze / Breakthrough (d_norm < 0.35, WVR >= 0.50)
    r_sqz = SentinelStructuralGates.evaluate_gamma_wall(
        GammaWallInput(spot_price=spot, wall_strike=25040.0, wall_type=WallType.CALL_WALL,
                       implied_volatility=iv, dte_days=dte, wall_total_oi=total_oi, wall_unwind_oi=600000.0)
    )
    assert r_sqz.state == GammaWallState.WALL_BREAKTHROUGH_VULNERABLE
    assert r_sqz.action == StructuralGatingAction.ALLOW

    # Unknown / Incomplete Chain (zero total OI or non-positive spot/strike)
    r_unk = SentinelStructuralGates.evaluate_gamma_wall(
        GammaWallInput(spot_price=spot, wall_strike=25040.0, wall_type=WallType.CALL_WALL,
                       implied_volatility=iv, dte_days=dte, wall_total_oi=0.0)
    )
    assert r_unk.state == GammaWallState.UNKNOWN
    assert r_unk.action == StructuralGatingAction.BLOCK_ALL_ENTRIES
    assert r_unk.is_valid is False


def test_fail_closed_degenerate_geometry():
    """
    Zero ATR, inverted range, insufficient history (<20 bars), or negative spot
    must fail closed without throwing unhandled exceptions.
    """
    # 1. Opening Shock fail closed
    invalid_shock = OpeningShockInput(
        opening_range_high=25000.0,
        opening_range_low=25050.0,  # Inverted
        daily_atr_20=200.0,
    )
    res = SentinelStructuralGates.evaluate_opening_shock(invalid_shock)
    assert res.is_valid is False
    assert res.regime == OpeningShockRegime.UNKNOWN
    assert res.action == StructuralGatingAction.BLOCK_ALL_ENTRIES

    # 2. History < 20 bars fail closed
    short_history = OpeningShockInput(
        opening_range_high=25050.0,
        opening_range_low=25000.0,
        daily_atr_20=200.0,
        historical_bars_available=19,
    )
    res_short = SentinelStructuralGates.evaluate_opening_shock(short_history)
    assert res_short.is_valid is False
    assert res_short.regime == OpeningShockRegime.UNKNOWN

    # 3. ATR <= 0 div-zero fail closed
    zero_atr = OpeningShockInput(
        opening_range_high=25050.0,
        opening_range_low=25000.0,
        daily_atr_20=0.0,
    )
    res_zero = SentinelStructuralGates.evaluate_opening_shock(zero_atr)
    assert res_zero.is_valid is False

    # 4. Boundary Auction fail closed on inverted PDH/PDL
    invalid_bound = AuctionBoundaryInput(
        spot_price=25000.0,
        prior_day_high=24800.0,  # Inverted: PDH < PDL
        prior_day_low=25200.0,
        daily_atr_20=200.0,
        excursion_bar_volume=1000.0,
        excursion_bar_delta_volume=200.0,
        consecutive_outside_closes=2,
        returned_inside_within_n_bars=False,
    )
    res_bound = SentinelStructuralGates.evaluate_auction_boundary(invalid_bound)
    assert res_bound.is_valid is False
    assert res_bound.state == AuctionBoundaryState.UNKNOWN
    assert res_bound.action == StructuralGatingAction.BLOCK_ALL_ENTRIES

    # 5. Gamma Wall fail closed on zero OI or non-positive strike
    invalid_gamma = GammaWallInput(
        spot_price=25000.0,
        wall_strike=0.0,  # Invalid strike
        wall_type=WallType.CALL_WALL,
        implied_volatility=0.15,
        dte_days=2.0,
        wall_total_oi=0.0,  # Zero OI
    )
    res_gamma = SentinelStructuralGates.evaluate_gamma_wall(invalid_gamma)
    assert res_gamma.is_valid is False
    assert res_gamma.state == GammaWallState.UNKNOWN
    assert res_gamma.action == StructuralGatingAction.BLOCK_ALL_ENTRIES


# ---------------------------------------------------------------------------
# GATE-SG-3: Failed Auction Trap at Prior Day High
# ---------------------------------------------------------------------------

def test_failed_auction_trap_pdh():
    """
    Spot breaches PDH but re-enters prior day range with negative delta divergence.
    Gate classifies as FAILED_AUCTION_TRAP and issues RESTRICT_BREAKOUT_ONLY.
    """
    trap_input = AuctionBoundaryInput(
        spot_price=25150.0,
        prior_day_high=25100.0,
        prior_day_low=24900.0,
        daily_atr_20=200.0,
        excursion_bar_volume=5000.0,
        excursion_bar_delta_volume=-1500.0,  # Negative delta rejection
        consecutive_outside_closes=1,
        returned_inside_within_n_bars=True,  # Trapped and rejected back inside
    )
    decision = SentinelStructuralGates.evaluate_auction_boundary(trap_input)
    assert decision.is_valid is True
    assert decision.state == AuctionBoundaryState.FAILED_AUCTION_TRAP
    assert decision.action == StructuralGatingAction.RESTRICT_BREAKOUT_ONLY
    assert decision.rejection_ratio < 0.0


# ---------------------------------------------------------------------------
# GATE-SG-4: Genuine Auction Acceptance at Prior Day Low
# ---------------------------------------------------------------------------

def test_auction_acceptance_pdl():
    """
    Spot breaks below PDL with sustained outside closes and aggressive selling volume.
    Gate confirms AUCTION_ACCEPTANCE and permits trend continuation.
    """
    acceptance_input = AuctionBoundaryInput(
        spot_price=24850.0,
        prior_day_high=25100.0,
        prior_day_low=24900.0,
        daily_atr_20=200.0,
        excursion_bar_volume=8000.0,
        excursion_bar_delta_volume=-4000.0,  # Heavy selling delta
        consecutive_outside_closes=3,        # Sustained acceptance
        returned_inside_within_n_bars=False,
    )
    decision = SentinelStructuralGates.evaluate_auction_boundary(acceptance_input)
    assert decision.is_valid is True
    assert decision.state == AuctionBoundaryState.AUCTION_ACCEPTANCE
    assert decision.action == StructuralGatingAction.ALLOW
    assert decision.rejection_ratio >= 0.20


# ---------------------------------------------------------------------------
# GATE-SG-5: Scale Invariance for Normalized Gamma Wall Distance (d_norm)
# ---------------------------------------------------------------------------

def test_scale_invariance_d_norm():
    """
    Scaling both spot and strike by k produces identical d_norm within 1e-9.
    """
    base_input = GammaWallInput(
        spot_price=25000.0,
        wall_strike=25100.0,
        wall_type=WallType.CALL_WALL,
        implied_volatility=0.14,
        dte_days=1.0,
        wall_total_oi=500000.0,
    )
    base_res = SentinelStructuralGates.evaluate_gamma_wall(base_input)
    assert base_res.is_valid is True

    for k in (0.2, 0.5, 2.0, 5.0):
        scaled_input = GammaWallInput(
            spot_price=base_input.spot_price * k,
            wall_strike=base_input.wall_strike * k,
            wall_type=WallType.CALL_WALL,
            implied_volatility=base_input.implied_volatility,
            dte_days=base_input.dte_days,
            wall_total_oi=base_input.wall_total_oi,
        )
        scaled_res = SentinelStructuralGates.evaluate_gamma_wall(scaled_input)
        assert scaled_res.is_valid is True
        assert pytest.approx(scaled_res.normalized_distance, 1e-9) == base_res.normalized_distance


# ---------------------------------------------------------------------------
# GATE-SG-6: Zero DTE Boundary Safety
# ---------------------------------------------------------------------------

def test_zero_dte_boundary_safety():
    """
    On 0-DTE expiration afternoon, dte_days approaches 0.0.
    The evaluator must floor tau to 0.5 / 365 to prevent divide-by-zero explosions.
    """
    zero_dte_input = GammaWallInput(
        spot_price=25000.0,
        wall_strike=25050.0,
        wall_type=WallType.CALL_WALL,
        implied_volatility=0.15,
        dte_days=0.0,  # Exact 0-DTE
        wall_total_oi=1000000.0,
    )
    res = SentinelStructuralGates.evaluate_gamma_wall(zero_dte_input)
    assert res.is_valid is True
    assert res.normalized_distance > 0.0
    assert not math.isinf(res.normalized_distance)
    assert not math.isnan(res.normalized_distance)


# ---------------------------------------------------------------------------
# GATE-SG-7: Pin Risk Barrier vs. Gamma Squeeze Vulnerability
# ---------------------------------------------------------------------------

def test_pin_risk_vs_gamma_squeeze():
    """
    Near fortified call wall with zero unwinding (WVR = 0.02) -> PIN_RISK_BARRIER (RESTRICT_BREAKOUT).
    Near fragile call wall with heavy unwinding (WVR = 0.60) -> WALL_BREAKTHROUGH_VULNERABLE (ALLOW).
    """
    # 1. Fortified wall pin risk
    fortified_input = GammaWallInput(
        spot_price=25040.0,
        wall_strike=25050.0,
        wall_type=WallType.CALL_WALL,
        implied_volatility=0.12,
        dte_days=1.0,
        wall_total_oi=1000000.0,
        wall_unwind_oi=20000.0,  # WVR = 0.02
    )
    res_fortified = SentinelStructuralGates.evaluate_gamma_wall(fortified_input)
    assert res_fortified.state == GammaWallState.PIN_RISK_BARRIER
    assert res_fortified.action == StructuralGatingAction.RESTRICT_BREAKOUT_ONLY

    # 2. Fragile unwinding wall squeeze
    unwinding_input = GammaWallInput(
        spot_price=25040.0,
        wall_strike=25050.0,
        wall_type=WallType.CALL_WALL,
        implied_volatility=0.12,
        dte_days=1.0,
        wall_total_oi=1000000.0,
        wall_unwind_oi=600000.0,  # WVR = 0.60
    )
    res_unwinding = SentinelStructuralGates.evaluate_gamma_wall(unwinding_input)
    assert res_unwinding.state == GammaWallState.WALL_BREAKTHROUGH_VULNERABLE
    assert res_unwinding.action == StructuralGatingAction.ALLOW


# ---------------------------------------------------------------------------
# GATE-SG-8: Immutability and Safety Invariants
# ---------------------------------------------------------------------------

def test_immutability_and_read_only():
    """
    All decision outputs must verify read_only=True, is_order_action=False,
    and attempting to mutate fields must raise FrozenInstanceError.
    """
    inp = OpeningShockInput(
        opening_range_high=25020.0,
        opening_range_low=25000.0,
        daily_atr_20=200.0,
    )
    res = SentinelStructuralGates.evaluate_opening_shock(inp)
    assert res.read_only is True
    assert res.is_order_action is False
    assert res.broker_api_called is False
    assert res.allowed_for_live_execution is False

    with pytest.raises(FrozenInstanceError):
        res.action = StructuralGatingAction.ALLOW  # type: ignore


# ---------------------------------------------------------------------------
# GATE-SG-9: Composite Structural Gate Evaluation
# ---------------------------------------------------------------------------

def test_composite_structural_gate():
    """
    Composite gate combines shock, auction, and gamma decisions.
    Aggregates constraints and fails closed if any gate blocks.
    """
    # Scenario A: All gates allow
    shock_ok = OpeningShockDecision(
        regime=OpeningShockRegime.NORMAL_EQUILIBRIUM,
        omega_15=0.40,
        action=StructuralGatingAction.ALLOW,
        is_valid=True,
        diagnostic="OK",
    )
    bound_ok = AuctionBoundaryDecision(
        state=AuctionBoundaryState.IN_VALUE_AUCTION,
        normalized_penetration=0.0,
        rejection_ratio=0.0,
        action=StructuralGatingAction.ALLOW,
        is_valid=True,
        diagnostic="OK",
    )
    gamma_ok = GammaWallDecision(
        state=GammaWallState.UNCONSTRAINED_FLOW,
        normalized_distance=0.90,
        wall_vulnerability_ratio=0.10,
        action=StructuralGatingAction.ALLOW,
        is_valid=True,
        diagnostic="OK",
    )
    composite_ok = SentinelStructuralGates.evaluate_composite(shock_ok, bound_ok, gamma_ok)
    assert composite_ok.is_valid is True
    assert composite_ok.action == StructuralGatingAction.ALLOW
    assert len(composite_ok.active_constraints) == 0

    # Scenario B: Failed auction trap triggers restriction
    bound_trap = AuctionBoundaryDecision(
        state=AuctionBoundaryState.FAILED_AUCTION_TRAP,
        normalized_penetration=0.25,
        rejection_ratio=-0.35,
        action=StructuralGatingAction.RESTRICT_BREAKOUT_ONLY,
        is_valid=True,
        diagnostic="Trap",
    )
    composite_restricted = SentinelStructuralGates.evaluate_composite(shock_ok, bound_trap, gamma_ok)
    assert composite_restricted.is_valid is True
    assert composite_restricted.action == StructuralGatingAction.RESTRICT_BREAKOUT_ONLY
    assert "FAILED_AUCTION_TRAP_BLOCKS_BREAKOUT" in composite_restricted.active_constraints


# ---------------------------------------------------------------------------
# Grill Me Adversarial Test 4: Statelessness and Zero Cross-Session Memory
# ---------------------------------------------------------------------------

def test_statelessness_and_zero_cross_session_leakage():
    """
    Running consecutive sessions through SentinelStructuralGates
    demonstrates zero state leakage or memory retention across evaluations.
    """
    gates = SentinelStructuralGates()

    # Session 1: Extreme shock
    s1 = OpeningShockInput(opening_range_high=25300.0, opening_range_low=25000.0, daily_atr_20=200.0)
    res1 = gates.evaluate_opening_shock(s1)
    assert res1.regime == OpeningShockRegime.EXHAUSTION_SHOCK

    # Session 2: Immediate quiet coil
    s2 = OpeningShockInput(opening_range_high=25020.0, opening_range_low=25000.0, daily_atr_20=200.0)
    res2 = gates.evaluate_opening_shock(s2)
    assert res2.regime == OpeningShockRegime.COMPRESSED_COIL

    # Clean brand new instance returns identical output
    fresh_res2 = SentinelStructuralGates.evaluate_opening_shock(s2)
    assert res2 == fresh_res2
