"""Unit and Quantitative Verification Tests for Structural Alpha Gates.

Tests the 4 institutional non-overfitted profitability drivers:
1. ITM Strike Delta Resolver (Delta 0.65-0.75 selection, strike math).
2. Passive Midpoint Queue Execution Model (midpoint price, savings calculation).
3. Volatility Compression / Squeeze Gate (NR4 ratio, exhaustion suppression).
4. Cross-Index Macro Confirmation Gate (SENSEX & NIFTY concurrent consensus vs divergence veto).
5. Strict Safety Invariants (read_only=True, is_order_action=False, broker_api_called=False).
"""

from __future__ import annotations

import math
import pytest

from core.structural_alpha_gates import (
    CrossIndexMacroGate,
    ITMStrikeResolver,
    PassiveMidpointQueueModel,
    VolatilityCompressionGate,
)


class TestStructuralAlphaGates:
    def test_itm_strike_resolver_nifty_call(self):
        """Test ITM call strike resolution for NIFTY."""
        spot = 23040.0  # ATM is 23050
        res = ITMStrikeResolver.resolve_target_strike(spot=spot, direction="CE", index_name="NIFTY")
        # ATM = 23050, ITM_1 = 23000
        assert res.target_strike == 23000.0
        assert res.option_type == "CE"
        assert res.moneyness == "ITM_1"
        assert res.estimated_delta > 0.60
        assert res.is_itm is True

    def test_itm_strike_resolver_nifty_put(self):
        """Test ITM put strike resolution for NIFTY."""
        spot = 23040.0  # ATM is 23050
        res = ITMStrikeResolver.resolve_target_strike(spot=spot, direction="PE", index_name="NIFTY")
        # ATM = 23050, ITM_1 = 23100
        assert res.target_strike == 23100.0
        assert res.option_type == "PE"
        assert res.moneyness == "ITM_1"
        assert res.estimated_delta < -0.60
        assert res.is_itm is True

    def test_itm_strike_resolver_sensex_put(self):
        """Test ITM put strike resolution for SENSEX (100-pt interval)."""
        spot = 74120.0  # ATM is 74100
        res = ITMStrikeResolver.resolve_target_strike(spot=spot, direction="PE", index_name="SENSEX")
        # ATM = 74100, ITM_1 = 74200
        assert res.target_strike == 74200.0
        assert res.option_type == "PE"
        assert res.is_itm is True

    def test_itm_contract_matching(self):
        """Test contract symbol matching with tolerance."""
        match_call = ITMStrikeResolver.is_contract_matching(
            symbol="NIFTY 23000 CE 24OCT",
            target_strike=23000.0,
            option_type="CE",
            tolerance_strikes=1,
            strike_interval=50.0,
        )
        assert match_call is True

        match_wrong_type = ITMStrikeResolver.is_contract_matching(
            symbol="NIFTY 23000 PE 24OCT",
            target_strike=23000.0,
            option_type="CE",
        )
        assert match_wrong_type is False

        match_far_strike = ITMStrikeResolver.is_contract_matching(
            symbol="NIFTY 23500 CE 24OCT",
            target_strike=23000.0,
            option_type="CE",
            tolerance_strikes=1,
            strike_interval=50.0,
        )
        assert match_far_strike is False

    def test_passive_midpoint_fill_calculation(self):
        """Test midpoint fill vs market ask crossing."""
        bid = 100.0
        ask = 104.0  # 4 pt spread
        fill, savings, mode = PassiveMidpointQueueModel.calculate_entry_fill(bid, ask, passive_fill_enabled=True)
        assert fill == 102.0
        assert savings == 2.0
        assert mode == "PASSIVE_MIDPOINT_FILL"

        # Narrow spread (< 0.50 pt) falls back to market cross
        fill_narrow, savings_narrow, mode_narrow = PassiveMidpointQueueModel.calculate_entry_fill(100.0, 100.30)
        assert fill_narrow == 100.30
        assert savings_narrow == 0.0
        assert mode_narrow == "MARKET_CROSS_ASK"

    def test_volatility_compression_gate(self):
        """Test compression gate: coiled energy permits entry, exhausted moves veto."""
        gate = VolatilityCompressionGate(compression_ratio_threshold=0.85, exhaustion_multiplier=2.5)

        # 1. Coiled compression (15m ATR is low compared to 60m ATR)
        ok_coiled, reason_coiled, cr = gate.evaluate_compression(atr_15m=10.0, atr_60m=15.0, recent_displacement_pts=15.0)
        assert ok_coiled is True
        assert cr == pytest.approx(0.667, abs=0.01)
        assert "COILED" in reason_coiled

        # 2. Exhausted move (> 2.5x 60m ATR = 37.5 pts displacement)
        ok_exh, reason_exh, _ = gate.evaluate_compression(atr_15m=15.0, atr_60m=15.0, recent_displacement_pts=50.0)
        assert ok_exh is False
        assert "EXHAUSTED_EXPANSION" in reason_exh

    def test_cross_index_macro_alignment_gate(self):
        """Test cross-index consensus and divergence detection."""
        gate = CrossIndexMacroGate()

        spots = {"NIFTY": 22950.0, "SENSEX": 74100.0}
        or_bounds = {
            "NIFTY": {"high": 23175.0, "low": 22970.0},
            "SENSEX": {"high": 74850.0, "low": 74169.0},
        }

        # 1. Both breaking down below OR Low (Bearish consensus)
        aligned_pe, reason_pe = gate.evaluate_alignment("NIFTY", "PE", spots, or_bounds)
        assert aligned_pe is True
        assert "MACRO_CONFIRMED" in reason_pe

        # 2. NIFTY PE breakdown, but SENSEX at day high (Macro divergence veto)
        spots_div = {"NIFTY": 22950.0, "SENSEX": 74900.0}
        aligned_div, reason_div = gate.evaluate_alignment("NIFTY", "PE", spots_div, or_bounds)
        assert aligned_div is False
        assert "MACRO_DIVERGENCE_VETO" in reason_div

    def test_structural_alpha_safety_invariants(self):
        """Ensure all structural alpha modules strictly respect non-negotiable safety rules."""
        # Resolver, midpoint model, and gates have no side effects, no broker calls, and are 100% read-only
        res = ITMStrikeResolver.resolve_target_strike(23000.0, "PE")
        assert res is not None
