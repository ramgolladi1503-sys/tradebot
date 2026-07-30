from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet

# Policy results
ELIGIBLE = "ELIGIBLE"
ELIGIBLE_WITH_PENALTY = "ELIGIBLE_WITH_PENALTY"
WATCHLIST_ONLY = "WATCHLIST_ONLY"
ADVISORY_ONLY = "ADVISORY_ONLY"
BLOCKED = "BLOCKED"

REGIME_POLICY_VERSION = "2.0.0"

CANONICAL_ENTROPY_STATES = frozenset({"LOW", "NORMAL", "HIGH", "EXTREME", "UNKNOWN"})
CANONICAL_SESSION_BUCKETS = frozenset(
    {
        "DEFAULT",
        "OPEN_DISCOVERY",
        "MID_SESSION",
        "CLOSING_VOL",
        "EXPIRY_DAY",
        "EVENT_MODE",
        "UNKNOWN",
    }
)


@dataclass(frozen=True)
class StrategyRequirements:
    requires_stable_regime: bool
    allowed_session_buckets: FrozenSet[str]
    preferred_entropy_states: FrozenSet[str]
    blocked_entropy_states: FrozenSet[str]
    entropy_policy: str


STRATEGY_ALIASES: dict[str, str] = {
    # Opening / ORB family
    "ORB": "OPENING_BREAKOUT",
    "OPENING_DRIVE": "OPENING_BREAKOUT",
    "OPENING_DRIVE_V1": "OPENING_BREAKOUT",
    "OPENING_RANGE_BREAKOUT": "OPENING_BREAKOUT",
    "OPENING_RANGE_RETEST": "OPENING_BREAKOUT",
    "OPENING_RANGE_RETEST_V1": "OPENING_BREAKOUT",
    # Mean-reversion / reversal family
    "MEAN_REVERSION": "MEAN_REVERSION",
    "MEAN_REVERSION_EXTENSION": "MEAN_REVERSION",
    "MEAN_REVERSION_EXTENSION_V1": "MEAN_REVERSION",
    "EXHAUSTION_REVERSAL": "MEAN_REVERSION",
    "EXHAUSTION_REVERSAL_V1": "MEAN_REVERSION",
    "FAILED_BREAKOUT_TRAP": "MEAN_REVERSION",
    "FAILED_BREAKOUT_TRAP_V1": "MEAN_REVERSION",
    "MARKET_EVENT_GRAPH_REVERSAL": "MEAN_REVERSION",
    "MARKET_EVENT_GRAPH_REVERSAL_V1": "MEAN_REVERSION",
    # Directional continuation family
    "TREND_CONTINUATION": "TREND_CONTINUATION",
    "TREND_PULLBACK": "TREND_CONTINUATION",
    "TREND_PULLBACK_V1": "TREND_CONTINUATION",
    "VWAP_RECLAIM_REJECTION": "TREND_CONTINUATION",
    "VWAP_RECLAIM_REJECTION_V1": "TREND_CONTINUATION",
    "COMPRESSION_BREAKOUT": "TREND_CONTINUATION",
    "COMPRESSION_BREAKOUT_V1": "TREND_CONTINUATION",
    "LATE_DAY_MOMENTUM": "TREND_CONTINUATION",
    "LATE_DAY_MOMENTUM_V1": "TREND_CONTINUATION",
    "OPTION_PRESSURE": "TREND_CONTINUATION",
    "OPTION_PRESSURE_V1": "TREND_CONTINUATION",
    # Event family
    "EVENT_VOLATILITY": "EVENT_VOLATILITY",
    "EVENT_VOLATILITY_EXPANSION": "EVENT_VOLATILITY",
    "EVENT_VOLATILITY_EXPANSION_V1": "EVENT_VOLATILITY",
    # Legacy short-premium family retained for policy compatibility
    "SHORT_PREMIUM": "SHORT_PREMIUM",
    "SHORT_STRADDLE": "SHORT_PREMIUM",
    "SHORT_STRANGLE": "SHORT_PREMIUM",
    # Explicit no-trade family
    "NO_TRADE": "NO_TRADE",
    "NO_TRADE_CHOP": "NO_TRADE",
    "NO_TRADE_CHOP_V1": "NO_TRADE",
}

