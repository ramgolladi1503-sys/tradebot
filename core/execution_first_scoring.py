from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import config as cfg


@dataclass(frozen=True)
class ExecutionFirstScoreDecision:
    adjusted_score: float
    cap_applied: float | None
    penalty_applied: float
    reasons: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)


def _clamp01(value: float | None, *, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    return max(0.0, min(1.0, float(value)))


def apply_execution_first_score(
    *,
    priority_score: float,
    signal_score: float,
    execution_score: float,
    candidate_class: str,
    execution_ok: bool = True,
    stale_quote: bool = False,
    missing_liquidity: bool = False,
    spread_uncertain: bool = False,
    data_confidence: float | None = None,
) -> ExecutionFirstScoreDecision:
    """Make execution quality dominate final ranking.

    EDGE-34 rule: a high signal score cannot hide weak tradability. This helper
    applies deterministic caps/penalties after signal/execution blending and
    before final class caps are applied.
    """
    reasons: list[str] = []
    score = _clamp01(priority_score)
    execution = _clamp01(execution_score)
    signal = _clamp01(signal_score)
    cap: float | None = None
    penalty = 0.0
    normalized_class = str(candidate_class or "").strip().upper()

    if normalized_class != "EXECUTABLE":
        return ExecutionFirstScoreDecision(
            adjusted_score=round(score, 6),
            cap_applied=None,
            penalty_applied=0.0,
            context={
                "execution_score": execution,
                "signal_score": signal,
                "candidate_class": normalized_class,
                "applied": False,
            },
        )

    hard_floor = float(getattr(cfg, "EXECUTION_FIRST_HARD_FLOOR", 0.35) or 0.35)
    soft_floor = float(getattr(cfg, "EXECUTION_FIRST_SOFT_FLOOR", 0.55) or 0.55)
    hard_cap = float(getattr(cfg, "EXECUTION_FIRST_HARD_CAP", 0.49) or 0.49)
    soft_cap = float(getattr(cfg, "EXECUTION_FIRST_SOFT_CAP", 0.65) or 0.65)
    weak_penalty = float(getattr(cfg, "EXECUTION_FIRST_WEAK_PENALTY", 0.08) or 0.08)
    unsafe_cap = float(getattr(cfg, "EXECUTION_FIRST_UNSAFE_CAP", 0.45) or 0.45)

    if not execution_ok:
        cap = unsafe_cap
        reasons.append("execution_not_ok_cap")
    elif execution < hard_floor:
        cap = hard_cap
        reasons.append("execution_hard_floor_cap")
    elif execution < soft_floor:
        cap = soft_cap
        penalty += weak_penalty
        reasons.append("execution_soft_floor_penalty")

    if stale_quote:
        penalty += float(getattr(cfg, "EXECUTION_FIRST_STALE_QUOTE_PENALTY", 0.10) or 0.10)
        reasons.append("stale_quote_execution_penalty")
    if missing_liquidity:
        penalty += float(getattr(cfg, "EXECUTION_FIRST_MISSING_LIQUIDITY_PENALTY", 0.08) or 0.08)
        reasons.append("missing_liquidity_execution_penalty")
    if spread_uncertain:
        penalty += float(getattr(cfg, "EXECUTION_FIRST_SPREAD_UNCERTAIN_PENALTY", 0.07) or 0.07)
        reasons.append("spread_uncertain_execution_penalty")

    confidence = _clamp01(data_confidence, default=1.0)
    confidence_floor = float(getattr(cfg, "EXECUTION_FIRST_DATA_CONFIDENCE_FLOOR", 0.45) or 0.45)
    if confidence < confidence_floor:
        penalty += float(getattr(cfg, "EXECUTION_FIRST_LOW_CONFIDENCE_PENALTY", 0.06) or 0.06)
        reasons.append("low_data_confidence_execution_penalty")

    if signal >= float(getattr(cfg, "EXECUTION_FIRST_HIGH_SIGNAL_THRESHOLD", 0.75) or 0.75) and execution < soft_floor:
        reasons.append("high_signal_overridden_by_execution")

    adjusted = _clamp01(score - penalty)
    if cap is not None:
        adjusted = min(adjusted, _clamp01(cap))

    return ExecutionFirstScoreDecision(
        adjusted_score=round(float(adjusted), 6),
        cap_applied=None if cap is None else round(float(cap), 6),
        penalty_applied=round(float(penalty), 6),
        reasons=tuple(reasons),
        context={
            "execution_score": execution,
            "signal_score": signal,
            "candidate_class": normalized_class,
            "execution_ok": bool(execution_ok),
            "stale_quote": bool(stale_quote),
            "missing_liquidity": bool(missing_liquidity),
            "spread_uncertain": bool(spread_uncertain),
            "data_confidence": confidence,
            "hard_floor": hard_floor,
            "soft_floor": soft_floor,
            "applied": bool(reasons),
        },
    )
