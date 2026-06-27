from dataclasses import dataclass

@dataclass(frozen=True)
class ValidationConfig:
    """
    Configuration for the Statistical Validation Engine.
    Controls sample thresholds, resampling parameters, and stress scenario multipliers.
    """
    minimum_usable_sample_size: int = 30
    minimum_regime_sample_size: int = 15
    
    bootstrap_iterations: int = 1000
    bootstrap_confidence_level: float = 0.95
    bootstrap_seed: int = 42 # For deterministic tests
    
    walk_forward_window_size: int = 30
    walk_forward_minimum_internal_size: int = 15
    
    stability_rolling_window_size: int = 30
    
    # Cost Stress Multipliers (for cost_sensitivity.py)
    increased_slippage_multiplier: float = 2.0
    higher_brokerage_multiplier: float = 2.0
    spread_expansion_multiplier: float = 2.0
