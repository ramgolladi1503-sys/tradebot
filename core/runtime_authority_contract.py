"""Read-only authority map and protected-boundary contract for TradeBot runtime."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Iterable


class AuthorityKind(str, Enum):
    EXECUTION = "EXECUTION"
    EXECUTION_GUARD = "EXECUTION_GUARD"
    CANDIDATE_CONSTRUCTION = "CANDIDATE_CONSTRUCTION"
    UI_ONLY = "UI_ONLY"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    OBSERVABILITY_ONLY = "OBSERVABILITY_ONLY"
    UNKNOWN_PENDING_PROOF = "UNKNOWN_PENDING_PROOF"


@dataclass(frozen=True)
class RuntimeAuthorityStage:
    order: int
    stage: str
    owner_module: str
    callable_name: str
    authority: AuthorityKind
    mutates_runtime_state: bool
    may_call_broker: bool
    notes: str = ""


FEED_PROTECTED_PREFIXES: tuple[str, ...] = (
    "core/market_data.py",
    "core/kite_depth_ws.py",
    "core/feed_runtime.py",
    "core/feed_health_truth.py",
    "core/feed_hold_gate.py",
    "core/recovery_state_machine.py",
    "core/kite_ws_subprocess.py",
    "config/",
)


_STAGES: tuple[RuntimeAuthorityStage, ...] = (
    RuntimeAuthorityStage(
        10,
        "startup",
        "main",
        "main",
        AuthorityKind.EXECUTION_GUARD,
        True,
        False,
        "Boot safety, auth, instance lock, database and readiness checks.",
    ),
    RuntimeAuthorityStage(
        20,
        "cycle_orchestration",
        "core.orchestrator",
        "Orchestrator",
        AuthorityKind.EXECUTION_GUARD,
        True,
        False,
        "Legacy production coordinator; concentration risk remains.",
    ),
    RuntimeAuthorityStage(
        30,
        "candidate_construction",
        "strategies.trade_builder",
        "TradeBuilder",
        AuthorityKind.CANDIDATE_CONSTRUCTION,
        True,
        False,
        "Legacy builder produces and mutates candidate state.",
    ),
    RuntimeAuthorityStage(
        40,
        "legacy_opportunity_engine",
        "core.opportunity_engine",
        "annotate_ranked_opportunities",
        AuthorityKind.UNKNOWN_PENDING_PROOF,
        True,
        False,
        "Imported by legacy builder, but execution authority must be proven by call-path evidence.",
    ),
    RuntimeAuthorityStage(
        50,
        "canonical_ranked_report",
        "core.ranking_orchestrator",
        "build_ranked_opportunity_report",
        AuthorityKind.UI_ONLY,
        False,
        False,
        "Module contract is explicitly read-only and non-executing.",
    ),
    RuntimeAuthorityStage(
        60,
        "runtime_snapshot_projection",
        "core.runtime_snapshot_producer",
        "produce_and_store_runtime_snapshots",
        AuthorityKind.UI_ONLY,
        True,
        False,
        "Writes dashboard/evidence snapshots; must never create broker intents.",
    ),
    RuntimeAuthorityStage(
        70,
        "risk_evaluation",
        "core.risk_engine",
        "RiskEngine",
        AuthorityKind.EXECUTION_GUARD,
        True,
        False,
        "Risk authority must remain downstream of candidate construction.",
    ),
    RuntimeAuthorityStage(
        80,
        "execution_routing",
        "core.execution_router",
        "ExecutionRouter",
        AuthorityKind.EXECUTION,
        True,
        True,
        "Only stage in this map permitted to route an order action.",
    ),
)


def build_runtime_authority_map() -> tuple[RuntimeAuthorityStage, ...]:
    return tuple(sorted(_STAGES, key=lambda stage: stage.order))


def validate_runtime_authority_map(
    stages: Iterable[RuntimeAuthorityStage] | None = None,
) -> tuple[str, ...]:
    rows = tuple(stages or build_runtime_authority_map())
    errors: list[str] = []
    if len({row.stage for row in rows}) != len(rows):
        errors.append("duplicate_stage_name")
    if [row.order for row in rows] != sorted(row.order for row in rows):
        errors.append("stage_order_not_monotonic")
    execution_stages = [row for row in rows if row.authority is AuthorityKind.EXECUTION]
    if len(execution_stages) != 1:
        errors.append("execution_authority_must_be_unique")
    for row in rows:
        if row.authority in {
            AuthorityKind.UI_ONLY,
            AuthorityKind.RESEARCH_ONLY,
            AuthorityKind.OBSERVABILITY_ONLY,
        } and row.may_call_broker:
            errors.append(f"non_execution_stage_may_call_broker:{row.stage}")
    return tuple(errors)


def protected_feed_path(path: str) -> bool:
    normalized = str(PurePosixPath(str(path).replace("\\", "/")))
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in FEED_PROTECTED_PREFIXES
    )


def assert_feed_boundary_untouched(changed_paths: Iterable[str]) -> None:
    touched = sorted({str(path) for path in changed_paths if protected_feed_path(str(path))})
    if touched:
        raise AssertionError(f"feed_boundary_modified:{','.join(touched)}")


def authority_map_payload() -> dict[str, object]:
    rows = build_runtime_authority_map()
    return {
        "schema_version": 1,
        "feed_boundary_frozen": True,
        "stages": [
            {
                "order": row.order,
                "stage": row.stage,
                "owner_module": row.owner_module,
                "callable_name": row.callable_name,
                "authority": row.authority.value,
                "mutates_runtime_state": row.mutates_runtime_state,
                "may_call_broker": row.may_call_broker,
                "notes": row.notes,
            }
            for row in rows
        ],
        "validation_errors": list(validate_runtime_authority_map(rows)),
        "is_order_action": False,
    }


__all__ = [
    "AuthorityKind",
    "FEED_PROTECTED_PREFIXES",
    "RuntimeAuthorityStage",
    "assert_feed_boundary_untouched",
    "authority_map_payload",
    "build_runtime_authority_map",
    "protected_feed_path",
    "validate_runtime_authority_map",
]
