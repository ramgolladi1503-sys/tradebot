"""Read-only truth contract for top opportunity executable/advisory lists.

The dashboard and runtime snapshots must not treat a row as a top executable
opportunity just because legacy fields say `is_executable=true` or
`execution_status=executable`. The executable list requires canonical execution
entry truth; display-only rows remain advisory/debug evidence.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

TOP_OPPORTUNITY_EXECUTABLE_TRUTH_SCHEMA_VERSION = 1
CANONICAL_RANKED_SNAPSHOT_SOURCE = "CANONICAL_RANKED_SNAPSHOT"
LIVE_PHASE2_SOURCE = "LIVE_PHASE2"
CANONICAL_CANDIDATE_POOL_AUTHORITY = "CANONICAL_CANDIDATE_POOL"
CANONICAL_RANKING_AUTHORITY = "CANONICAL_RANKING"
LIVE_PHASE2_TRUTH_AUTHORITY = "LIVE_PHASE2_TRUTH"
LIVE_PHASE2_RANKING_AUTHORITY = "LIVE_PHASE2_RANKING"
_EXECUTABLE_ENTRY_SOURCES = {"ask", "bid", "last", "retained_prior_ask", "retained_prior_bid"}
_FALLBACK_SOURCES = {"rest_fallback", "recovered_fallback", "fallback_estimated"}


def annotate_top_opportunity_authority(
    row: Mapping[str, Any] | None,
    *,
    pipeline_source: str,
    status_authority: str,
    rank_authority: str,
    execution_eligibility: bool | None = None,
    execution_eligibility_authority: str | None = None,
    phase2_status: str | None = None,
    phase2_score: Any | None = None,
    raw_strategy_score: Any | None = None,
    fallback_state: str | None = None,
    blocked_reason: str | None = None,
    advisory_reason: str | None = None,
) -> dict[str, Any]:
    out = dict(row or {})
    out["pipeline_source"] = str(pipeline_source or "UNKNOWN")
    out["status_authority"] = str(status_authority or "UNKNOWN")
    out["rank_authority"] = str(rank_authority or "UNKNOWN")
    if execution_eligibility is not None:
        out["execution_eligibility"] = bool(execution_eligibility)
    if execution_eligibility_authority is not None:
        out["execution_eligibility_authority"] = str(execution_eligibility_authority or "UNKNOWN")
    if phase2_status is not None:
        out["phase2_status"] = str(phase2_status or "UNKNOWN")
    if phase2_score is not None:
        out["phase2_score"] = phase2_score
    if raw_strategy_score is not None:
        out["raw_strategy_score"] = raw_strategy_score
    out["fallback_state"] = fallback_state if fallback_state is not None else _derive_fallback_state(out)
    if blocked_reason is not None:
        out["blocked_reason"] = blocked_reason
    if advisory_reason is not None:
        out["advisory_reason"] = advisory_reason
    return out


def _derive_fallback_state(row: Mapping[str, Any] | None) -> str:
    payload = dict(row or {})
    fallback_state = str(payload.get("fallback_state") or "").strip().lower()
    if fallback_state:
        return fallback_state
    if bool(payload.get("recovered_fallback")) or bool(payload.get("fallback_used")):
        return "recovered_fallback"
    source_flags = payload.get("source_flags")
    if isinstance(source_flags, Mapping):
        if bool(source_flags.get("recovered_fallback")) or bool(source_flags.get("fallback_used")):
            return "recovered_fallback"
        fallback_class = str(source_flags.get("fallback_class") or "").strip().lower()
        if fallback_class and fallback_class != "none":
            return fallback_class
    row_kind = str(payload.get("row_kind") or "").strip().lower()
    if row_kind in {"fallback", "recovered_fallback"}:
        return row_kind
    for source_field in ("execution_entry_source", "display_entry_source", "quote_source", "entry_source"):
        source_value = str(payload.get(source_field) or "").strip().lower()
        if source_value in _FALLBACK_SOURCES:
            return "recovered_fallback" if source_value == "recovered_fallback" else "fallback"
    return "none"


@dataclass(frozen=True)
class TopOpportunityTruthRecord:
    trade_id: str
    source_list: str
    destination_list: str
    executable_truth: bool
    reason: str
    execution_entry: float | None
    execution_entry_source: str
    execution_entry_status: str
    display_entry: float | None
    display_entry_source: str
    quote_source: str
    legacy_claims_executable: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TopOpportunityTruthReport:
    is_order_action = False
    broker_api_called = False
    live_order_action = False
    broker_order_action = False
    append = False

    schema_version: int
    read_only: bool
    source_executable_count: int
    source_advisory_count: int
    top_executable_count: int
    top_advisory_count: int
    demoted_count: int
    rejected_count: int
    records: tuple[TopOpportunityTruthRecord, ...]
    rejection_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_action": False,
            "broker_order_action": False,
            "append": self.append,
            "source_executable_count": self.source_executable_count,
            "source_advisory_count": self.source_advisory_count,
            "top_executable_count": self.top_executable_count,
            "top_advisory_count": self.top_advisory_count,
            "demoted_count": self.demoted_count,
            "rejected_count": self.rejected_count,
            "records": [record.to_dict() for record in self.records],
            "rejection_reasons": list(self.rejection_reasons),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def normalize_top_opportunity_payload(
    payload: Mapping[str, Any] | None,
    *,
    executable_limit: int | None = None,
    advisory_limit: int | None = None,
) -> tuple[dict[str, Any], TopOpportunityTruthReport]:
    """Normalize top opportunity lists without mutating rows or taking actions."""
    source = dict(payload or {})
    source_executable = _coerce_rows(source.get("top_executable_opportunities"))
    source_advisory = _coerce_rows(source.get("top_advisory_opportunities"))
    executable_out: list[dict[str, Any]] = []
    advisory_out: list[dict[str, Any]] = []
    records: list[TopOpportunityTruthRecord] = []

    for row in source_executable:
        decision = classify_top_opportunity_row(row, source_list="top_executable")
        records.append(decision)
        if decision.executable_truth:
            executable_out.append(dict(row))
        else:
            advisory_out.append(_with_truth_demoted(row, decision.reason))

    for row in source_advisory:
        decision = classify_top_opportunity_row(row, source_list="top_advisory")
        records.append(decision)
        if decision.executable_truth:
            advisory_out.append(_with_truth_demoted(row, "source_list_advisory_not_promoted"))
        else:
            advisory_out.append(dict(row))

    if executable_limit is not None:
        executable_out = executable_out[: max(0, int(executable_limit))]
    if advisory_limit is not None:
        advisory_out = advisory_out[: max(0, int(advisory_limit))]

    normalized = dict(source)
    normalized["top_executable_opportunities"] = executable_out
    normalized["top_advisory_opportunities"] = advisory_out
    normalized["top_executable_count"] = len(executable_out)
    normalized["top_advisory_count"] = len(advisory_out)
    normalized["source_candidate_count"] = len(source_executable) + len(source_advisory)
    normalized["top_opportunity_truth"] = {
        "schema_version": TOP_OPPORTUNITY_EXECUTABLE_TRUTH_SCHEMA_VERSION,
        "demoted_count": sum(1 for record in records if record.destination_list == "top_advisory" and record.source_list == "top_executable"),
        "rejected_count": 0,
    }

    report = TopOpportunityTruthReport(
        schema_version=TOP_OPPORTUNITY_EXECUTABLE_TRUTH_SCHEMA_VERSION,
        read_only=True,
        source_executable_count=len(source_executable),
        source_advisory_count=len(source_advisory),
        top_executable_count=len(executable_out),
        top_advisory_count=len(advisory_out),
        demoted_count=sum(1 for record in records if record.destination_list == "top_advisory" and record.source_list == "top_executable"),
        rejected_count=0,
        records=tuple(records),
        rejection_reasons=tuple(sorted({record.reason for record in records if not record.executable_truth})),
        warnings=tuple(sorted(_warnings(records))),
        metadata={
            "contract": "top_opportunity_executable_truth_v1",
            "scope": "read_only_no_runtime_no_broker_no_order",
            "executable_limit": executable_limit,
            "advisory_limit": advisory_limit,
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_action": False,
            "broker_order_action": False,
        },
    )
    return normalized, report


def classify_top_opportunity_row(
    row: Mapping[str, Any],
    *,
    source_list: str,
) -> TopOpportunityTruthRecord:
    execution_entry = _positive_float(row.get("execution_entry"))
    execution_source = _lower(row.get("execution_entry_source")) or "none"
    execution_status = _lower(row.get("execution_entry_status")) or "missing"
    display_entry = _positive_float(row.get("display_entry") if row.get("display_entry") is not None else row.get("entry"))
    display_source = _lower(row.get("display_entry_source") or row.get("entry_source")) or "none"
    quote_source = _lower(row.get("quote_source") or row.get("option_ltp_source")) or "unknown"
    legacy_claims_executable = _legacy_claims_executable(row)

    reason = _truth_reason(
        execution_entry=execution_entry,
        execution_source=execution_source,
        execution_status=execution_status,
        display_entry=display_entry,
        display_source=display_source,
        quote_source=quote_source,
        legacy_claims_executable=legacy_claims_executable,
    )
    executable_truth = reason == "canonical_execution_entry_truth"
    return TopOpportunityTruthRecord(
        trade_id=str(row.get("trade_id") or row.get("advisory_id") or row.get("trade_key") or ""),
        source_list=str(source_list),
        destination_list="top_executable" if executable_truth and source_list == "top_executable" else "top_advisory",
        executable_truth=bool(executable_truth and source_list == "top_executable"),
        reason=reason if source_list == "top_executable" else "source_list_advisory_not_promoted",
        execution_entry=execution_entry,
        execution_entry_source=execution_source,
        execution_entry_status=execution_status,
        display_entry=display_entry,
        display_entry_source=display_source,
        quote_source=quote_source,
        legacy_claims_executable=legacy_claims_executable,
    )


def _truth_reason(
    *,
    execution_entry: float | None,
    execution_source: str,
    execution_status: str,
    display_entry: float | None,
    display_source: str,
    quote_source: str,
    legacy_claims_executable: bool,
) -> str:
    if execution_source in _FALLBACK_SOURCES or display_source in _FALLBACK_SOURCES or quote_source in _FALLBACK_SOURCES:
        return "fallback_source_advisory_only"
    if execution_entry is None and display_entry is not None:
        return "display_only_missing_execution_entry"
    if execution_entry is None:
        return "missing_execution_entry"
    if execution_status != "executable":
        return "execution_entry_not_executable_status"
    if execution_source not in _EXECUTABLE_ENTRY_SOURCES:
        return "execution_entry_source_not_execution_grade"
    if legacy_claims_executable:
        return "canonical_execution_entry_truth"
    return "canonical_execution_entry_truth"


def _legacy_claims_executable(row: Mapping[str, Any]) -> bool:
    readiness = str(row.get("readiness") or "").strip().upper()
    execution_status = _lower(row.get("execution_status")) or ""
    final_action = str(row.get("final_action") or "").strip().upper()
    permission = str(row.get("permission") or "").strip().upper()
    status = str(row.get("status") or "").strip().upper()
    return bool(
        row.get("is_executable")
        or execution_status == "executable"
        or readiness == "READY"
        or final_action == "EXECUTE"
        or permission == "EXECUTE"
        or status == "READY"
    )


def _with_truth_demoted(row: Mapping[str, Any], reason: str) -> dict[str, Any]:
    out = dict(row)
    out["is_executable"] = False
    out["execution_status"] = "advisory_only"
    if str(out.get("readiness") or "").strip().upper() == "READY":
        out["readiness"] = "ADVISORY_ONLY"
    if str(out.get("permission") or "").strip().upper() == "EXECUTE":
        out["permission"] = "ADVISORY_ONLY"
    if str(out.get("final_action") or "").strip().upper() == "EXECUTE":
        out["final_action"] = "ADVISORY_ONLY"
    out["top_opportunity_truth_reason"] = str(reason)
    return out


def _coerce_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _positive_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if out != out or out <= 0:
        return None
    return float(out)


def _lower(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text or None


def _warnings(records: Iterable[TopOpportunityTruthRecord]) -> set[str]:
    warnings: set[str] = set()
    for record in records:
        if record.legacy_claims_executable and not record.executable_truth:
            warnings.add("legacy_executable_claim_demoted")
        if record.reason == "fallback_source_advisory_only":
            warnings.add("fallback_demoted_from_top_executable")
    return warnings


__all__ = [
    "TOP_OPPORTUNITY_EXECUTABLE_TRUTH_SCHEMA_VERSION",
    "TopOpportunityTruthRecord",
    "TopOpportunityTruthReport",
    "classify_top_opportunity_row",
    "normalize_top_opportunity_payload",
]
