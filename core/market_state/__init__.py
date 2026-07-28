"""Causal market-state representation primitives.

This package is research-facing and emits descriptive state variables only.
It does not generate trade signals or modify production strategy decisions.
"""

from .representation import MarketStateConfig, build_market_state_frame, state_contract

__all__ = ["MarketStateConfig", "build_market_state_frame", "state_contract"]