SESSION_ALIASES: dict[str, str] = {
    "": "DEFAULT",
    "DEFAULT": "DEFAULT",
    "OPEN": "OPEN_DISCOVERY",
    "OPEN_DISCOVERY": "OPEN_DISCOVERY",
    "MORNING_TREND": "OPEN_DISCOVERY",
    "MIDDAY": "MID_SESSION",
    "MIDDAY_CHOP": "MID_SESSION",
    "MID_SESSION": "MID_SESSION",
    "AFTERNOON": "MID_SESSION",
    "CLOSING_VOL": "CLOSING_VOL",
    "LATE_DAY": "CLOSING_VOL",
    "LATE_AFTERNOON": "CLOSING_VOL",
    "AFTERNOON_TREND": "CLOSING_VOL",
    "EXPIRY": "EXPIRY_DAY",
    "EXPIRY_DAY": "EXPIRY_DAY",
    "EVENT": "EVENT_MODE",
    "EVENT_MODE": "EVENT_MODE",
}

_ALL_TRADING_SESSIONS = frozenset(
    {
        "DEFAULT",
        "OPEN_DISCOVERY",
        "MID_SESSION",
        "CLOSING_VOL",
        "EXPIRY_DAY",
        "EVENT_MODE",
    }
)

STRATEGY_REGISTRY: Dict[str, StrategyRequirements] = {
    "OPENING_BREAKOUT": StrategyRequirements(
        requires_stable_regime=False,
        allowed_session_buckets=frozenset({"OPEN_DISCOVERY", "EXPIRY_DAY"}),
        preferred_entropy_states=frozenset({"NORMAL", "LOW"}),
        blocked_entropy_states=frozenset(),
        entropy_policy="allow_high_with_volatility",
    ),
    "MEAN_REVERSION": StrategyRequirements(
        requires_stable_regime=True,
        allowed_session_buckets=frozenset(
            {"DEFAULT", "MID_SESSION", "CLOSING_VOL", "EXPIRY_DAY"}
        ),
        preferred_entropy_states=frozenset({"NORMAL", "LOW"}),
        blocked_entropy_states=frozenset({"EXTREME"}),
        entropy_policy="high_advisory_extreme_block",
    ),
    "SHORT_PREMIUM": StrategyRequirements(
        requires_stable_regime=True,
        allowed_session_buckets=frozenset({"MID_SESSION", "DEFAULT"}),
        preferred_entropy_states=frozenset({"LOW"}),
        blocked_entropy_states=frozenset({"HIGH", "EXTREME"}),
        entropy_policy="block_high_or_poor_liquidity",
    ),
    "TREND_CONTINUATION": StrategyRequirements(
        requires_stable_regime=False,
        allowed_session_buckets=frozenset(
            {
                "DEFAULT",
                "OPEN_DISCOVERY",
                "MID_SESSION",
                "CLOSING_VOL",
                "EXPIRY_DAY",
            }
        ),
        preferred_entropy_states=frozenset({"NORMAL", "LOW"}),
        blocked_entropy_states=frozenset({"EXTREME"}),
        entropy_policy="allow_high_with_trend_confirmation",
    ),
    "EVENT_VOLATILITY": StrategyRequirements(
        requires_stable_regime=False,
        allowed_session_buckets=_ALL_TRADING_SESSIONS,
        preferred_entropy_states=frozenset({"NORMAL", "HIGH", "EXTREME"}),
        blocked_entropy_states=frozenset(),
        entropy_policy="event_uncertainty_expected",
    ),
    "NO_TRADE": StrategyRequirements(
        requires_stable_regime=False,
        allowed_session_buckets=_ALL_TRADING_SESSIONS,
        preferred_entropy_states=frozenset(),
        blocked_entropy_states=frozenset({"LOW", "NORMAL", "HIGH", "EXTREME"}),
        entropy_policy="always_block",
    ),
}


