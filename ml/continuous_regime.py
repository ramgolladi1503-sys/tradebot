import numpy as np
import logging
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)

@dataclass
class RegimeVector:
    """
    Continuous ML Feature Vector representing the current market state.
    Values are strictly bounded between 0.0 and 1.0.
    """
    trend_strength: float 
    volatility_expansion: float
    mean_reversion_probability: float

def extract_continuous_regime(prices: List[float], atr_history: List[float]) -> RegimeVector:
    """
    Transforms hardcoded discrete regime tags into a continuous ML feature vector.
    
    Args:
        prices: List of recent closing prices (ideally 20+ periods).
        atr_history: List of recent ATR values matching prices length.
        
    Returns:
        RegimeVector with properties [0.0, 1.0]
    """
    if not prices or len(prices) < 20 or not atr_history or len(atr_history) < 20:
        return RegimeVector(0.5, 0.5, 0.5) # Fail open with neutral vector
        
    try:
        # Calculate Trend Strength using R-squared of linear regression
        y = np.array(prices[-20:])
        x = np.arange(len(y))
        
        # Fit line
        slope, intercept = np.polyfit(x, y, 1)
        y_pred = slope * x + intercept
        
        # R-squared
        ss_res = np.sum((y - y_pred)**2)
        ss_tot = np.sum((y - np.mean(y))**2)
        r_squared = 1 - (ss_res / (ss_tot + 1e-9))
        
        # Trend strength is the R-squared bounded [0, 1]
        # Multiply by a slope significance factor (if slope is near 0, trend is 0)
        percent_slope = abs(slope) / (np.mean(y) + 1e-9)
        slope_discount = min(1.0, percent_slope / 0.0005) # Need at least 0.05% slope per period
        
        trend_strength = max(0.0, min(1.0, float(r_squared * slope_discount)))
        
        # Calculate Volatility Expansion
        # Current ATR vs Average ATR over the window
        current_atr = atr_history[-1]
        avg_atr = np.mean(atr_history[-20:])
        
        vol_ratio = current_atr / (avg_atr + 1e-9)
        # Bounded between 0 and 1, where 1.0 means ATR has doubled or more
        volatility_expansion = max(0.0, min(1.0, float(vol_ratio / 2.0)))
        
        # Mean Reversion Probability is generally inverse to trend strength,
        # but also peaks when volatility is expanding and trend is weak
        mr_prob = (1.0 - trend_strength) * (0.5 + volatility_expansion / 2.0)
        mean_reversion_probability = max(0.0, min(1.0, mr_prob))
        
        return RegimeVector(
            trend_strength=round(trend_strength, 4),
            volatility_expansion=round(volatility_expansion, 4),
            mean_reversion_probability=round(mean_reversion_probability, 4)
        )
        
    except Exception as e:
        logger.error(f"Continuous regime extraction failed: {e}")
        return RegimeVector(0.5, 0.5, 0.5)

def calculate_dynamic_multiplier(base_value: float, regime_vector: RegimeVector, sensitivity: float = 0.5) -> float:
    """
    Dynamically scales a multiplier based on the continuous regime vector.
    Replaces hardcoded dicts in core/regime_router.py.
    
    Args:
        base_value: The base threshold/buffer to scale.
        regime_vector: The continuous regime state.
        sensitivity: How much the volatility impacts the multiplier (0.5 = +/- 50%).
        
    Returns:
        float: The scaled dynamic multiplier.
    """
    try:
        # If volatility is 1.0 (max), multiplier increases by sensitivity
        # If volatility is 0.0 (min), multiplier decreases by sensitivity
        # 0.5 volatility is neutral (no adjustment)
        adjustment = (regime_vector.volatility_expansion - 0.5) * sensitivity * 2.0
        return base_value * (1.0 + adjustment)
    except Exception:
        return base_value
