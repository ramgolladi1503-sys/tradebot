from typing import Dict, Any, Optional, Set

# Policy Results
ELIGIBLE = "ELIGIBLE"
ELIGIBLE_WITH_PENALTY = "ELIGIBLE_WITH_PENALTY"
WATCHLIST_ONLY = "WATCHLIST_ONLY"
ADVISORY_ONLY = "ADVISORY_ONLY"
BLOCKED = "BLOCKED"

REGIME_POLICY_VERSION = "1.0.0"

class StrategyRequirements:
    def __init__(
        self,
        requires_stable_regime: bool,
        allowed_session_buckets: Set[str],
        preferred_entropy_states: Set[str],
        blocked_entropy_states: Set[str],
        entropy_policy: str
    ):
        self.requires_stable_regime = requires_stable_regime
        self.allowed_session_buckets = allowed_session_buckets
        self.preferred_entropy_states = preferred_entropy_states
        self.blocked_entropy_states = blocked_entropy_states
        self.entropy_policy = entropy_policy

# Initial defaults as requested
STRATEGY_REGISTRY: Dict[str, StrategyRequirements] = {
    "ORB": StrategyRequirements(
        requires_stable_regime=False,
        allowed_session_buckets={"OPEN_DISCOVERY", "MORNING_TREND"},
        preferred_entropy_states={"NORMAL", "LOW"},
        blocked_entropy_states=set(),
        entropy_policy="allow_high_with_volatility"
    ),
    "MEAN_REVERSION": StrategyRequirements(
        requires_stable_regime=True,
        allowed_session_buckets={"DEFAULT", "MIDDAY_CHOP", "LATE_AFTERNOON"},
        preferred_entropy_states={"NORMAL", "LOW"},
        blocked_entropy_states={"HIGH", "EXTREME"},
        entropy_policy="block_high"
    ),
    "SHORT_PREMIUM": StrategyRequirements(
        requires_stable_regime=True,
        allowed_session_buckets={"MIDDAY_CHOP"},
        preferred_entropy_states={"LOW"},
        blocked_entropy_states={"HIGH", "EXTREME"},
        entropy_policy="block_high_or_poor_liquidity"
    ),
    "TREND_CONTINUATION": StrategyRequirements(
        requires_stable_regime=False,
        allowed_session_buckets={"MORNING_TREND", "AFTERNOON_TREND", "DEFAULT"},
        preferred_entropy_states={"NORMAL"},
        blocked_entropy_states={"EXTREME"},
        entropy_policy="allow_with_trend"
    )
}

def evaluate_strategy_regime_policy(
    strategy: str,
    session_bucket: str,
    entropy_value: float,
    normalized_entropy: float,
    entropy_state: str,
    trend_state: str = "UNKNOWN",
    volatility_expansion: bool = False,
    volume_impulse: bool = False,
    liquidity_quality: str = "UNKNOWN",
    is_expiry_day: bool = False
) -> Dict[str, Any]:
    """
    Evaluates market regime context against strategy requirements to determine 
    candidate suitability.
    """
    strategy_upper = str(strategy).upper()
    reqs = STRATEGY_REGISTRY.get(strategy_upper)

    if not reqs:
        # Unknown strategy -> Default to conservative behavior
        if entropy_state in {"HIGH", "EXTREME"}:
            return {
                "policy_result": BLOCKED,
                "reason": "unknown_strategy_high_entropy_blocked",
                "candidate_generation_allowed": False
            }
        return {
            "policy_result": WATCHLIST_ONLY,
            "reason": "unknown_strategy_conservative_default",
            "candidate_generation_allowed": True
        }

    if entropy_state == "UNKNOWN":
        return {
            "policy_result": ADVISORY_ONLY,
            "reason": "unknown_entropy_state_advisory",
            "candidate_generation_allowed": True
        }

    # Evaluate Liquidity
    if reqs.entropy_policy == "block_high_or_poor_liquidity" and liquidity_quality == "POOR":
        return {
            "policy_result": BLOCKED,
            "reason": "poor_liquidity_blocked",
            "candidate_generation_allowed": False
        }

    # Evaluate Entropy
    if entropy_state in reqs.blocked_entropy_states:
        if strategy_upper == "MEAN_REVERSION" and entropy_state == "HIGH":
            return {
                "policy_result": ADVISORY_ONLY,
                "reason": "mean_reversion_high_entropy_advisory",
                "candidate_generation_allowed": True
            }
        return {
            "policy_result": BLOCKED,
            "reason": f"entropy_state_{entropy_state.lower()}_blocked",
            "candidate_generation_allowed": False
        }

    # Special handling per policy
    if reqs.entropy_policy == "allow_high_with_volatility" and entropy_state in {"HIGH", "EXTREME"}:
        if volatility_expansion or volume_impulse:
            if session_bucket == "OPEN_DISCOVERY":
                return {
                    "policy_result": ELIGIBLE_WITH_PENALTY,
                    "reason": "open_discovery_high_entropy_with_volatility_expansion",
                    "candidate_generation_allowed": True
                }
            return {
                "policy_result": ELIGIBLE_WITH_PENALTY,
                "reason": "high_entropy_with_volatility_expansion",
                "candidate_generation_allowed": True
            }
        return {
            "policy_result": BLOCKED,
            "reason": "high_entropy_missing_volatility_expansion",
            "candidate_generation_allowed": False
        }

    if reqs.entropy_policy == "allow_with_trend" and entropy_state in {"HIGH", "NORMAL"}:
        if trend_state == "STRONG":
            return {
                "policy_result": ELIGIBLE,
                "reason": "trend_confirmation_valid",
                "candidate_generation_allowed": True
            }
        elif entropy_state == "HIGH":
            return {
                "policy_result": BLOCKED,
                "reason": "high_entropy_missing_trend_confirmation",
                "candidate_generation_allowed": False
            }

    if strategy_upper == "MEAN_REVERSION":
        if entropy_state in {"NORMAL", "LOW"} and (trend_state == "RANGE" or trend_state == "WEAK"):
            return {
                "policy_result": ELIGIBLE,
                "reason": "normal_entropy_range_regime_eligible",
                "candidate_generation_allowed": True
            }

    # Default to eligible if no explicit block
    return {
        "policy_result": ELIGIBLE,
        "reason": "strategy_regime_requirements_met",
        "candidate_generation_allowed": True
    }
