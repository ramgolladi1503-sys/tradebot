import pytest
import numpy as np
from ml.continuous_regime import extract_continuous_regime, calculate_dynamic_multiplier

def test_extract_continuous_regime_fallback():
    # Less than 20 periods should fail open with 0.5s
    vec = extract_continuous_regime([100.0] * 10, [1.0] * 10)
    assert vec.trend_strength == 0.5
    assert vec.volatility_expansion == 0.5
    assert vec.mean_reversion_probability == 0.5

def test_extract_continuous_regime_strong_trend():
    # Perfectly linear prices = 1.0 trend strength
    prices = np.linspace(100, 120, 20).tolist()
    atr = [1.0] * 20
    
    vec = extract_continuous_regime(prices, atr)
    assert vec.trend_strength > 0.95
    assert vec.volatility_expansion == 0.5 # 1.0 / (1.0) / 2 = 0.5
    assert vec.mean_reversion_probability < 0.1 # strong trend means low MR

def test_extract_continuous_regime_volatility_expansion():
    prices = [100.0] * 20 # flat prices -> 0 trend
    
    # ATR average is 1.0, but current is 2.0 (doubled!)
    atr = [1.0] * 19 + [2.0]
    
    vec = extract_continuous_regime(prices, atr)
    assert vec.trend_strength == 0.0 # flat line
    assert vec.volatility_expansion > 0.9 # (2.0 / ~1.05) / 2 = ~0.95
    assert vec.mean_reversion_probability > 0.9 # 0 trend + high vol = high MR probability

def test_calculate_dynamic_multiplier():
    vec = extract_continuous_regime([100.0] * 20, [1.0] * 19 + [2.0]) # high vol
    
    # Base is 100
    # Volatility is ~0.95. Adjustment = (0.95 - 0.5) * 0.5 * 2.0 = 0.45 * 1.0 = +45%
    mult = calculate_dynamic_multiplier(100.0, vec, sensitivity=0.5)
    assert mult > 140.0
    
    # If neutral (0.5), it should be 100
    vec_neutral = extract_continuous_regime([], []) # returns 0.5s
    mult2 = calculate_dynamic_multiplier(100.0, vec_neutral, sensitivity=0.5)
    assert mult2 == 100.0
