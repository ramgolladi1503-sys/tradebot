"""Pure final executable-quality gate for EDGE-82.

This module is evidence-only. It evaluates already-built no-trade, ranking,
and executable-truth evidence and returns a deterministic report. It does not
call external execution adapters, mutate runtime state, write files, score
opportunities, rank candidates, or change dashboard behavior.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

FINAL_EXECUTABLE_QUALITY_SCHEMA_VERSION = 1
FINAL_EXECUTABLE_QUALITY_SOURCE = "final_executable_quality_gate_v1"

FINAL_EXECUTABLE_QUALITY_PASSED = "FINAL_EXECUTABLE_QUALITY_PASSED"
FINAL_EXECUTABLE_QUALITY_BLOCKED = "FINAL_EXECUTABLE_QUALITY_BLOCKED"

MISSING_GATE_EVIDENCE_REASON = "missing_final_quality_gate_evidence"
NO_TRADE_REQUIRED_REASON = "no_trade_required"
NO_EXECUTABLE_RANK_REASON = "no_executable_ranked_candidate"
RANKING_SAFETY_BLOCK_REASON = "ranking_safety_block"
EXECUTABLE_TRUTH_MISSING_REASON = "missing_executable_truth_evidence"
EXECUTABLE_TRUTH_BLOCKED_REASON = "executable_truth_blocked"
EXECUTABLE_TRUTH_UNKNOWN_REASON = "executable_truth_unknown"

SAFE_RANK_BUCKET = "EXECUTABLE_CANDIDATE"
SAFE_SCORE_ELIGIBILITY = "SCORE_ELIGIBLE"

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class FinalExecutableQualityBlocker:
    """One deterministic blocker produced by the final quality gate."""

    reason_code: str
    severity: int
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "severity": self.severity,
            "message": self.message,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class FinalExecutableQualityReport:
    """Read-only final executable-quality gate report."""

    schema_version: int
    read_only: bool
    append: bool
    source: str
    status: str
    executable_quality_passed: bool
    primary_reason: str
    selected_candidate: dict[str, Any] | None
    blockers: tuple[FinalExecutableQualityBlocker, ...]
    evidence_sources: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "status": self.status,
            "executable_quality_passed": self.executable_quality_passed,
            "primary_reason": self.primary_reason,
            "selected_candidate": dict(self.selected_candidate or {}),
            "blocker_count": len(self.blockers),
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "evidence_sources": list(self.evidence_sources),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_final_executable_quality_report(
    *,
    no_trade: Any | Mapping[str, Any] | None = None,
    ranking: Any | Mapping[str, Any] | None = None,
    executable_truths: Iterable[Any] | Any | None = None,
    now_epoch: float | None = None,
    source: str = FINAL_EXECUTABLE_QUALITY_SOURCE,
) -> FinalExecutableQualityReport:
    """Build final executable-quality evidence from already computed reports."""

    generated_epoch = float(time.time() if now_epoch is None else now_epoch)
    blockers: list[FinalExecutableQualityBlocker] = []
    warnings: list[str] = []
    evidence_sources: list[str] = []

    no_trade_payload = _payload(no_trade)
    ranking_payload = _payload(ranking)
    truth_payloads = tuple(item for item in (_payload(item) for item in _as_sequence(executable_truths)) if item)

    if no_trade_payload is not None:
        evidence_sources.append("no_trade_oracle")
        if bool(no_trade_payload.get("no_trade_required")) or no_trade_payload.get("status") == "NO_TRADE_REQUIRED":
            blockers.append(
                _blocker(
                    NO_TRADE_REQUIRED_REASON,
                    100,
                    "NoTradeOracle blocks final executable quality.",
                    {
                        "primary_reason": no_trade_payload.get("primary_reason"),
                        "blockers": list(_string_values(no_trade_payload.get("blockers"))),
                    },
                )
            )

    if ranking_payload is not None:
        evidence_sources.append("candidate_ranking")
    if truth_payloads:
        evidence_sources.append("executable_truth")

    selected_rank = _select_executable_rank(ranking_payload)
    if selected_rank is None:
        blockers.append(
            _blocker(
                NO_EXECUTABLE_RANK_REASON,
                90,
                "Ranking evidence does not contain an executable candidate.",
                _ranking_summary(ranking_payload),
            )
        )
    else:
        rank_blockers = _rank_blockers(selected_rank)
        if rank_blockers:
            blockers.append(
                _blocker(
                    RANKING_SAFETY_BLOCK_REASON,
                    85,
                    "Selected ranked candidate still carries blocker or safety evidence.",
                    {
                        "rank": selected_rank.get("rank"),
                        "strategy_id": selected_rank.get("strategy_id"),
                        "symbol": selected_rank.get("symbol"),
                        "rank_blockers": rank_blockers,
                    },
                )
            )

    if not truth_payloads:
        blockers.append(
            _blocker(
                EXECUTABLE_TRUTH_MISSING_REASON,
                95,
                "Executable-truth evidence is required before final quality can pass.",
                {},
            )
        )
    else:
        matching_truth = _matching_truth(selected_rank, truth_payloads)
        if matching_truth is None:
            blockers.append(
                _blocker(
                    EXECUTABLE_TRUTH_UNKNOWN_REASON,
                    88,
                    "No executable-truth evidence could be matched to the selected rank.",
                    {
                        "selected_rank": _candidate_identity(selected_rank),
                        "truth_count": len(truth_payloads),
                    },
                )
            )
        elif _execution_allowed(matching_truth) is not True:
            blockers.append(
                _blocker(
                    EXECUTABLE_TRUTH_BLOCKED_REASON,
                    92,
                    "Executable-truth evidence blocks the selected candidate.",
                    {
                        "selected_rank": _candidate_identity(selected_rank),
                        "reason_code": matching_truth.get("reason_code"),
                        "reasons": list(_string_values(matching_truth.get("reasons"))),
                    },
                )
            )

    if no_trade_payload is None or ranking_payload is None:
        missing = []
        if no_trade_payload is None:
            missing.append("no_trade_oracle")
        if ranking_payload is None:
            missing.append("candidate_ranking")
        blockers.append(
            _blocker(
                MISSING_GATE_EVIDENCE_REASON,
                99,
                "Required final quality gate evidence is missing.",
                {"missing_sources": missing},
            )
        )

    ordered = tuple(sorted(blockers, key=lambda item: (-item.severity, item.reason_code)))
    passed = not ordered
    status = FINAL_EXECUTABLE_QUALITY_PASSED if passed else FINAL_EXECUTABLE_QUALITY_BLOCKED
    primary_reason = "ok" if passed else ordered[0].reason_code
    return FinalExecutableQualityReport(
        schema_version=FINAL_EXECUTABLE_QUALITY_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        status=status,
        executable_quality_passed=passed,
        primary_reason=primary_reason,
        selected_candidate=_candidate_identity(selected_rank) if selected_rank is not None else None,
        blockers=ordered,
        evidence_sources=tuple(_dedupe(evidence_sources)),
        warnings=tuple(_dedupe(warnings)),
        metadata={
            "gate": FINAL_EXECUTABLE_QUALITY_SOURCE,
            "scope": "read_only_final_quality_evidence_only",
            "fail_closed_on_missing_evidence": True,
            "does_not_call_external_execution": True,
            "does_not_append_runtime_files": True,
            "does_not_rank_candidates": True,
            "does_not_score_edge": True,
        },
        generated_epoch=generated_epoch,
    )


def _payload(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    for method_name in ("to_payload", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            out = method()
            return dict(out) if isinstance(out, Mapping) else None
    if hasattr(value, "execution_allowed"):
        return {
            "execution_allowed": bool(getattr(value, "execution_allowed")),
            "reason_code": getattr(value, "reason_code", None),
            "reasons": list(getattr(value, "reasons", ())),
            "context": dict(getattr(value, "context", {}) or {}),
        }
    return None


def _as_sequence(value: Iterable[Any] | Any | None) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)):
        return (value,)
    if _payload(value) is not None:
        return (value,)
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _select_executable_rank(ranking_payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if ranking_payload is None:
        return None
    ranks = ranking_payload.get("ranks")
    if not isinstance(ranks, Iterable) or isinstance(ranks, (str, bytes, Mapping)):
        return None
    candidates = [dict(rank) for rank in ranks if isinstance(rank, Mapping)]
    executable = [rank for rank in candidates if _rank_is_executable(rank)]
    if not executable:
        return None
    return sorted(executable, key=lambda rank: _safe_int(rank.get("rank"), default=999999))[0]


def _rank_is_executable(rank: Mapping[str, Any]) -> bool:
    return (
        bool(rank.get("executable_candidate"))
        and str(rank.get("bucket") or "") == SAFE_RANK_BUCKET
        and str(rank.get("score_eligibility") or "") == SAFE_SCORE_ELIGIBILITY
    )


def _rank_blockers(rank: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("blockers", "safety_flags", "downgrade_reasons"):
        values.extend(_string_values(rank.get(key)))
    return list(_dedupe(values))


def _ranking_summary(ranking_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if ranking_payload is None:
        return {"ranking_present": False}
    return {
        "ranking_present": True,
        "rank_count": ranking_payload.get("rank_count"),
        "executable_count": ranking_payload.get("executable_count"),
        "near_executable_count": ranking_payload.get("near_executable_count"),
        "blockers": list(_string_values(ranking_payload.get("blockers"))),
        "safety_flags": list(_string_values(ranking_payload.get("safety_flags"))),
    }


def _matching_truth(
    selected_rank: Mapping[str, Any] | None,
    truth_payloads: tuple[Mapping[str, Any], ...],
) -> Mapping[str, Any] | None:
    if selected_rank is None:
        return None
    if len(truth_payloads) == 1:
        return truth_payloads[0]
    selected_identity = _candidate_identity(selected_rank)
    for payload in truth_payloads:
        if _identity_matches(selected_identity, payload):
            return payload
        context = payload.get("context") if isinstance(payload.get("context"), Mapping) else {}
        if _identity_matches(selected_identity, context):
            return payload
    return None


def _identity_matches(selected_identity: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    selected_candidate_id = str(selected_identity.get("candidate_id") or "").strip()
    payload_candidate_id = str(payload.get("candidate_id") or payload.get("trade_key") or "").strip()
    if selected_candidate_id and payload_candidate_id:
        return selected_candidate_id == payload_candidate_id
    strategy = str(selected_identity.get("strategy_id") or "").strip()
    symbol = str(selected_identity.get("symbol") or "").strip()
    direction = str(selected_identity.get("direction") or "").strip()
    movement = str(selected_identity.get("movement_type") or "").strip()
    return bool(
        strategy
        and symbol
        and direction
        and strategy == str(payload.get("strategy_id") or "").strip()
        and symbol == str(payload.get("symbol") or "").strip()
        and direction == str(payload.get("direction") or "").strip()
        and (not movement or movement == str(payload.get("movement_type") or "").strip())
    )


def _candidate_identity(rank: Mapping[str, Any] | None) -> dict[str, Any]:
    if rank is None:
        return {}
    return {
        "rank": rank.get("rank"),
        "candidate_id": rank.get("candidate_id") or rank.get("trade_key"),
        "strategy_id": rank.get("strategy_id"),
        "symbol": rank.get("symbol"),
        "direction": rank.get("direction"),
        "movement_type": rank.get("movement_type"),
        "final_score": rank.get("final_score"),
        "bucket": rank.get("bucket"),
        "score_eligibility": rank.get("score_eligibility"),
    }


def _execution_allowed(payload: Mapping[str, Any]) -> bool | None:
    value = payload.get("execution_allowed")
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return None
    return str(value).strip().lower() in {"1", "true", "yes", "ok", "allowed"}


def _string_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Mapping):
        return ()
    try:
        items = tuple(value)
    except TypeError:
        return (str(value),) if str(value).strip() else ()
    return tuple(str(item).strip() for item in items if str(item or "").strip())


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dedupe(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value or "").strip()}))


def _blocker(reason_code: str, severity: int, message: str, evidence: Mapping[str, Any]) -> FinalExecutableQualityBlocker:
    return FinalExecutableQualityBlocker(
        reason_code=reason_code,
        severity=int(severity),
        message=message,
        evidence=dict(evidence),
    )


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "EXECUTABLE_TRUTH_BLOCKED_REASON",
    "EXECUTABLE_TRUTH_MISSING_REASON",
    "EXECUTABLE_TRUTH_UNKNOWN_REASON",
    "FINAL_EXECUTABLE_QUALITY_BLOCKED",
    "FINAL_EXECUTABLE_QUALITY_PASSED",
    "FINAL_EXECUTABLE_QUALITY_SCHEMA_VERSION",
    "FINAL_EXECUTABLE_QUALITY_SOURCE",
    "MISSING_GATE_EVIDENCE_REASON",
    "NO_EXECUTABLE_RANK_REASON",
    "NO_TRADE_REQUIRED_REASON",
    "RANKING_SAFETY_BLOCK_REASON",
    "FinalExecutableQualityBlocker",
    "FinalExecutableQualityReport",
    "build_final_executable_quality_report",
]
