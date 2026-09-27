"""Research-only strategy fidelity checks. Not an execution authorization."""
from .contracts import (
    ResearchStrategySpec, SourceRule, TimestampPolicy, VerificationReport,
    verify_strategy_spec, check_causality
)
__all__ = ["ResearchStrategySpec", "SourceRule", "TimestampPolicy", "VerificationReport",
           "verify_strategy_spec", "check_causality"]
