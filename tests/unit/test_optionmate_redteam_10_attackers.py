"""
Unit Tests for OptionMate Red-Team 10 Attackers Suite.

Work Item: FEAT-OPTIONMATE-HARDENED-CALIBRATION-002
Pipeline: Hermes Architecture -> GSD Scoped Execution

Verifies defenses against:
- Attacker 1: NaN / None / malformed VIX input poisoning.
- Attacker 2: Zero-volume or micro-range (< 1.0 pt) golden candle chop.
- Attacker 3: Gap-down equality bias & spot_open conservation in grid output.
- Attacker 4: Asset tier determinism across index boundaries (NIFTY vs BANKNIFTY vs SENSEX).
- Attacker 6: Previous close point-in-time isolation in Upstox quote resolution.
- Attacker 9: Multi-asset 100-pt strike quantization for BANKNIFTY and SENSEX.
"""

import math
import pytest
from unittest.mock import MagicMock, patch

from strategies.optionmate_rbfn_strategy import (
    OptionMateRBFNStrategy,
    OptionMateGrid,
    OptionMateSignal,
    GoldenCandle,
)
from core.sentinel_dashboard_rbfn_helper import compute_official_rbfn_boundaries


class TestOptionMateRedTeam10Attackers:

    def test_attacker_1_nan_vix_fallback(self):
        """Attacker 1: NaN/None/invalid VIX must safely fall back to reference_vix (14.0)."""
        strat = OptionMateRBFNStrategy(step_size=50)

        # 1. compute_daily_grid with NaN VIX
        grid_nan = strat.compute_daily_grid(
            date="2026-11-16",
            spot_open=24000.0,
            prev_close=24000.0,
            atr_14=150.0,
            vix=float("nan"),
        )
        assert not math.isnan(grid_nan.rp1_upper)
        assert grid_nan.rp1_upper == 24102.0  # 24000 + 102 * sqrt(14/14)

        # 2. compute_daily_grid with negative/zero VIX
        grid_zero = strat.compute_daily_grid(
            date="2026-11-16",
            spot_open=24000.0,
            prev_close=24000.0,
            atr_14=150.0,
            vix=0.0,
        )
        assert grid_zero.rp1_upper == 24102.0

        # 3. generate_signal with NaN VIX
        gc = GoldenCandle.create(open=24000.0, high=24050.0, low=23990.0, close=24040.0, volume=100000.0)
        sig = strat.generate_signal(
            grid=grid_nan,
            current_spot=24020.0,
            current_atr=150.0,
            vix=float("nan"),
            golden_candle=gc,
        )
        assert sig.action == "BUY_CALL"
        assert sig.is_vetoed is False

        # 4. evaluate_midday_reversal with NaN VIX
        rev = strat.evaluate_midday_reversal(
            grid=grid_nan,
            current_spot=24070.0,
            recent_candle_closes=[24095.0, 24075.0],
            recent_candle_highs=[24105.0, 24095.0],
            recent_candle_lows=[24060.0, 24065.0],
            current_atr=150.0,
            vix=float("nan"),
        )
        assert rev is not None
        assert rev.action == "BUY_PUT"

    def test_attacker_2_zero_volume_and_micro_range_candle(self):
        """Attacker 2: Golden candle with 0 volume or < 1.0 pt range must be vetoed with GATE_2_ZERO_RANGE_CHOP."""
        strat = OptionMateRBFNStrategy(step_size=50, min_atr_frictional_hurdle=100.0)
        grid = strat.compute_daily_grid(
            date="2026-11-16",
            spot_open=24000.0,
            prev_close=24000.0,
            atr_14=150.0,
            vix=14.0,
        )

        # Case A: Volume == 0.0
        gc_zero_vol = GoldenCandle.create(open=24000.0, high=24050.0, low=23990.0, close=24040.0, volume=0.0)
        sig_a = strat.generate_signal(grid, current_spot=24020.0, current_atr=150.0, vix=14.0, golden_candle=gc_zero_vol)
        assert sig_a.action == "ABSTAIN"
        assert sig_a.is_vetoed is True
        assert "GATE_2_ZERO_RANGE_CHOP" in sig_a.veto_reason

        # Case B: Micro range (< 1.0 pt)
        gc_micro_range = GoldenCandle.create(open=24000.0, high=24000.5, low=24000.0, close=24000.2, volume=50000.0)
        assert gc_micro_range.range_pts < 1.0
        sig_b = strat.generate_signal(grid, current_spot=24020.0, current_atr=150.0, vix=14.0, golden_candle=gc_micro_range)
        assert sig_b.action == "ABSTAIN"
        assert sig_b.is_vetoed is True
        assert "GATE_2_ZERO_RANGE_CHOP" in sig_b.veto_reason

        # Case C: GoldenCandle.create range_pts floor check
        gc_flat = GoldenCandle.create(open=24000.0, high=24000.0, low=24000.0, close=24000.0, volume=1000.0)
        assert gc_flat.range_pts == 0.01  # Clamped to >= 0.01

    def test_attacker_3_gap_down_equality_bias_and_spot_open_conservation(self):
        """Attacker 3: When effective_spot == trend_decider, gap < 0 must give BEAR bias, and spot_open must be preserved."""
        strat = OptionMateRBFNStrategy(step_size=50)

        # Gap Down session: spot_open = 23900.0, prev_close = 24000.0
        # Gap = -100 <= -0.25 * 150 = -37.5 -> Gap regime -> trend_decider = spot_open = 23900.0
        # effective_spot = spot_open = 23900.0 == trend_decider
        # Since gap < 0, recommended_bias MUST be BEAR!
        grid = strat.compute_daily_grid(
            date="2026-11-16",
            spot_open=23900.0,
            prev_close=24000.0,
            atr_14=150.0,
            vix=14.0,
        )
        assert grid.trend_decider == 23900.0
        assert grid.spot_open == 23900.0  # Conserved
        assert grid.recommended_bias == "BEAR"
        assert grid.target_strike == grid.put_strike

        # Opening drive with 5m candle closing at 23920.0
        gc_5m = GoldenCandle.create(open=23900.0, high=23930.0, low=23890.0, close=23920.0, volume=80000.0)
        grid_5m = strat.compute_daily_grid(
            date="2026-11-16",
            spot_open=23900.0,
            prev_close=24000.0,
            atr_14=150.0,
            vix=14.0,
            bar_5m_equilibrium=gc_5m,
        )
        # spot_open MUST still equal 23900.0, not bar_5m.close!
        assert grid_5m.spot_open == 23900.0

    def test_attacker_4_asset_tier_determinism(self):
        """Attacker 4: Explicit symbol overrides price thresholds and resolves correct base step."""
        # 1. NIFTY
        strat_nifty = OptionMateRBFNStrategy(symbol="NIFTY")
        g_nifty = strat_nifty.compute_daily_grid("2026-11-16", spot_open=24000.0, prev_close=24000.0, atr_14=150.0, vix=14.0)
        assert g_nifty.rp1_upper - g_nifty.trend_decider == 102.0

        # 2. BANKNIFTY
        strat_bn = OptionMateRBFNStrategy(symbol="BANKNIFTY")
        g_bn = strat_bn.compute_daily_grid("2026-11-16", spot_open=51000.0, prev_close=51000.0, atr_14=350.0, vix=14.0)
        assert g_bn.rp1_upper - g_bn.trend_decider == 250.0

        # 3. SENSEX
        strat_sx = OptionMateRBFNStrategy(symbol="SENSEX")
        g_sx = strat_sx.compute_daily_grid("2026-11-16", spot_open=78000.0, prev_close=78000.0, atr_14=400.0, vix=14.0)
        assert g_sx.rp1_upper - g_sx.trend_decider == 400.0

        # 4. Boundary test: BANKNIFTY passed via compute_daily_grid symbol parameter
        strat_generic = OptionMateRBFNStrategy()
        g_bn_param = strat_generic.compute_daily_grid(
            "2026-11-16", spot_open=51000.0, prev_close=51000.0, atr_14=350.0, vix=14.0, symbol="BANKNIFTY"
        )
        assert g_bn_param.rp1_upper - g_bn_param.trend_decider == 250.0

    def test_attacker_6_prev_close_pit_isolation(self):
        """Attacker 6: In compute_official_rbfn_boundaries, Upstox quote must NOT fall back to last_price."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Simulated payload where ohlc.close is missing/None, but last_price is present (intraday price)
        mock_response.json.return_value = {
            "data": {
                "NSE_INDEX:Nifty 50": {
                    "last_price": 24150.0,
                    "ohlc": {"close": None, "open": 24000.0, "high": 24200.0, "low": 23950.0},
                }
            }
        }

        with patch("requests.get", return_value=mock_response):
            # Pass current spot of 24050.0; since ohlc.close is None and last_price fallback is removed,
            # resolved_prev_close should fall back to current_spot (24050.0), NOT last_price (24150.0)
            res = compute_official_rbfn_boundaries(spots={"NIFTY": 24050.0}, token="test_token")
            nifty_res = res["NIFTY"]
            # Flat session since spot_open = 24050.0 and resolved_prev_close = 24050.0
            assert nifty_res["trend_decider"] == 24050.0

    def test_attacker_9_multiasset_100_pt_strikes(self):
        """Attacker 9: BANKNIFTY and SENSEX must quantize strikes to 100-pt multiples in daily grid and midday reversal."""
        # 1. BANKNIFTY daily grid
        strat_bn = OptionMateRBFNStrategy(symbol="BANKNIFTY")
        g_bn = strat_bn.compute_daily_grid("2026-11-16", spot_open=51234.0, prev_close=51234.0, atr_14=350.0, vix=14.0)
        assert g_bn.call_strike % 100 == 0
        assert g_bn.put_strike % 100 == 0

        # BANKNIFTY midday reversal
        rev_bn = strat_bn.evaluate_midday_reversal(
            grid=g_bn,
            current_spot=51400.0,
            recent_candle_closes=[g_bn.rp1_upper - 10.0, g_bn.rp1_upper - 20.0],
            recent_candle_highs=[g_bn.rp1_upper + 5.0, g_bn.rp1_upper],
            recent_candle_lows=[51350.0, 51360.0],
            current_atr=350.0,
            vix=14.0,
        )
        assert rev_bn is not None
        assert rev_bn.target_strike % 100 == 0

        # 2. SENSEX daily grid
        strat_sx = OptionMateRBFNStrategy(symbol="SENSEX")
        g_sx = strat_sx.compute_daily_grid("2026-11-16", spot_open=78123.0, prev_close=78123.0, atr_14=400.0, vix=14.0)
        assert g_sx.call_strike % 100 == 0
        assert g_sx.put_strike % 100 == 0

        # SENSEX midday reversal
        rev_sx = strat_sx.evaluate_midday_reversal(
            grid=g_sx,
            current_spot=78400.0,
            recent_candle_closes=[g_sx.rp1_upper - 10.0, g_sx.rp1_upper - 20.0],
            recent_candle_highs=[g_sx.rp1_upper + 5.0, g_sx.rp1_upper],
            recent_candle_lows=[78300.0, 78320.0],
            current_atr=400.0,
            vix=14.0,
        )
        assert rev_sx is not None
        assert rev_sx.target_strike % 100 == 0
