"""Movement strategy registry shell.

This module provides future strategy plumbing for the opportunity engine. It is
intentionally read-only: it does not call brokers, submit orders, change ranking,
change execution gates, touch depth subscriptions, or tune trades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from core.movement_contract import MovementContractError, StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult, classify_movement_regime

StrategyHandler = Callable[
    [StrategyContext, MovementRegimeResult],
    StrategyCandidate | Iterable[StrategyCandidate] | None,
]


@dataclass(frozen=True)
class MovementStrategyDefinition:
    """Registered movement-strategy metadata and callable."""

    strategy_id: str
    handler: StrategyHandler
    movement_types: tuple[str, ...] = ()
    min_regime_scores: dict[str, float] = field(default_factory=dict)
    enabled: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        strategy_id = str(self.strategy_id or "").strip()
        if not strategy_id:
            raise MovementContractError("strategy_definition_missing_id")
        if not callable(self.handler):
            raise MovementContractError(f"strategy_handler_not_callable:{strategy_id}")
        movement_types = tuple(
            str(item).strip().upper() for item in self.movement_types if str(item).strip()
        )
        min_scores: dict[str, float] = {}
        for key, value in dict(self.min_regime_scores or {}).items():
            label = str(key or "").strip().upper()
            if not label:
                continue
            try:
                score = float(value)
            except Exception as exc:
                raise MovementContractError(
                    f"strategy_min_regime_score_not_numeric:{strategy_id}:{label}"
                ) from exc
            if score < 0.0 or score > 1.0:
                raise MovementContractError(
                    f"strategy_min_regime_score_out_of_range:{strategy_id}:{label}:{score}"
                )
            min_scores[label] = score
        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "movement_types", movement_types)
        object.__setattr__(self, "min_regime_scores", min_scores)

    def should_activate(self, regime: MovementRegimeResult) -> bool:
        if not self.enabled:
            return False
        if not self.min_regime_scores:
            return True
        return all(
            float(regime.scores.get(label, 0.0)) >= threshold
            for label, threshold in self.min_regime_scores.items()
        )


@dataclass(frozen=True)
class MovementStrategyRunResult:
    """Result of running the registered strategy set."""

    candidates: tuple[StrategyCandidate, ...]
    activated_strategy_ids: tuple[str, ...]
    suppressed_strategy_ids: tuple[str, ...]
    error_counts: dict[str, int]
    errors: tuple[str, ...]
    regime: MovementRegimeResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": len(self.candidates),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "activated_strategy_ids": list(self.activated_strategy_ids),
            "suppressed_strategy_ids": list(self.suppressed_strategy_ids),
            "error_counts": dict(self.error_counts),
            "errors": list(self.errors),
            "regime": self.regime.to_dict(),
        }


class MovementStrategyRegistry:
    """Small, deterministic registry for future movement strategies."""

    def __init__(self, strategies: Iterable[MovementStrategyDefinition] | None = None) -> None:
        self._strategies: dict[str, MovementStrategyDefinition] = {}
        for strategy in strategies or ():
            self.register(strategy)

    def register(self, definition: MovementStrategyDefinition) -> None:
        if not isinstance(definition, MovementStrategyDefinition):
            raise MovementContractError("movement_strategy_definition_required")
        if definition.strategy_id in self._strategies:
            raise MovementContractError(f"duplicate_strategy_id:{definition.strategy_id}")
        self._strategies[definition.strategy_id] = definition

    def unregister(self, strategy_id: str) -> None:
        self._strategies.pop(str(strategy_id or "").strip(), None)

    def list_strategy_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._strategies))

    def get(self, strategy_id: str) -> MovementStrategyDefinition | None:
        return self._strategies.get(str(strategy_id or "").strip())

    def run(
        self,
        context: StrategyContext | dict[str, Any],
        *,
        regime: MovementRegimeResult | None = None,
        fail_fast: bool = False,
    ) -> MovementStrategyRunResult:
        ctx = context if isinstance(context, StrategyContext) else StrategyContext(**context)
        regime_result = regime or classify_movement_regime(ctx)
        candidates: list[StrategyCandidate] = []
        activated: list[str] = []
        suppressed: list[str] = []
        errors: list[str] = []
        error_counts: dict[str, int] = {}

        for strategy_id in sorted(self._strategies):
            definition = self._strategies[strategy_id]
            if not definition.should_activate(regime_result):
                suppressed.append(strategy_id)
                continue
            activated.append(strategy_id)
            try:
                emitted = definition.handler(ctx, regime_result)
                candidates.extend(_normalize_emitted_candidates(strategy_id, emitted))
            except Exception as exc:
                message = f"strategy_error:{strategy_id}:{type(exc).__name__}:{exc}"
                errors.append(message)
                error_counts[strategy_id] = error_counts.get(strategy_id, 0) + 1
                if fail_fast:
                    raise MovementContractError(message) from exc

        return MovementStrategyRunResult(
            candidates=tuple(candidates),
            activated_strategy_ids=tuple(activated),
            suppressed_strategy_ids=tuple(suppressed),
            error_counts=dict(error_counts),
            errors=tuple(errors),
            regime=regime_result,
        )


def _normalize_emitted_candidates(
    strategy_id: str,
    emitted: StrategyCandidate | Iterable[StrategyCandidate] | None,
) -> tuple[StrategyCandidate, ...]:
    if emitted is None:
        return ()
    if isinstance(emitted, StrategyCandidate):
        return (emitted,)
    if isinstance(emitted, (str, bytes, dict)):
        raise MovementContractError(f"strategy_returned_invalid_candidate_payload:{strategy_id}")
    try:
        items = tuple(emitted)
    except TypeError as exc:
        raise MovementContractError(f"strategy_returned_non_iterable:{strategy_id}") from exc
    for item in items:
        if not isinstance(item, StrategyCandidate):
            raise MovementContractError(
                f"strategy_returned_non_candidate:{strategy_id}:{type(item).__name__}"
            )
    return items


def create_empty_movement_strategy_registry() -> MovementStrategyRegistry:
    return MovementStrategyRegistry()


__all__ = [
    "MovementStrategyDefinition",
    "MovementStrategyRegistry",
    "MovementStrategyRunResult",
    "StrategyHandler",
    "create_empty_movement_strategy_registry",
]