def canonical_strategy_family(strategy: str) -> str | None:
    key = str(strategy or "").strip().upper().replace("-", "_").replace(" ", "_")
    if not key:
        return None
    return STRATEGY_ALIASES.get(key)


def canonical_session_bucket(session_bucket: str, *, is_expiry_day: bool = False) -> str:
    raw = str(session_bucket or "").strip().upper().replace("-", "_").replace(" ", "_")
    resolved = SESSION_ALIASES.get(raw)
    if resolved is None:
        return "UNKNOWN"
    if is_expiry_day and resolved == "DEFAULT":
        return "EXPIRY_DAY"
    return resolved


def canonical_entropy_state(entropy_state: str, normalized_entropy: float | None) -> str:
    state = str(entropy_state or "").strip().upper()
    if state in CANONICAL_ENTROPY_STATES:
        return state
    try:
        value = float(normalized_entropy)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        return "UNKNOWN"
    if value <= 0.35:
        return "LOW"
    if value <= 0.80:
        return "NORMAL"
    if value < 0.95:
        return "HIGH"
    return "EXTREME"


def _result(
    policy_result: str,
    reason: str,
    *,
    family: str | None,
    session_bucket: str,
    entropy_state: str,
    candidate_generation_allowed: bool,
    requirements: StrategyRequirements | None = None,
) -> Dict[str, Any]:
    return {
        "policy_result": policy_result,
        "reason": reason,
        "candidate_generation_allowed": bool(candidate_generation_allowed),
        "strategy_family": family,
        "canonical_session_bucket": session_bucket,
        "canonical_entropy_state": entropy_state,
        "requires_stable_regime": (
            bool(requirements.requires_stable_regime) if requirements else None
        ),
        "regime_policy_version": REGIME_POLICY_VERSION,
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
    is_expiry_day: bool = False,
    regime_status: str | None = None,
    stable_regime: bool | None = None,
) -> Dict[str, Any]:
    """Evaluate a candidate against the canonical strategy/regime policy.

    Unknown strategies never become executable. Explicitly invalid regime truth
    remains advisory or blocked. Policy evaluation is read-only.
    """
    del entropy_value  # Retained for backward-compatible call signatures.

    family = canonical_strategy_family(strategy)
    session = canonical_session_bucket(
        session_bucket,
        is_expiry_day=is_expiry_day,
    )
    state = canonical_entropy_state(entropy_state, normalized_entropy)
    trend = str(trend_state or "UNKNOWN").strip().upper()
    liquidity = str(liquidity_quality or "UNKNOWN").strip().upper()
    status = str(regime_status or "").strip().upper()

    if family is None:
        if state in {"HIGH", "EXTREME"}:
            return _result(
                BLOCKED,
                "unknown_strategy_high_entropy_blocked",
                family=None,
                session_bucket=session,
                entropy_state=state,
                candidate_generation_allowed=False,
            )
        return _result(
            WATCHLIST_ONLY,
            "unknown_strategy_conservative_default",
            family=None,
            session_bucket=session,
            entropy_state=state,
            candidate_generation_allowed=True,
        )

    requirements = STRATEGY_REGISTRY[family]

    if family == "NO_TRADE":
        return _result(
            BLOCKED,
            "explicit_no_trade_strategy",
            family=family,
            session_bucket=session,
            entropy_state=state,
            candidate_generation_allowed=False,
            requirements=requirements,
        )

    if session not in requirements.allowed_session_buckets:
        return _result(
            BLOCKED,
            f"session_bucket_{session.lower()}_blocked",
            family=family,
            session_bucket=session,
            entropy_state=state,
            candidate_generation_allowed=False,
            requirements=requirements,
        )

    if state == "UNKNOWN":
        return _result(
            ADVISORY_ONLY,
            "unknown_entropy_state_advisory",
            family=family,
            session_bucket=session,
            entropy_state=state,
            candidate_generation_allowed=True,
            requirements=requirements,
        )

    if status in {"INVALID_INPUT", "INSUFFICIENT_DATA"}:
        return _result(
            ADVISORY_ONLY,
            f"regime_status_{status.lower()}_advisory",
            family=family,
            session_bucket=session,
            entropy_state=state,
            candidate_generation_allowed=True,
            requirements=requirements,
        )

    if requirements.requires_stable_regime and (
        stable_regime is False or status in {"UNCERTAIN", "UNKNOWN"}
    ):
        return _result(
            ADVISORY_ONLY,
            "stable_regime_required_advisory",
            family=family,
            session_bucket=session,
            entropy_state=state,
            candidate_generation_allowed=True,
            requirements=requirements,
        )

    if (
        requirements.entropy_policy == "block_high_or_poor_liquidity"
        and liquidity == "POOR"
    ):
        return _result(
            BLOCKED,
            "poor_liquidity_blocked",
            family=family,
            session_bucket=session,
            entropy_state=state,
            candidate_generation_allowed=False,
            requirements=requirements,
        )

    if state in requirements.blocked_entropy_states:
        return _result(
            BLOCKED,
            f"entropy_state_{state.lower()}_blocked",
            family=family,
            session_bucket=session,
            entropy_state=state,
            candidate_generation_allowed=False,
            requirements=requirements,
        )

    if family == "OPENING_BREAKOUT" and state in {"HIGH", "EXTREME"}:
        if volatility_expansion or volume_impulse:
            return _result(
                ELIGIBLE_WITH_PENALTY,
                "opening_high_entropy_with_expansion",
                family=family,
                session_bucket=session,
                entropy_state=state,
                candidate_generation_allowed=True,
                requirements=requirements,
            )
        return _result(
            BLOCKED,
            "opening_high_entropy_without_expansion",
            family=family,
            session_bucket=session,
            entropy_state=state,
            candidate_generation_allowed=False,
            requirements=requirements,
        )

    if family == "MEAN_REVERSION":
        if state == "HIGH":
            return _result(
                ADVISORY_ONLY,
                "mean_reversion_high_entropy_advisory",
                family=family,
                session_bucket=session,
                entropy_state=state,
                candidate_generation_allowed=True,
                requirements=requirements,
            )
        if trend in {"STRONG", "TREND", "TREND_EXPANSION"}:
            return _result(
                ADVISORY_ONLY,
                "mean_reversion_strong_trend_advisory",
                family=family,
                session_bucket=session,
                entropy_state=state,
                candidate_generation_allowed=True,
                requirements=requirements,
            )

    if family == "TREND_CONTINUATION" and state == "HIGH":
        trend_confirmed = trend in {
            "STRONG",
            "TREND",
            "TREND_EXPANSION",
        }
        if trend_confirmed or volatility_expansion or volume_impulse:
            return _result(
                ELIGIBLE_WITH_PENALTY,
                "trend_high_entropy_with_confirmation",
                family=family,
                session_bucket=session,
                entropy_state=state,
                candidate_generation_allowed=True,
                requirements=requirements,
            )
        return _result(
            BLOCKED,
            "trend_high_entropy_without_confirmation",
            family=family,
            session_bucket=session,
            entropy_state=state,
            candidate_generation_allowed=False,
            requirements=requirements,
        )

    if family == "EVENT_VOLATILITY" and state in {"HIGH", "EXTREME"}:
        return _result(
            ELIGIBLE_WITH_PENALTY,
            "event_uncertainty_expected_defined_risk",
            family=family,
            session_bucket=session,
            entropy_state=state,
            candidate_generation_allowed=True,
            requirements=requirements,
        )

    if state not in requirements.preferred_entropy_states:
        return _result(
            ELIGIBLE_WITH_PENALTY,
            f"entropy_state_{state.lower()}_non_preferred",
            family=family,
            session_bucket=session,
            entropy_state=state,
            candidate_generation_allowed=True,
            requirements=requirements,
        )

    return _result(
        ELIGIBLE,
        "strategy_regime_requirements_met",
        family=family,
        session_bucket=session,
        entropy_state=state,
        candidate_generation_allowed=True,
        requirements=requirements,
    )
