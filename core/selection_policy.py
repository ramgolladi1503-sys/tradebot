"""Selection policy report for ranked opportunity candidates.

This module is read-only. It converts canonical ranked-pipeline output plus the
single truth-path decision into a deterministic selection report. It does not
create paper intents, place orders, call brokers, mutate ranks, or touch the
dashboard.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

SELECTION_POLICY_SCHEMA_VERSION = 1

SELECTED_FOR_PAPER = "SELECTED_FOR_PAPER"
WAIT = "WAIT"
ADVISORY_ONLY = "ADVISORY_ONLY"
NO_TRADE = "NO_TRADE"
BLOCKED = "BLOCKED"

SCORE_ELIGIBLE = "SCORE_ELIGIBLE"
NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
SCORING_ADVISORY_ONLY = "ADVISORY_ONLY"
SUPPRESSED_BY_DOWNGRADE = "SUPPRESSED_BY_DOWNGRADE"
NO_TRADE_ONLY = "NO_TRADE_ONLY"

EXECUTABLE_BUCKET = "EXECUTABLE_CANDIDATE"
NEAR_EXECUTABLE_BUCKET = "NEAR_EXECUTABLE_CANDIDATE"
ADVISORY_BUCKET = "ADVISORY_CANDIDATE"
SUPPRESSED_BUCKET = "SUPPRESSED_CANDIDATE"
NO_TRADE_BUCKET = "NO_TRADE_CANDIDATE"


def _to_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    return None


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    return out if out == out else default


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


def _ranks_from_report(report: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    ranking = report.get("ranking")
    if isinstance(ranking, Mapping):
        ranks = ranking.get("ranks")
    else:
        ranks = report.get("ranks")
    if not isinstance(ranks, (list, tuple)):
        return ()
    return tuple(rank for rank in ranks if isinstance(rank, Mapping))


def _truth_path_allowed(truth_path_decision: Any) -> tuple[bool, tuple[str, ...]]:
    truth = _to_mapping(truth_path_decision)
    if truth is None:
        return False, ("TRUTH_PATH_DECISION_MISSING",)
    blockers = list(_list_of_strings(truth.get("blockers")))
    if not _bool(truth.get("allowed_for_paper_intent"), default=False):
        blockers.append("TRUTH_PATH_NOT_PAPER_INTENT_ELIGIBLE")
    if _bool(truth.get("advisory_only"), default=False):
        blockers.append("TRUTH_PATH_ADVISORY_ONLY")
    if _bool(truth.get("allowed_for_live_execution"), default=False):
        blockers.append("TRUTH_PATH_LIVE_EXECUTION_UNEXPECTED")
    return not blockers, _dedupe(blockers)


@dataclass(frozen=True)
class SelectionRecord:
    rank: int
    strategy_id: str
    symbol: str
    direction: str
    final_score: float
    bucket: str
    score_eligibility: str
    decision: str
    selected: bool
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class SelectionPolicyReport:
    schema_version: int
    read_only: bool
    is_order_action: bool
    append: bool
    state: str
    selected_count: int
    candidate_count: int
    max_selected: int
    min_final_score: float
    selected_strategy_ids: tuple[str, ...]
    selections: tuple[SelectionRecord, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["selected_strategy_ids"] = list(self.selected_strategy_ids)
        payload["selections"] = [record.to_dict() for record in self.selections]
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["reasons"] = list(self.reasons)
        payload["metadata"] = dict(self.metadata)
        return payload


def build_selection_policy_report(
    ranked_report: Any,
    *,
    truth_path_decision: Any = None,
    max_selected: int = 1,
    min_final_score: float = 0.0,
) -> SelectionPolicyReport:
    """Build a deterministic selection report from ranked candidates.

    A candidate can be selected only when the ranked pipeline report is safe,
    the truth-path decision is paper-intent eligible, and the candidate itself is
    rank-ordered, executable, score-eligible, blocker-free, and above the score
    floor.
    """

    report = _to_mapping(ranked_report)
    blockers: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []
    ranks: tuple[Mapping[str, Any], ...] = ()
    max_selected = max(0, int(max_selected))
    min_final_score = float(min_final_score)

    if report is None:
        blockers.append("RANKED_REPORT_MISSING")
        reasons.append("ranked_report_required_for_selection")
    else:
        if not _bool(report.get("read_only"), default=False):
            blockers.append("RANKED_REPORT_NOT_READ_ONLY")
        if _bool(report.get("is_order_action"), default=False):
            blockers.append("RANKED_REPORT_CONTAINS_ORDER_ACTION")
        if _bool(report.get("append"), default=False):
            blockers.append("RANKED_REPORT_APPEND_TRUE")
        ranks = _ranks_from_report(report)
        if not ranks:
            blockers.append("NO_RANKED_CANDIDATES")
            reasons.append("no_ranked_candidates_available")

    truth_allowed, truth_blockers = _truth_path_allowed(truth_path_decision)
    if not truth_allowed:
        blockers.extend(truth_blockers)
        reasons.append("truth_path_must_be_paper_intent_eligible")

    global_blockers = _dedupe(blockers)
    selected_so_far = 0
    records: list[SelectionRecord] = []

    for rank in sorted(ranks, key=lambda row: (_as_int(row.get("rank"), default=999999), str(row.get("strategy_id") or ""))):
        record = _classify_rank(
            rank,
            global_blockers=global_blockers,
            truth_allowed=truth_allowed,
            selected_so_far=selected_so_far,
            max_selected=max_selected,
            min_final_score=min_final_score,
        )
        if record.selected:
            selected_so_far += 1
        records.append(record)

    selected_strategy_ids = tuple(record.strategy_id for record in records if record.selected)
    report_state = _report_state(records, global_blockers)
    if selected_strategy_ids:
        reasons.append("top_ranked_execution_grade_candidate_selected_for_paper")
    elif records and report_state == WAIT:
        reasons.append("ranked_candidates_waiting_for_confirmation_or_capacity")
    elif records and report_state == ADVISORY_ONLY:
        reasons.append("ranked_candidates_are_advisory_only")
    elif records and report_state == NO_TRADE:
        reasons.append("ranked_pipeline_recommends_no_trade")

    return SelectionPolicyReport(
        schema_version=SELECTION_POLICY_SCHEMA_VERSION,
        read_only=True,
        is_order_action=False,
        append=False,
        state=report_state,
        selected_count=len(selected_strategy_ids),
        candidate_count=len(records),
        max_selected=max_selected,
        min_final_score=min_final_score,
        selected_strategy_ids=selected_strategy_ids,
        selections=tuple(records),
        blockers=global_blockers,
        warnings=_dedupe(warnings),
        reasons=tuple(sorted({reason for reason in reasons if reason})),
        metadata={
            "selector": "selection_policy_v1",
            "scope": "read_only_no_paper_intent_no_order_creation",
            "requires_truth_path": True,
            "requires_ranked_report": True,
        },
    )


def _classify_rank(
    rank: Mapping[str, Any],
    *,
    global_blockers: tuple[str, ...],
    truth_allowed: bool,
    selected_so_far: int,
    max_selected: int,
    min_final_score: float,
) -> SelectionRecord:
    candidate_blockers = list(_list_of_strings(rank.get("blockers")))
    warnings = list(_list_of_strings(rank.get("warnings"))) + list(_list_of_strings(rank.get("directional_warnings")))
    reasons: list[str] = []

    score = _as_float(rank.get("final_score"), default=0.0)
    bucket = str(rank.get("bucket") or "")
    eligibility = str(rank.get("score_eligibility") or "")
    executable_candidate = _bool(rank.get("executable_candidate"), default=False)
    direction = str(rank.get("direction") or "")

    if global_blockers:
        decision = BLOCKED
        candidate_blockers.extend(global_blockers)
        reasons.append("global_selection_precondition_failed")
    elif direction == "NO_TRADE" or eligibility == NO_TRADE_ONLY or bucket == NO_TRADE_BUCKET:
        decision = NO_TRADE
        reasons.append("ranked_candidate_is_no_trade")
    elif eligibility == SCORING_ADVISORY_ONLY or bucket == ADVISORY_BUCKET:
        decision = ADVISORY_ONLY
        reasons.append("ranked_candidate_is_advisory_only")
    elif eligibility == SUPPRESSED_BY_DOWNGRADE or bucket == SUPPRESSED_BUCKET or candidate_blockers:
        decision = BLOCKED
        reasons.append("ranked_candidate_has_blockers_or_is_suppressed")
    elif eligibility == NEEDS_CONFIRMATION or bucket == NEAR_EXECUTABLE_BUCKET:
        decision = WAIT
        reasons.append("ranked_candidate_needs_confirmation")
    elif not truth_allowed:
        decision = BLOCKED
        candidate_blockers.append("TRUTH_PATH_NOT_ALLOWED")
        reasons.append("truth_path_not_allowed")
    elif selected_so_far >= max_selected:
        decision = WAIT
        reasons.append("selection_capacity_already_used")
    elif score < min_final_score:
        decision = WAIT
        reasons.append("ranked_candidate_below_min_final_score")
    elif not executable_candidate or eligibility != SCORE_ELIGIBLE or bucket != EXECUTABLE_BUCKET:
        decision = WAIT
        reasons.append("ranked_candidate_not_execution_bucket")
    else:
        decision = SELECTED_FOR_PAPER
        reasons.append("ranked_candidate_selected_for_paper")

    return SelectionRecord(
        rank=_as_int(rank.get("rank"), default=0),
        strategy_id=str(rank.get("strategy_id") or ""),
        symbol=str(rank.get("symbol") or ""),
        direction=direction,
        final_score=round(score, 6),
        bucket=bucket,
        score_eligibility=eligibility,
        decision=decision,
        selected=decision == SELECTED_FOR_PAPER,
        reasons=tuple(sorted({reason for reason in reasons if reason})),
        blockers=_dedupe(candidate_blockers),
        warnings=_dedupe(warnings),
    )


def _report_state(records: list[SelectionRecord], global_blockers: tuple[str, ...]) -> str:
    if global_blockers:
        return BLOCKED
    if any(record.selected for record in records):
        return SELECTED_FOR_PAPER
    if not records:
        return BLOCKED
    decisions = {record.decision for record in records}
    if decisions == {NO_TRADE}:
        return NO_TRADE
    if decisions and decisions.issubset({ADVISORY_ONLY}):
        return ADVISORY_ONLY
    if decisions and decisions.issubset({BLOCKED}):
        return BLOCKED
    return WAIT


__all__ = [
    "ADVISORY_ONLY",
    "BLOCKED",
    "NO_TRADE",
    "SELECTED_FOR_PAPER",
    "SELECTION_POLICY_SCHEMA_VERSION",
    "WAIT",
    "SelectionPolicyReport",
    "SelectionRecord",
    "build_selection_policy_report",
]
