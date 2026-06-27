from enum import Enum

class ValidationStatus(Enum):
    """Overall status of the statistical validation."""
    VALID = "VALID"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    UNDEFINED = "UNDEFINED"

class SignificanceLevel(Enum):
    """Confidence in the statistical results."""
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

class StabilityStatus(Enum):
    """Walk-forward and temporal stability status."""
    STABLE = "STABLE"
    UNSTABLE = "UNSTABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

class DrawdownStatus(Enum):
    """Assessment of the drawdown profile."""
    WITHIN_LIMITS = "WITHIN_LIMITS"
    EXCESSIVE = "EXCESSIVE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

