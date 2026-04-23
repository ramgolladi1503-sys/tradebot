from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.paper_strategy_learning import PaperStrategyLearningEngine


REGIME_STRATEGY_PRIORS: dict[str, dict[str, float]] = {
    "TREND": {
        "breakout": 1.00,
        "trend_continuation": 1.10,
        "mean_reversion": 0.70,
        "volatility_expansion": 0.95,
    },
    "RANGE": {
        "breakout": 0.70,
        "trend_continuation": 0.75,
        "mean_reversion": 1.10,
        "volatility_expansion": 0.80,
    },
    "RANGE_VOLATILE": {
        "breakout": 0.85,
        "trend_continuation": 0.80,
        "mean_reversion": 0.90,
        "volatility_expansion": 1.05,
    },
    "EVENT": {
        "breakout": 0.80,
        "trend_continuation": 0.70,
        "mean_reversion": 0.60,
        "volatility_expansion": 1.15,
    },
    "PANIC": {
        "breakout": 0.65,
        "trend_continuation": 0.60,
        "mean_reversion": 0.55,
        "volatility_expansion": 1.10,
    },
    "NEUTRAL": {
        "breakout": 0.90,
        "trend_continuation": 0.90,
        "mean_reversion": 0.90,
        "volatility_expansion": 0.90,
    },
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "None"):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


@dataclass(frozen=True)
class RegimeAllocationDecision:
    strategy_family: str
    regime: str
    allowed: bool
    allocation_multiplier: float
    final_score: float
    reason: str
    details: dict[str, Any]


class RegimeAwareStrategyAllocator:
    def __init__(self, learning_engine: PaperStrategyLearningEngine | None = None) -> None:
        self.learning_engine = learning_engine or PaperStrategyLearningEngine()

    def decide(
        self,
        *,
        strategy_family: str,
        regime: str,
        candidate_score: float,
        execution_quality: float | None = None,
    ) -> RegimeAllocationDecision:
        family = str(strategy_family or "unknown").strip().lower() or "unknown"
        regime_key = str(regime or "NEUTRAL").strip().upper() or "NEUTRAL"
        learning = self.learning_engine.decision(family)
        regime_prior = float(REGIME_STRATEGY_PRIORS.get(regime_key, REGIME_STRATEGY_PRIORS["NEUTRAL"]).get(family, 0.85))
        exec_quality = _safe_float(execution_quality, 0.5)
        base_score = _safe_float(candidate_score, 0.0)

        if not learning.allowed:
            return RegimeAllocationDecision(
                strategy_family=family,
                regime=regime_key,
                allowed=False,
                allocation_multiplier=0.0,
                final_score=0.0,
                reason=f"learning_block:{learning.reason}",
                details={
                    "regime_prior": regime_prior,
                    "learning_state": learning.state,
                    "learning_multiplier": learning.size_multiplier,
                    "candidate_score": base_score,
                    "execution_quality": exec_quality,
                    "metrics": learning.metrics,
                },
            )

        allocation_multiplier = float(max(0.20, min(1.35, regime_prior * float(learning.size_multiplier))))
        final_score = max(0.0, min(1.0, (0.55 * base_score) + (0.30 * allocation_multiplier) + (0.15 * exec_quality)))

        allowed = True
        reason = "adaptive_allocation_ok"
        if final_score < 0.45:
            allocation_multiplier *= 0.5
            reason = "adaptive_allocation_downsize"
        if final_score < 0.30:
            allowed = False
            allocation_multiplier = 0.0
            reason = "adaptive_allocation_block"

        return RegimeAllocationDecision(
            strategy_family=family,
            regime=regime_key,
            allowed=allowed,
            allocation_multiplier=round(float(max(0.0, min(1.35, allocation_multiplier))), 4),
            final_score=round(float(final_score), 4),
            reason=reason,
            details={
                "regime_prior": round(regime_prior, 4),
                "learning_state": learning.state,
                "learning_multiplier": round(float(learning.size_multiplier), 4),
                "candidate_score": round(base_score, 4),
                "execution_quality": round(exec_quality, 4),
                "metrics": learning.metrics,
            },
        )
