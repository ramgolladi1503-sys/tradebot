from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


REGIME_TO_STRATEGIES = {
    "TRENDING": ("breakout", "continuation"),
    "RANGING": ("mean_reversion",),
    "VOLATILE": ("vol_expansion",),
    "LOW_VOL": ("scalping", "mean_reversion"),
}


@dataclass(frozen=True)
class RoutedStrategyCandidate:
    symbol: str
    strategy: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


class RegimeStrategyRouter:
    def __init__(self, mapping: dict[str, tuple[str, ...]] | None = None):
        self.mapping = mapping or REGIME_TO_STRATEGIES

    def route(self, regime: str, candidates: Iterable[RoutedStrategyCandidate]) -> list[RoutedStrategyCandidate]:
        allowed = set(self.mapping.get(str(regime or "").upper(), ()))
        routed = [c for c in list(candidates or []) if c.strategy in allowed]
        routed.sort(key=lambda x: float(x.score), reverse=True)
        return routed

    def explain(self, regime: str, candidates: Iterable[RoutedStrategyCandidate]) -> dict[str, list[str]]:
        allowed = set(self.mapping.get(str(regime or "").upper(), ()))
        accepted: list[str] = []
        rejected: list[str] = []
        for c in list(candidates or []):
            if c.strategy in allowed:
                accepted.append(c.strategy)
            else:
                rejected.append(c.strategy)
        return {"accepted": accepted, "rejected": rejected}
