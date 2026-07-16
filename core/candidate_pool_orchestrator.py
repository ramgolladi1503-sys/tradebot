"""Candidate-pool orchestrator shell for the opportunity engine.

This module collects movement strategy candidates into one report, attaches
option-confirmation and no-trade assessment evidence, and exposes the durable
owner acceptance boundary for the temporal ORB retest proposal before a
candidate is treated as authoritative. It does not rank, execute, submit
orders, call brokers, touch depth subscriptions, mutate candidates, tune
strategy thresholds, or change dashboard behavior.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult, classify_movement_regime
from core.opening_range_retest_emission_store import OpeningRangeRetestEmissionStore
from core.opening_range_retest_publication import (
    ACCEPTED_PUBLICATION_RESULTS,
    STRATEGY_ID as OPENING_RANGE_RETEST_STRATEGY_ID,
    accept_opening_range_retest_candidate,
    default_owner_db_path,
)
from core.no_trade_engine import NoTradeAssessment, assess_no_trade
from core.option_confirmation import (
    CandidateOptionConfirmation,
    OptionPressureAssessment,
    assess_option_pressure,
    enrich_candidate_with_option_confirmation,
)

CandidateGenerator = Callable[[StrategyContext, MovementRegimeResult], Iterable[StrategyCandidate]]

REPORT_SCHEMA_VERSION = 1
logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class CandidatePoolReport:
    """Single read-only candidate-pool report for the future opportunity engine."""

    schema_version: int
    symbol: str
    read_only: bool = True  # read_only=True
    is_order_action: bool = False  # is_order_action=False
    append: bool = False  # append=False
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
    opening_range_retest_owner_store: OpeningRangeRetestEmissionStore | None = None,
    include_no_trade_candidate: bool = True,
) -> CandidatePoolReport:
    """Build a read-only report from strategy candidates.

    The function is missing-data safe and generator-failure tolerant. A broken
    strategy contributes a warning, not a broker action and not a crash. The
    report can show executable eligibility, but it cannot make anything
    executable. If no-trade suppression is active, report-level executable count
    is forced to zero even when a raw candidate individually looks eligible.
    """

    if isinstance(ctx, dict):
        from core.movement_contract import context_from_dict
        ctx = context_from_dict(ctx)
    if not isinstance(ctx, StrategyContext):
        raise TypeError("candidate_pool_context_invalid")

    regime_result = regime or classify_movement_regime(ctx)
    option_assessment = option_pressure or assess_option_pressure(ctx)
    generators = tuple(candidate_generators) if candidate_generators is not None else get_default_candidate_generators()

    raw_movement_candidates: list[StrategyCandidate] = []
    warnings: list[str] = []
    owner_blockers: list[str] = []
    owner_results: list[dict[str, Any]] = []
    authoritative_setup_ids: set[str] = set()
    failed_generator_count = 0
    owner_store = opening_range_retest_owner_store

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
                if _phase2_boundary_violations(candidate):
                    warnings.append(f"candidate_ownership_blocked:{candidate.strategy_id}")
                    continue
                if candidate.strategy_id == OPENING_RANGE_RETEST_STRATEGY_ID:
                    if owner_store is None:
                        owner_store = OpeningRangeRetestEmissionStore(db_path=default_owner_db_path())
                    owner_summary, owner_blocker = _accept_opening_range_retest_candidate(
                        candidate,
                        owner_store=owner_store,
                    )
                    owner_results.append(owner_summary)
                    if owner_blocker is not None:
                        owner_blockers.append(owner_blocker)
                        warnings.append(owner_blocker)
                        continue
                    if not owner_summary["new_authoritative_output"]:
                        continue
                    setup_id = str(owner_summary["setup_id"])
                    if setup_id in authoritative_setup_ids:
                        continue
                    authoritative_setup_ids.add(setup_id)
                raw_movement_candidates.append(candidate)
            else:
                warnings.append(f"strategy_generator_returned_non_candidate:{generator_name}")

    movement_candidates: list[StrategyCandidate] = []
    option_confirmations: list[CandidateOptionConfirmation] = []
    for candidate in raw_movement_candidates:
        if candidate.direction in {"BUY_CALL", "BUY_PUT"}:
            enriched, confirmation = enrich_candidate_with_option_confirmation(
                candidate,
                ctx,
                assessment=option_assessment,
            )
            movement_candidates.append(enriched)
            option_confirmations.append(confirmation)
        else:
            movement_candidates.append(candidate)

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
    option_confirmations_tuple = tuple(option_confirmations)

    blockers = tuple(
        sorted(
            set(
                tuple(option_assessment.blockers)
                + tuple(no_trade_assessment.blockers)
                + tuple(owner_blockers)
                + tuple(blocker for candidate in candidates for blocker in candidate.blockers)
                + tuple(blocker for confirmation in option_confirmations_tuple for blocker in confirmation.blockers)
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
                + tuple(warning for confirmation in option_confirmations_tuple for warning in confirmation.warnings)
            )
        )
    )

    eligible_before_suppression = sum(1 for candidate in movement_candidates if candidate.executable_eligible)
    report_executable_count = 0 if no_trade_assessment.no_trade else eligible_before_suppression

    return CandidatePoolReport(
        schema_version=REPORT_SCHEMA_VERSION,
        symbol=ctx.symbol,
        read_only=True,
        is_order_action=False,
        append=False,
        regime=regime_result,
        option_pressure=option_assessment,
        no_trade_assessment=no_trade_assessment,
        candidates=candidates,
        option_confirmations=option_confirmations_tuple,
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
            "raw_candidate_count_before_phase2_enrichment": len(raw_movement_candidates),
            "opening_range_retest_owner_results": tuple(owner_results),
            "opening_range_retest_owner_candidate_input_count": sum(1 for result in owner_results),
            "opening_range_retest_owner_proposal_count": sum(1 for result in owner_results),
            "opening_range_retest_owner_authoritative_count": sum(1 for result in owner_results if result["new_authoritative_output"]),
            "opening_range_retest_owner_existing_record_count": sum(1 for result in owner_results if result["existing_authoritative_record"]),
            "opening_range_retest_owner_blocked_count": len(owner_blockers),
        },
    )


def get_default_candidate_generators() -> tuple[CandidateGenerator, ...]:
    """Return the read-only movement strategy generators.

    Imports stay lazy so importing this module cannot accidentally load strategy
    modules in unrelated legacy paths.
    """

    from strategies.movement import (  # noqa: PLC0415
        generate_compression_breakout_candidates,
        generate_event_volatility_expansion_candidates,
        generate_exhaustion_reversal_candidates,
        generate_failed_breakout_trap_candidates,
        generate_late_day_momentum_candidates,
        generate_mean_reversion_extension_candidates,
        generate_opening_drive_candidates,
        generate_opening_range_retest_candidates,
        generate_trend_pullback_candidates,
        generate_vwap_reclaim_rejection_candidates,
    )

    return (
        generate_opening_drive_candidates,
        generate_opening_range_retest_candidates,
        generate_compression_breakout_candidates,
        generate_trend_pullback_candidates,
        generate_vwap_reclaim_rejection_candidates,
        generate_failed_breakout_trap_candidates,
        generate_exhaustion_reversal_candidates,
        generate_mean_reversion_extension_candidates,
        generate_event_volatility_expansion_candidates,
        generate_late_day_momentum_candidates,
    )


def _build_no_trade_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    movement_candidates: Iterable[StrategyCandidate],
) -> tuple[StrategyCandidate, ...]:
    from strategies.movement.no_trade_chop import generate_no_trade_candidates  # noqa: PLC0415

    return tuple(generate_no_trade_candidates(ctx, regime, movement_candidates) or ())


def _accept_opening_range_retest_candidate(
    candidate: StrategyCandidate,
    *,
    owner_store: OpeningRangeRetestEmissionStore,
) -> tuple[dict[str, Any], str | None]:
    setup_identity = candidate.evidence.get("setup_identity") if isinstance(candidate.evidence, dict) else None
    setup_id = ""
    if isinstance(setup_identity, dict):
        setup_id = str(setup_identity.get("setup_id") or "")
    try:
        publication_result = accept_opening_range_retest_candidate(candidate, store=owner_store)
    except Exception as exc:
        blocker = f"opening_range_retest_owner_error:{setup_id or candidate.strategy_id}:{exc.__class__.__name__}"
        return (
            {
                "setup_id": setup_id or candidate.strategy_id,
                "strategy_id": candidate.strategy_id,
                "result": "ERROR",
                "detail": exc.__class__.__name__,
                "lineage_state": None,
                "publication_state": None,
                "publication_attempts": None,
                "outbox_id": None,
                "authoritative": False,
            },
            blocker,
        )

    summary = {
        "setup_id": publication_result.setup_id or setup_id or candidate.strategy_id,
        "strategy_id": candidate.strategy_id,
        "result": publication_result.result,
        "detail": publication_result.detail,
        "lineage_state": publication_result.lineage_state,
        "publication_state": publication_result.publication_state,
        "publication_attempts": publication_result.publication_attempts,
        "outbox_id": publication_result.outbox_id,
        "authoritative": publication_result.result == "ACCEPTED_FOR_PUBLICATION",
        "existing_authoritative_record": publication_result.result in ACCEPTED_PUBLICATION_RESULTS,
        "new_authoritative_output": publication_result.result == "ACCEPTED_FOR_PUBLICATION",
        "proposal_count": 1,
        "outbox_insert_count": 1 if publication_result.result == "ACCEPTED_FOR_PUBLICATION" else 0,
        "durable_record_count": 1 if publication_result.result in ACCEPTED_PUBLICATION_RESULTS else 0,
    }
    if publication_result.result not in ACCEPTED_PUBLICATION_RESULTS:
        blocker = f"opening_range_retest_owner_blocked:{publication_result.result}:{summary['setup_id']}"
        return summary, blocker
    return summary, None


def _generator_name(generator: CandidateGenerator) -> str:
    return str(getattr(generator, "__name__", generator.__class__.__name__))


def _phase2_boundary_violations(candidate: StrategyCandidate) -> tuple[str, ...]:
    violations = candidate.phase2_boundary_violations(producer_stage="STRATEGY")
    if not violations:
        return ()
    violating_fields = sorted(
        {
            violation.rsplit(":", 1)[-1]
            for violation in violations
            if ":" in violation
        }
    )
    try:
        logger.warning(
            "event=CANDIDATE_OWNERSHIP_BLOCKED runtime_strategy_id=%s violating_fields=%s reason=%s",
            candidate.strategy_id,
            ",".join(violating_fields) or "-",
            "strategy_candidate_claims_phase2_owned_truth",
        )
    except Exception:
        pass
    return violations


__all__ = [
    "CandidateGenerator",
    "CandidatePoolReport",
    "REPORT_SCHEMA_VERSION",
    "build_candidate_pool_report",
    "get_default_candidate_generators",
]
