"""Explicit separation of execution, UI and research ranking authorities."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class RankingAuthority(str, Enum):
    EXECUTION = "EXECUTION"
    UI_ONLY = "UI_ONLY"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    UNKNOWN_PENDING_PROOF = "UNKNOWN_PENDING_PROOF"


@dataclass(frozen=True)
class RankingEngineRecord:
    engine_id: str
    module: str
    callable_name: str
    authority: RankingAuthority
    evidence: str


DEFAULT_RANKING_ENGINES: tuple[RankingEngineRecord, ...] = (
    RankingEngineRecord(
        "legacy_opportunity_engine",
        "core.opportunity_engine",
        "annotate_ranked_opportunities",
        RankingAuthority.UNKNOWN_PENDING_PROOF,
        "Imported by TradeBuilder; exact execution-intent authority requires runtime call-path proof.",
    ),
    RankingEngineRecord(
        "canonical_ranked_opportunity_pipeline",
        "core.ranking_orchestrator",
        "build_ranked_opportunity_report",
        RankingAuthority.UI_ONLY,
        "Module docstring and result contract explicitly prohibit execution and broker calls.",
    ),
    RankingEngineRecord(
        "runtime_ranked_snapshot",
        "core.runtime_snapshot_producer",
        "produce_and_store_runtime_snapshots",
        RankingAuthority.UI_ONLY,
        "Projects ranked records into dashboard/evidence snapshots.",
    ),
)


def validate_ranking_authorities(
    engines: Iterable[RankingEngineRecord] = DEFAULT_RANKING_ENGINES,
    *,
    require_execution_authority: bool = False,
) -> tuple[str, ...]:
    rows = tuple(engines)
    errors: list[str] = []
    if len({row.engine_id for row in rows}) != len(rows):
        errors.append("duplicate_ranking_engine_id")
    execution = [row for row in rows if row.authority is RankingAuthority.EXECUTION]
    if len(execution) > 1:
        errors.append("multiple_execution_ranking_authorities")
    if require_execution_authority and len(execution) != 1:
        errors.append("execution_ranking_authority_not_proven")
    return tuple(errors)


def resolve_execution_ranking_authority(
    engines: Iterable[RankingEngineRecord] = DEFAULT_RANKING_ENGINES,
) -> RankingEngineRecord:
    rows = tuple(engines)
    errors = validate_ranking_authorities(rows, require_execution_authority=True)
    if errors:
        raise RuntimeError(";".join(errors))
    return next(row for row in rows if row.authority is RankingAuthority.EXECUTION)


def assert_ui_rankings_non_executable(
    engines: Iterable[RankingEngineRecord] = DEFAULT_RANKING_ENGINES,
) -> None:
    for row in engines:
        if row.authority is RankingAuthority.UI_ONLY and row.engine_id == "legacy_opportunity_engine":
            raise AssertionError("legacy_execution_candidate_misclassified_as_ui_only")


def ranking_authority_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "engines": [
            {
                "engine_id": row.engine_id,
                "module": row.module,
                "callable_name": row.callable_name,
                "authority": row.authority.value,
                "evidence": row.evidence,
            }
            for row in DEFAULT_RANKING_ENGINES
        ],
        "validation_errors": list(validate_ranking_authorities()),
        "execution_authority_proven": not bool(
            validate_ranking_authorities(require_execution_authority=True)
        ),
        "is_order_action": False,
    }


__all__ = [
    "DEFAULT_RANKING_ENGINES",
    "RankingAuthority",
    "RankingEngineRecord",
    "assert_ui_rankings_non_executable",
    "ranking_authority_payload",
    "resolve_execution_ranking_authority",
    "validate_ranking_authorities",
]
