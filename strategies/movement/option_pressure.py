"""Compatibility wrapper for downstream option confirmation ownership.

Phase-2 option confirmation is attached downstream to directional raw
candidates. This compatibility callable remains registry-addressable but does
not emit standalone market-thesis candidates.
"""

from __future__ import annotations

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.strategy_parameter_profiles import resolve_required_profile_parameters

STRATEGY_ID = "option_pressure_confirmation_v1"
MOVEMENT_TYPE = "OPTION_PRESSURE_CONFIRMATION"
EMBEDDED_PROFILE_DEFAULTS = {
    "MIN_PRESSURE_SCORE": 0.45,
}
REQUIRED_PROFILE_KEYS = tuple(EMBEDDED_PROFILE_DEFAULTS)
def generate_option_pressure_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Return no standalone candidates; option confirmation is downstream-owned."""

    profile = resolve_required_profile_parameters(STRATEGY_ID, REQUIRED_PROFILE_KEYS)
    if not profile.is_valid:
        return ()
    _ = (ctx, regime)
    return ()


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_option_pressure_candidates"]
