"""VIX-Adaptive Temperature Scaling Guard for Multiclass Probabilities.

Prevents over-smoothing during sudden market liquidations:
- When VIX velocity is calm: T -> 1.5 (smooths out noise, prevents false breakouts).
- When VIX spikes (delta VIX > 0): T -> 1.0 (sharpens probabilities into a step function).
- Guarantees calibrated probabilities sum strictly to 1.0 with rank preservation.
"""

from __future__ import annotations
import numpy as np


class TemperatureScalingGuard:
    """Dynamically adjusts Softmax temperature based on volatility velocity."""

    def __init__(self, base_temperature: float = 1.40, vix_sensitivity: float = 1.50):
        self.base_temperature = base_temperature
        self.vix_sensitivity = vix_sensitivity

    def get_adaptive_temperature(self, vix_delta: float) -> float:
        """Sharpens temperature as volatility expands."""
        if vix_delta <= 0:
            return self.base_temperature
        # Exponential sharpening towards 1.0 as VIX spikes
        decay = np.exp(-self.vix_sensitivity * vix_delta)
        temp = 1.0 + (self.base_temperature - 1.0) * decay
        return float(np.clip(temp, 1.0, self.base_temperature))

    def scale_probabilities(self, logits: np.ndarray, vix_delta: float = 0.0) -> np.ndarray:
        """Scales raw model logits into calibrated probabilities summing strictly to 1.0."""
        temp = self.get_adaptive_temperature(vix_delta)
        scaled_logits = logits / temp
        # Subtract max for numerical stability (prevents overflow)
        exp_logits = np.exp(scaled_logits - np.max(scaled_logits))
        probabilities = exp_logits / np.sum(exp_logits)
        return probabilities
