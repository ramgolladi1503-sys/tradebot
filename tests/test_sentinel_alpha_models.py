import pytest
from core.market_structure.sentinel_alpha_models import (
    TargetDeltaStrikePicker,
    WallAbsorptionClassifier,
)

def test_target_delta_strike_picker_scalp():
    picker = TargetDeltaStrikePicker(max_premium_cap=250.0)
    spot = 23000.0
    strikes = [22800.0, 22900.0, 22950.0, 23000.0, 23050.0, 23100.0]
    # Synthetic LTPs
    ltps = {
        22800.0: 290.0, # Too expensive (capped at 250)
        22900.0: 195.0,
        22950.0: 155.0,
        23000.0: 115.0,
        23050.0: 82.0,
        23100.0: 55.0,
    }
    res = picker.pick_strike(spot, strikes, ltps, direction="CE", regime="RANGE_SCALP")
    assert res.is_safe is True
    # 23000 is ATM (delta ~ 0.52), matches target scalp delta
    assert res.selected_strike in [22950.0, 23000.0]
    assert res.estimated_premium <= 250.0

def test_target_delta_rejects_deep_itm_over_cap():
    picker = TargetDeltaStrikePicker(max_premium_cap=250.0)
    spot = 55000.0
    strikes = [54500.0, 54800.0, 55000.0]
    ltps = {
        54500.0: 680.0, # Deep ITM like today's BANKNIFTY 54800
        54800.0: 420.0,
        55000.0: 230.0,
    }
    res = picker.pick_strike(spot, strikes, ltps, direction="CE", regime="TREND_CONTINUATION")
    # Strikes with LTP > 250 are filtered out; selects 55000 with LTP 230
    assert res.selected_strike == 55000.0
    assert res.estimated_premium == 230.0
    assert res.is_safe is True

def test_wall_absorption_classifier():
    wavi_clf = WallAbsorptionClassifier(wavi_threshold=0.85)
    
    # Case 1: True Wall Rejection (volume fails to absorb wall)
    wavi_low = wavi_clf.calculate_wavi(
        volume_at_wall=5000,
        wall_standing_depth=50000,
        delta_oi_opposing=10000,
        avg_oi=100000,
        duration_seconds=3.0,
    )
    override, reason = wavi_clf.evaluate_override(wavi_low, remaining_depth_ratio=0.85)
    assert override is False
    assert "WALL_DEFENSE_INTACT" in reason

    # Case 2: Institutional Squeeze Breakout (wall absorbed + depth depleted)
    wavi_high = wavi_clf.calculate_wavi(
        volume_at_wall=150000,
        wall_standing_depth=50000,
        delta_oi_opposing=-20000,
        avg_oi=100000,
        duration_seconds=3.0,
    )
    override, reason = wavi_clf.evaluate_override(wavi_high, remaining_depth_ratio=0.10)
    assert override is True
    assert "SHORT_COVERING_SQUEEZE_CONFIRMED" in reason


from core.market_structure.sentinel_alpha_models import VolatilitySizingEngine

def test_volatility_sizing_engine():
    engine = VolatilitySizingEngine(exhaustion_ivr_threshold=80.0, normal_expansion_threshold=50.0)
    
    # 1. Normal cheap volatility expansion (IVR = 30) -> Full Size
    ivr_cheap = engine.calculate_intraday_ivr(current_iv=0.14, min_iv_session=0.12, max_iv_session=0.20)
    mult, is_veto, reason = engine.compute_size_multiplier(ivr_cheap, atr_exhausted=False)
    assert is_veto is False
    assert mult == 1.0
    assert "Full Size" in reason

    # 2. Elevated volatility / late impulse (IVR = 65) -> Half Size
    ivr_elevated = engine.calculate_intraday_ivr(current_iv=0.175, min_iv_session=0.12, max_iv_session=0.20)
    mult, is_veto, reason = engine.compute_size_multiplier(ivr_elevated, atr_exhausted=False)
    assert is_veto is False
    assert mult == 0.50
    assert "Half Size" in reason

    # 3. Exhausted volatility (IVR = 85) -> Hard Binary Veto
    ivr_exhausted = engine.calculate_intraday_ivr(current_iv=0.19, min_iv_session=0.12, max_iv_session=0.20)
    mult, is_veto, reason = engine.compute_size_multiplier(ivr_exhausted, atr_exhausted=False)
    assert is_veto is True
    assert mult == 0.0
    assert "VOLATILITY_EXHAUSTED_HARD_VETO" in reason

    # 4. ATR daily exhaustion flag -> Hard Binary Veto regardless of IV
    mult, is_veto, reason = engine.compute_size_multiplier(ivr_cheap, atr_exhausted=True)
    assert is_veto is True
    assert mult == 0.0
