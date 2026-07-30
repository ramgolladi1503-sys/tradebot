"""Read-only candidate-pool orchestrator shell for the opportunity engine.

This module collects movement strategy candidates into one report and attaches
option-confirmation and no-trade assessment evidence. It is intentionally a
shell: it does not rank, execute, submit orders, call brokers, touch depth
subscriptions, mutate candidates, tune strategy thresholds, or change dashboard
behavior.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable

from core.market_event_graph_runtime_observer import observe_market_event_graph_runtime
from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult, classify_movement_regime
from core.no_trade_engine import NoTradeAssessment, assess_no_trade
from core.option_confirmation import (
    CandidateOptionConfirmation,
    OptionPressureAssessment,
    assess_option_pressure,
    confirm_candidate_option_pressure,
)

CandidateGenerator = Callable[[StrategyContext, MovementRegimeResult], Iterable[StrategyCandidate]]
REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True, kw_only=True)
class CandidatePoolReport:
    """Single read-only candidate-pool report for the future opportunity engine."""

    schema_version: int
    symbol: str
    read_only: bool = True
    is_order_action = False
    append: bool = False
    regime: MovementRegimeResult
    option_pressure: OptionPressureAssessment
    no_trade_assessment: NoTradeAssessment
    candidates: tuple[StrategyCandidate, ...]
    option_confirmations: tuple[CandidateOptionConfirmation, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    candidate_count: int
    movement_candidate_count: int
    no_trade_candidate_count: int
    validated_candidate_count: int
    blocked_candidate_count: int
    eligible_candidate_count_before_suppression: int
    report_executable_eligible_count: int
    generator_count: int
    failed_generator_count: int
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_order_action"] = False
        data["regime"] = self.regime.to_dict()
        data["option_pressure"] = self.option_pressure.to_dict()
        data["no_trade_assessment"] = self.no_trade_assessment.to_dict()
        data["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        data["option_confirmations"] = [confirmation.to_dict() for confirmation in self.option_confirmations]
        data["blockers"] = list(self.blockers)
        data["warnings"] = list(self.warnings)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def build_candidate_pool_report(
    ctx: StrategyContext | dict[str, Any],
    regime: MovementRegimeResult | None = None,
    *,
    candidate_generators: Iterable[CandidateGenerator] | None = None,
    option_pressure: OptionPressureAssessment | None = None,
    include_no_trade_candidate: bool = True,
) -> CandidatePoolReport:
    """Build a read-only report from strategy candidates."""

    if isinstance(ctx, dict):
        from core.movement_contract import context_from_dict

        ctx = context_from_dict(ctx)
    if not isinstance(ctx, StrategyContext):
        raise TypeError("candidate_pool_context_invalid")

    runtime_observation = observe_market_event_graph_runtime(
        ctx.metadata,
        context_ts=ctx.ts_epoch,
    )
    regime_result = regime or classify_movement_regime(ctx)
    option_assessment = option_pressure or assess_option_pressure(ctx)
    generators = tuple(candidate_generators) if candidate_generators is not None else get_default_candidate_generators()

    movement_candidates: list[StrategyCandidate] = []
    warnings: list[str] = []
    failed_generator_count = 0

    for generator in generators:
        generator_name = _generator_name(generator)
        try:
            generated = tuple(generator(ctx, regime_result) or ())
        except Exception as exc:
            failed_generator_count += 1
            warnings.append(f"strategy_generator_failed:{generator_name}:{exc.__class__.__name__}")
            continue
        for candidate in generated:
            if isinstance(candidate, StrategyCandidate):
                movement_candidates.append(candidate)
            else:
                warnings.append(f"strategy_generator_returned_non_candidate:{generator_name}")

    no_trade_assessment = assess_no_trade(
        ctx,
        regime_result,
        movement_candidates,
        option_pressure=option_assessment,
    )
    no_trade_candidates: tuple[StrategyCandidate, ...] = ()
    if include_no_trade_candidate and no_trade_assessment.no_trade:
        no_trade_candidates = _build_no_trade_candidates(ctx, regime_result, movement_candidates)

    candidates = tuple(movement_candidates) + tuple(no_trade_candidates)
    option_confirmations = tuple(
        confirm_candidate_option_pressure(candidate, ctx)
        for candidate in movement_candidates
        if candidate.direction in {"BUY_CALL", "BUY_PUT"}
    )
    blockers = tuple(
        sorted(
            set(
                tuple(option_assessment.blockers)
                + tuple(no_trade_assessment.blockers)
                + tuple(blocker for candidate in candidates for blocker in candidate.blockers)
                + tuple(blocker for confirmation in option_confirmations for blocker in confirmation.blockers)
            )
        )
    )
    all_warnings = tuple(
        sorted(
            set(
                tuple(warnings)
                + tuple(regime_result.warnings)
                + tuple(option_assessment.warnings)
                + tuple(no_trade_assessment.warnings)
                + tuple(warning for candidate in candidates for warning in candidate.warnings)
                + tuple(warning for confirmation in option_confirmations for warning in confirmation.warnings)
            )
        )
    )

    eligible_before_suppression = sum(1 for candidate in movement_candidates if candidate.executable_eligible)
    report_executable_count = 0 if no_trade_assessment.no_trade else eligible_before_suppression

    return CandidatePoolReport(
        schema_version=REPORT_SCHEMA_VERSION,
        symbol=ctx.symbol,
        read_only=True,
        append=False,
        regime=regime_result,
        option_pressure=option_assessment,
        no_trade_assessment=no_trade_assessment,
        candidates=candidates,
        option_confirmations=option_confirmations,
        blockers=blockers,
        warnings=all_warnings,
        candidate_count=len(candidates),
        movement_candidate_count=len(movement_candidates),
        no_trade_candidate_count=len(no_trade_candidates),
        validated_candidate_count=sum(1 for candidate in candidates if candidate.status == "VALIDATED_CANDIDATE"),
        blocked_candidate_count=sum(1 for candidate in candidates if candidate.status == "BLOCKED_CANDIDATE"),
        eligible_candidate_count_before_suppression=eligible_before_suppression,
        report_executable_eligible_count=report_executable_count,
        generator_count=len(generators),
        failed_generator_count=failed_generator_count,
        metadata={
            "report_type": "candidate_pool_orchestrator_shell",
            "scope": "read_only_no_execution_no_ranking",
            "primary_regime": regime_result.primary_regime,
            "dominant_option_direction": option_assessment.dominant_direction,
            "no_trade": no_trade_assessment.no_trade,
            "no_trade_primary_reason": no_trade_assessment.primary_reason,
            "default_strategy_mode": "MARKET_EVENT_GRAPH_SHADOW_ONLY",
            "market_event_graph_runtime_status": runtime_observation["status"],
            "market_event_graph_runtime_reason": runtime_observation["reason"],
            "market_event_graph_runtime_observation": runtime_observation,
        },
    )


def get_default_candidate_generators() -> tuple[CandidateGenerator, ...]:
    """Return only the frozen market-event graph for default shadow observation.

    Previously implemented strategies remain importable and available for explicit
    research/replay calls, but they are intentionally excluded from the default
    live candidate pool because they have not met the current structural-edge bar.
    """

    from strategies.movement import generate_market_event_graph_reversal_candidates  # noqa: PLC0415

    return (generate_market_event_graph_reversal_candidates,)


def _build_no_trade_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    movement_candidates: Iterable[StrategyCandidate],
) -> tuple[StrategyCandidate, ...]:
    from strategies.movement.no_trade_chop import generate_no_trade_candidates  # noqa: PLC0415

    return tuple(generate_no_trade_candidates(ctx, regime, movement_candidates) or ())


def _generator_name(generator: CandidateGenerator) -> str:
    return str(getattr(generator, "__name__", generator.__class__.__name__))


__all__ = [
    "CandidateGenerator",
    "CandidatePoolReport",
    "REPORT_SCHEMA_VERSION",
    "build_candidate_pool_report",
    "get_default_candidate_generators",
]
