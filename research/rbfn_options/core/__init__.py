"""RBFN Options Core Package.

Deterministic, scikit-free Radial Basis Function Network implementation,
causal spot boundary model, point-in-time low-premium strike selector,
and option reversal execution replay.
"""
from __future__ import annotations

from research.rbfn_options.core.low_premium_strike_selector import (
    PREMIUM_LADDER_TIERS,
    OptionContractCandidate,
    select_low_premium_strike,
)
from research.rbfn_options.core.rbfn_engine import GaussianRBFNetwork
from research.rbfn_options.core.spot_boundary_model import (
    CausalSpotBoundaryModel,
    SpotBoundaryForecast,
)
from research.rbfn_options.core.strike_reversal_replay import (
    ReversalReplayEngine,
    ReversalReplayResult,
    ReversalTrade,
    StatutoryCosts,
)

__all__ = [
    "GaussianRBFNetwork",
    "CausalSpotBoundaryModel",
    "SpotBoundaryForecast",
    "PREMIUM_LADDER_TIERS",
    "OptionContractCandidate",
    "select_low_premium_strike",
    "StatutoryCosts",
    "ReversalTrade",
    "ReversalReplayResult",
    "ReversalReplayEngine",
]
