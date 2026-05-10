from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from core.data_quality import apply_data_quality_contract


class CandidateLifecycle(str, Enum):
    RAW = "RAW"
    NORMALIZED = "NORMALIZED"
    DATA_INVALID = "DATA_INVALID"
    ADVISORY_ONLY = "ADVISORY_ONLY"
    NEAR_EXECUTABLE = "NEAR_EXECUTABLE"
    EXECUTABLE = "EXECUTABLE"
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class CandidatePoolResult:
    candidates: list[dict[str, Any]] = field(default_factory=list)
    top_executable_candidates: list[dict[str, Any]] = field(default_factory=list)
    near_executable_candidates: list[dict[str, Any]] = field(default_factory=list)
    advisory_candidates: list[dict[str, Any]] = field(default_factory=list)
    rejected_candidates: list[dict[str, Any]] = field(default_factory=list)
    debug_candidates: list[dict[str, Any]] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "total": len(self.candidates),
            "top_executable": len(self.top_executable_candidates),
            "near_executable": len(self.near_executable_candidates),
            "advisory": len(self.advisory_candidates),
            "rejected": len(self.rejected_candidates),
            "debug": len(self.debug_candidates),
        }


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _candidate_id(candidate: Mapping[str, Any], index: int) -> str:
    return str(
        candidate.get("candidate_id")
        or candidate.get("trade_id")
        or candidate.get("trade_key")
        or candidate.get("instrument_id")
        or f"candidate-{index}"
    ).strip()


def _candidate_symbol(candidate: Mapping[str, Any]) -> str:
    return str(candidate.get("symbol") or candidate.get("underlying") or "UNKNOWN").strip().upper() or "UNKNOWN"


def _score(candidate: Mapping[str, Any]) -> float:
    return float(
        _safe_float(candidate.get("final_score"))
        or _safe_float(candidate.get("rank_score"))
        or _safe_float(candidate.get("opportunity_score"))
        or _safe_float(candidate.get("confidence"))
        or 0.0
    )


def _has_reject_signal(candidate: Mapping[str, Any]) -> bool:
    status = str(candidate.get("candidate_status") or candidate.get("execution_status") or "").strip().lower()
    final_action = str(candidate.get("final_action") or candidate.get("permission") or "").strip().upper()
    if status in {"rejected", "blocked", "data_invalid"}:
        return True
    if final_action in {"BLOCK", "REJECT", "REJECTED"}:
        return True
    return bool(candidate.get("reject_reason") or candidate.get("final_blocker"))


def _derive_lifecycle(candidate: Mapping[str, Any]) -> CandidateLifecycle:
    if _has_reject_signal(candidate):
        return CandidateLifecycle.REJECTED

    data_grade = str(candidate.get("data_quality_grade") or "").strip().upper()
    execution_truth_allowed = bool(candidate.get("execution_truth_allowed", False))
    selected_for_execution = bool(candidate.get("selected_for_execution", False))
    execution_allowed = bool(candidate.get("execution_allowed", False))
    eligible_for_execution = bool(candidate.get("eligible_for_execution", False))
    execution_entry_status = str(candidate.get("execution_entry_status") or "").strip().lower()
    display_entry_status = str(candidate.get("display_entry_status") or "").strip().lower()

    if selected_for_execution and execution_truth_allowed:
        return CandidateLifecycle.SELECTED
    if execution_truth_allowed and execution_allowed and eligible_for_execution and execution_entry_status == "executable":
        return CandidateLifecycle.EXECUTABLE
    if data_grade in {"A", "B"} and not execution_truth_allowed:
        return CandidateLifecycle.NEAR_EXECUTABLE
    if data_grade in {"C", "D"} or display_entry_status in {"displayable", "non_executable"}:
        return CandidateLifecycle.ADVISORY_ONLY
    if data_grade == "F":
        return CandidateLifecycle.DATA_INVALID
    return CandidateLifecycle.NORMALIZED


def normalize_candidate(raw_candidate: Mapping[str, Any], *, index: int = 0) -> dict[str, Any]:
    """Normalize a raw strategy/review candidate into the canonical pool contract."""
    candidate = dict(raw_candidate or {})
    candidate.setdefault("candidate_id", _candidate_id(candidate, index))
    candidate.setdefault("symbol", _candidate_symbol(candidate))
    candidate.setdefault("source_strategy", candidate.get("strategy") or candidate.get("strategy_name") or "unknown")
    candidate.setdefault("candidate_pool_version", "v1")

    candidate = apply_data_quality_contract(candidate)
    lifecycle = _derive_lifecycle(candidate)
    candidate["candidate_lifecycle"] = lifecycle.value

    if lifecycle in {CandidateLifecycle.ADVISORY_ONLY, CandidateLifecycle.DATA_INVALID, CandidateLifecycle.REJECTED}:
        candidate["selected_for_execution"] = False
        candidate["eligible_for_execution"] = False
        candidate["execution_allowed"] = False
        candidate.setdefault("capital_assigned", 0.0)
    if lifecycle == CandidateLifecycle.EXECUTABLE:
        candidate["candidate_status"] = "executable"
    elif lifecycle == CandidateLifecycle.NEAR_EXECUTABLE:
        candidate["candidate_status"] = "near_executable"
    elif lifecycle == CandidateLifecycle.ADVISORY_ONLY:
        candidate["candidate_status"] = "advisory_only"
    elif lifecycle == CandidateLifecycle.REJECTED:
        candidate["candidate_status"] = "rejected"
    elif lifecycle == CandidateLifecycle.DATA_INVALID:
        candidate["candidate_status"] = "data_invalid"

    source_flags = dict(candidate.get("source_flags") or {})
    source_flags["candidate_lifecycle"] = lifecycle.value
    source_flags["candidate_pool_version"] = "v1"
    candidate["source_flags"] = source_flags
    return candidate


def build_candidate_pool(raw_candidates: Iterable[Mapping[str, Any]]) -> CandidatePoolResult:
    """Build canonical candidate streams from raw candidates.

    This is intentionally conservative and additive. It does not execute trades.
    It only classifies candidates so later ranking/risk/allocation code can consume
    clean streams instead of mixed raw rows.
    """
    normalized = [normalize_candidate(candidate, index=index) for index, candidate in enumerate(list(raw_candidates or []))]
    ordered = sorted(
        normalized,
        key=lambda row: (
            row.get("candidate_lifecycle") in {CandidateLifecycle.SELECTED.value, CandidateLifecycle.EXECUTABLE.value},
            _score(row),
            str(row.get("candidate_id") or ""),
        ),
        reverse=True,
    )

    executable = [row for row in ordered if row.get("candidate_lifecycle") in {CandidateLifecycle.SELECTED.value, CandidateLifecycle.EXECUTABLE.value}]
    near = [row for row in ordered if row.get("candidate_lifecycle") == CandidateLifecycle.NEAR_EXECUTABLE.value]
    advisory = [row for row in ordered if row.get("candidate_lifecycle") == CandidateLifecycle.ADVISORY_ONLY.value]
    rejected = [row for row in ordered if row.get("candidate_lifecycle") in {CandidateLifecycle.REJECTED.value, CandidateLifecycle.DATA_INVALID.value}]
    debug = [row for row in ordered if row.get("candidate_lifecycle") == CandidateLifecycle.NORMALIZED.value]

    for rank, row in enumerate(executable, start=1):
        row["candidate_pool_rank"] = rank

    return CandidatePoolResult(
        candidates=ordered,
        top_executable_candidates=executable,
        near_executable_candidates=near,
        advisory_candidates=advisory,
        rejected_candidates=rejected,
        debug_candidates=debug,
    )
