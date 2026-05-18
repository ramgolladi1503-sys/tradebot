"""Single opportunity truth-path policy.

This module does not run strategies, rank candidates, place orders, call brokers,
or create paper orders. It classifies whether an opportunity decision came from
the canonical ranked pipeline and whether it is allowed to advance to later
paper-intent orchestration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from core.ranking_orchestrator import PIPELINE_STAGE_ORDER

OPPORTUNITY_TRUTH_PATH_SCHEMA_VERSION = 1
CANONICAL_ORCHESTRATOR = "ranked_opportunity_pipeline_v1"
LEGACY_SOURCE_PREFIXES: tuple[str, ...] = (
    "legacy",
    "direct",
    "dashboard",
    "manual",
    "strategy_module",
    "final_decision",
)


def _to_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    return None


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _list_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


def _metadata(report: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = report.get("metadata")
    return metadata if isinstance(metadata, Mapping) else {}


def _is_legacy_source(source_name: str | None, report: Mapping[str, Any] | None) -> bool:
    source = _norm_lower(source_name)
    if any(source.startswith(prefix) for prefix in LEGACY_SOURCE_PREFIXES):
        return True
    if report is None:
        return False
    metadata = _metadata(report)
    origin = _norm_lower(metadata.get("source") or metadata.get("origin") or metadata.get("orchestrator"))
    return any(origin.startswith(prefix) for prefix in LEGACY_SOURCE_PREFIXES)


def _pipeline_stage_order_matches(report: Mapping[str, Any]) -> bool:
    return tuple(_list_of_strings(report.get("pipeline_stage_order"))) == tuple(PIPELINE_STAGE_ORDER)


def _execution_grade_allowed(execution_grade_decision: Any) -> tuple[bool, tuple[str, ...]]:
    payload = _to_mapping(execution_grade_decision)
    if payload is None:
        return False, ("EXECUTION_GRADE_DECISION_MISSING",)
    blockers = list(_list_of_strings(payload.get("blockers")))
    if not _bool(payload.get("execution_grade"), default=False):
        blockers.append("EXECUTION_GRADE_FALSE")
    if not _bool(payload.get("allowed_for_paper_execution"), default=False):
        blockers.append("PAPER_EXECUTION_NOT_ALLOWED")
    if _bool(payload.get("advisory_only"), default=False):
        blockers.append("EXECUTION_FIREWALL_ADVISORY_ONLY")
    return not blockers, _dedupe(blockers)


@dataclass(frozen=True)
class OpportunityTruthPathDecision:
    schema_version: int
    state: str
    canonical: bool
    source_name: str
    truth_path: str
    allowed_for_paper_intent: bool
    allowed_for_live_execution: bool
    advisory_only: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    required_stage_order: tuple[str, ...]
    observed_stage_order: tuple[str, ...]
    top_rank_strategy_id: str | None
    ranked_candidate_count: int
    is_order_action: bool = False
    append: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["reasons"] = list(self.reasons)
        payload["required_stage_order"] = list(self.required_stage_order)
        payload["observed_stage_order"] = list(self.observed_stage_order)
        return payload


def assess_opportunity_truth_path(
    ranked_report: Any = None,
    *,
    source_name: str = CANONICAL_ORCHESTRATOR,
    execution_grade_decision: Any = None,
) -> OpportunityTruthPathDecision:
    """Assess whether an opportunity can advance beyond advisory analysis.

    The only canonical upstream source is the ranked opportunity pipeline. Later
    paper-decision PRs can depend on this policy instead of re-checking ad hoc
    legacy/direct candidate paths.
    """

    report = _to_mapping(ranked_report)
    blockers: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []
    observed_stage_order: tuple[str, ...] = ()
    top_rank_strategy_id: str | None = None
    ranked_candidate_count = 0

    legacy_source = _is_legacy_source(source_name, report)
    if legacy_source:
        blockers.append("LEGACY_OPPORTUNITY_SOURCE")
        warnings.append("legacy_source_contained_as_advisory_only")
        reasons.append("legacy_or_direct_opportunity_path_cannot_promote_to_paper_intent")

    if report is None:
        blockers.append("RANKED_PIPELINE_REPORT_MISSING")
        reasons.append("ranked_pipeline_report_required")
    else:
        metadata = _metadata(report)
        orchestrator = _norm(metadata.get("orchestrator"))
        observed_stage_order = tuple(_list_of_strings(report.get("pipeline_stage_order")))
        top_rank_strategy_id = report.get("top_rank_strategy_id")
        try:
            ranked_candidate_count = int(report.get("ranked_candidate_count") or 0)
        except Exception:
            ranked_candidate_count = 0

        if orchestrator != CANONICAL_ORCHESTRATOR:
            blockers.append("NON_CANONICAL_OPPORTUNITY_SOURCE")
            reasons.append("opportunity_source_must_be_ranked_pipeline")
        if not _bool(report.get("read_only"), default=False):
            blockers.append("RANKED_PIPELINE_NOT_READ_ONLY")
        if _bool(report.get("is_order_action"), default=False):
            blockers.append("RANKED_PIPELINE_CONTAINS_ORDER_ACTION")
        if _bool(report.get("append"), default=False):
            blockers.append("RANKED_PIPELINE_APPEND_TRUE")
        if not _pipeline_stage_order_matches(report):
            blockers.append("RANKED_PIPELINE_STAGE_ORDER_INVALID")
        if ranked_candidate_count <= 0:
            blockers.append("NO_RANKED_CANDIDATES")
        if top_rank_strategy_id in (None, ""):
            blockers.append("TOP_RANK_MISSING")

    execution_allowed, execution_blockers = _execution_grade_allowed(execution_grade_decision)
    if not execution_allowed:
        blockers.extend(execution_blockers)
        reasons.append("execution_grade_firewall_must_pass_before_paper_intent")

    normalized_blockers = _dedupe(blockers)
    normalized_warnings = _dedupe(warnings)
    canonical = bool(report is not None and not legacy_source and "NON_CANONICAL_OPPORTUNITY_SOURCE" not in normalized_blockers)
    allowed = bool(canonical and execution_allowed and not normalized_blockers)

    if allowed:
        state = "PAPER_INTENT_ELIGIBLE"
        truth_path = "ranked_pipeline_to_execution_firewall"
        advisory_only = False
        reasons.append("canonical_ranked_pipeline_and_execution_firewall_passed")
    elif legacy_source:
        state = "ADVISORY_ONLY"
        truth_path = "legacy_advisory_contained"
        advisory_only = True
    else:
        state = "BLOCKED"
        truth_path = "blocked_before_paper_intent"
        advisory_only = False

    return OpportunityTruthPathDecision(
        schema_version=OPPORTUNITY_TRUTH_PATH_SCHEMA_VERSION,
        state=state,
        canonical=canonical,
        source_name=str(source_name or ""),
        truth_path=truth_path,
        allowed_for_paper_intent=allowed,
        allowed_for_live_execution=False,
        advisory_only=advisory_only,
        blockers=normalized_blockers,
        warnings=normalized_warnings,
        reasons=tuple(sorted({reason for reason in reasons if reason})),
        required_stage_order=tuple(PIPELINE_STAGE_ORDER),
        observed_stage_order=observed_stage_order,
        top_rank_strategy_id=str(top_rank_strategy_id) if top_rank_strategy_id not in (None, "") else None,
        ranked_candidate_count=ranked_candidate_count,
    )


__all__ = [
    "CANONICAL_ORCHESTRATOR",
    "OPPORTUNITY_TRUTH_PATH_SCHEMA_VERSION",
    "OpportunityTruthPathDecision",
    "assess_opportunity_truth_path",
]
