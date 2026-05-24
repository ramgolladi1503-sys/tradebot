"""Read-only capital allocation and selection policy contract.

EDGE-61 explains which ranked/top opportunity rows may be selected, capped,
skipped, or blocked. It does not mutate candidates, call brokers, optimize live
capital, or place orders.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

CAPITAL_SELECTION_POLICY_SCHEMA_VERSION = 1

_FALLBACK_MARKERS = {
    "rest_fallback",
    "recovered_fallback",
    "fallback_recovered",
    "fallback_estimated",
    "fallback",
    "price_mismatch",
    "stale_option_ltp",
    "subscription_failed",
}
_ADVISORY_MARKERS = {"advisory", "advisory_only", "displayable", "display_only", "debug"}
_EXECUTABLE_MARKERS = {"executable", "ready", "execute", "top_executable"}
_ZERO_ALLOCATION_REASONS = {
    "fallback_or_stale_data_advisory_only",
    "advisory_or_display_only_candidate",
    "not_execution_eligible",
    "selection_limit_reached",
    "symbol_cap_reached",
    "family_cap_reached",
    "capital_budget_exhausted",
    "invalid_policy_input",
}


@dataclass(frozen=True)
class CapitalSelectionPolicy:
    """Configuration for the read-only selection policy."""

    total_capital: float
    max_selected: int
    max_allocation_per_candidate: float
    default_allocation_per_candidate: float
    max_per_symbol: int = 1
    max_per_family: int = 1
    min_allocation_per_candidate: float = 0.0

    def normalized(self) -> "CapitalSelectionPolicy":
        return CapitalSelectionPolicy(
            total_capital=max(0.0, float(self.total_capital)),
            max_selected=max(0, int(self.max_selected)),
            max_allocation_per_candidate=max(0.0, float(self.max_allocation_per_candidate)),
            default_allocation_per_candidate=max(0.0, float(self.default_allocation_per_candidate)),
            max_per_symbol=max(0, int(self.max_per_symbol)),
            max_per_family=max(0, int(self.max_per_family)),
            min_allocation_per_candidate=max(0.0, float(self.min_allocation_per_candidate)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.normalized())


@dataclass(frozen=True)
class CapitalSelectionRecord:
    candidate_id: str
    rank: int
    symbol: str
    family: str
    source_list: str
    status: str
    selected: bool
    requested_allocation: float
    assigned_allocation: float
    capped: bool
    reason: str
    executable_eligible: bool
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapitalSelectionPolicyReport:
    """Read-only selection/allocation explanation report."""

    is_order_action = False
    broker_api_called = False
    live_order_action = False
    broker_order_action = False
    append = False

    schema_version: int
    read_only: bool
    policy: dict[str, Any]
    total_candidates: int
    selected_count: int
    capped_count: int
    skipped_count: int
    blocked_count: int
    total_assigned_allocation: float
    remaining_capital: float
    records: tuple[CapitalSelectionRecord, ...]
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
            "policy": dict(self.policy),
            "total_candidates": self.total_candidates,
            "selected_count": self.selected_count,
            "capped_count": self.capped_count,
            "skipped_count": self.skipped_count,
            "blocked_count": self.blocked_count,
            "total_assigned_allocation": self.total_assigned_allocation,
            "remaining_capital": self.remaining_capital,
            "records": [record.to_dict() for record in self.records],
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def explain_capital_selection_policy(
    rows_or_payload: Mapping[str, Any] | Iterable[Mapping[str, Any]] | None,
    *,
    policy: CapitalSelectionPolicy,
) -> CapitalSelectionPolicyReport:
    """Return read-only capital/selection decisions for ranked candidates."""

    normalized_policy = policy.normalized()
    rows = _extract_rows(rows_or_payload)
    records: list[CapitalSelectionRecord] = []
    selected_by_symbol: Counter[str] = Counter()
    selected_by_family: Counter[str] = Counter()
    selected_count = 0
    assigned_total = 0.0
    warnings: set[str] = set()

    for rank, (source_list, row) in enumerate(rows, start=1):
        candidate_id = _candidate_id(row, rank)
        symbol = _candidate_symbol(row)
        family = _candidate_family(row)
        bucket = _candidate_bucket(row, source_list)
        requested = _requested_allocation(row, normalized_policy)
        executable_eligible = bucket == "executable"
        evidence = {
            "bucket": bucket,
            "source_list": source_list,
            "selection_limit_used": selected_count,
            "symbol_selected_count": selected_by_symbol.get(symbol, 0),
            "family_selected_count": selected_by_family.get(family, 0),
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_action": False,
            "broker_order_action": False,
        }

        if not executable_eligible:
            reason = _blocked_reason(bucket)
            records.append(
                _record(
                    candidate_id=candidate_id,
                    rank=rank,
                    symbol=symbol,
                    family=family,
                    source_list=source_list,
                    status="BLOCKED",
                    selected=False,
                    requested=requested,
                    assigned=0.0,
                    capped=False,
                    reason=reason,
                    executable_eligible=False,
                    evidence=evidence,
                )
            )
            warnings.add(reason)
            continue

        if normalized_policy.max_selected <= 0 or selected_count >= normalized_policy.max_selected:
            records.append(
                _record(
                    candidate_id=candidate_id,
                    rank=rank,
                    symbol=symbol,
                    family=family,
                    source_list=source_list,
                    status="SKIPPED",
                    selected=False,
                    requested=requested,
                    assigned=0.0,
                    capped=False,
                    reason="selection_limit_reached",
                    executable_eligible=True,
                    evidence=evidence,
                )
            )
            continue

        if normalized_policy.max_per_symbol > 0 and selected_by_symbol[symbol] >= normalized_policy.max_per_symbol:
            records.append(
                _record(
                    candidate_id=candidate_id,
                    rank=rank,
                    symbol=symbol,
                    family=family,
                    source_list=source_list,
                    status="SKIPPED",
                    selected=False,
                    requested=requested,
                    assigned=0.0,
                    capped=False,
                    reason="symbol_cap_reached",
                    executable_eligible=True,
                    evidence=evidence,
                )
            )
            continue

        if normalized_policy.max_per_family > 0 and selected_by_family[family] >= normalized_policy.max_per_family:
            records.append(
                _record(
                    candidate_id=candidate_id,
                    rank=rank,
                    symbol=symbol,
                    family=family,
                    source_list=source_list,
                    status="SKIPPED",
                    selected=False,
                    requested=requested,
                    assigned=0.0,
                    capped=False,
                    reason="family_cap_reached",
                    executable_eligible=True,
                    evidence=evidence,
                )
            )
            continue

        remaining = max(0.0, normalized_policy.total_capital - assigned_total)
        if remaining <= 0.0:
            records.append(
                _record(
                    candidate_id=candidate_id,
                    rank=rank,
                    symbol=symbol,
                    family=family,
                    source_list=source_list,
                    status="SKIPPED",
                    selected=False,
                    requested=requested,
                    assigned=0.0,
                    capped=False,
                    reason="capital_budget_exhausted",
                    executable_eligible=True,
                    evidence=evidence,
                )
            )
            continue

        candidate_cap = min(normalized_policy.max_allocation_per_candidate, remaining)
        assigned = min(requested, candidate_cap)
        capped = requested > assigned
        if assigned < normalized_policy.min_allocation_per_candidate:
            records.append(
                _record(
                    candidate_id=candidate_id,
                    rank=rank,
                    symbol=symbol,
                    family=family,
                    source_list=source_list,
                    status="SKIPPED",
                    selected=False,
                    requested=requested,
                    assigned=0.0,
                    capped=False,
                    reason="capital_budget_exhausted",
                    executable_eligible=True,
                    evidence=evidence,
                )
            )
            continue

        selected_count += 1
        selected_by_symbol[symbol] += 1
        selected_by_family[family] += 1
        assigned_total = round(assigned_total + assigned, 6)
        records.append(
            _record(
                candidate_id=candidate_id,
                rank=rank,
                symbol=symbol,
                family=family,
                source_list=source_list,
                status="CAPPED" if capped else "SELECTED",
                selected=True,
                requested=requested,
                assigned=assigned,
                capped=capped,
                reason="max_candidate_allocation_cap" if capped else "selected_within_policy",
                executable_eligible=True,
                evidence=evidence,
            )
        )

    selected_records = tuple(record for record in records if record.selected)
    zero_allocation_violations = tuple(
        record for record in records if not record.selected and record.assigned_allocation != 0.0
    )
    over_allocation_violations = tuple(
        record
        for record in selected_records
        if record.assigned_allocation > normalized_policy.max_allocation_per_candidate
    )
    eligible_without_reason = tuple(
        record
        for record in records
        if record.executable_eligible and not record.selected and record.reason in {"", "NO_SELECTION"}
    )
    if zero_allocation_violations:
        warnings.add("zero_allocation_invariant_violation")
    if over_allocation_violations:
        warnings.add("max_candidate_allocation_invariant_violation")
    if eligible_without_reason:
        warnings.add("eligible_candidate_missing_selection_reason")

    capped_count = sum(1 for record in records if record.status == "CAPPED")
    skipped_count = sum(1 for record in records if record.status == "SKIPPED")
    blocked_count = sum(1 for record in records if record.status == "BLOCKED")
    return CapitalSelectionPolicyReport(
        schema_version=CAPITAL_SELECTION_POLICY_SCHEMA_VERSION,
        read_only=True,
        policy=normalized_policy.to_dict(),
        total_candidates=len(records),
        selected_count=sum(1 for record in records if record.selected),
        capped_count=capped_count,
        skipped_count=skipped_count,
        blocked_count=blocked_count,
        total_assigned_allocation=round(assigned_total, 6),
        remaining_capital=round(max(0.0, normalized_policy.total_capital - assigned_total), 6),
        records=tuple(records),
        warnings=tuple(sorted(warnings)),
        metadata={
            "contract": "capital_selection_policy_v1",
            "scope": "read_only_no_broker_no_order_no_live_allocation",
            "zero_allocation_reasons": sorted(_ZERO_ALLOCATION_REASONS),
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_action": False,
            "broker_order_action": False,
        },
    )


def _extract_rows(
    rows_or_payload: Mapping[str, Any] | Iterable[Mapping[str, Any]] | None,
) -> list[tuple[str, Mapping[str, Any]]]:
    if rows_or_payload is None:
        return []
    if isinstance(rows_or_payload, Mapping):
        extracted: list[tuple[str, Mapping[str, Any]]] = []
        for key in (
            "top_executable_opportunities",
            "ranked_opportunities",
            "selected_candidates",
            "candidates",
            "rows",
            "items",
            "top_advisory_opportunities",
        ):
            value = rows_or_payload.get(key)
            if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
                extracted.extend((key, row) for row in value if isinstance(row, Mapping))
        if extracted:
            return extracted
        return [("payload", rows_or_payload)]
    if isinstance(rows_or_payload, Iterable) and not isinstance(rows_or_payload, (str, bytes)):
        return [("rows", row) for row in rows_or_payload if isinstance(row, Mapping)]
    return []


def _record(
    *,
    candidate_id: str,
    rank: int,
    symbol: str,
    family: str,
    source_list: str,
    status: str,
    selected: bool,
    requested: float,
    assigned: float,
    capped: bool,
    reason: str,
    executable_eligible: bool,
    evidence: dict[str, Any],
) -> CapitalSelectionRecord:
    return CapitalSelectionRecord(
        candidate_id=candidate_id,
        rank=int(rank),
        symbol=symbol,
        family=family,
        source_list=source_list,
        status=status,
        selected=bool(selected),
        requested_allocation=round(float(requested), 6),
        assigned_allocation=round(float(assigned), 6),
        capped=bool(capped),
        reason=str(reason),
        executable_eligible=bool(executable_eligible),
        evidence=dict(evidence),
    )


def _candidate_id(row: Mapping[str, Any], rank: int) -> str:
    return str(
        row.get("candidate_id")
        or row.get("trade_id")
        or row.get("trade_key")
        or row.get("advisory_id")
        or row.get("symbol")
        or f"candidate-{rank}"
    ).strip()


def _candidate_symbol(row: Mapping[str, Any]) -> str:
    return str(row.get("symbol") or row.get("underlying") or "UNKNOWN").strip().upper() or "UNKNOWN"


def _candidate_family(row: Mapping[str, Any]) -> str:
    source_flags = row.get("source_flags") if isinstance(row.get("source_flags"), Mapping) else {}
    origin = source_flags.get("candidate_origin") if isinstance(source_flags.get("candidate_origin"), Mapping) else {}
    family = (
        row.get("strategy_family")
        or row.get("setup_family")
        or origin.get("setup_family")
        or source_flags.get("strategy_family")
        or source_flags.get("setup_family")
        or row.get("strategy")
        or "UNKNOWN"
    )
    return str(family).strip().lower() or "unknown"


def _candidate_bucket(row: Mapping[str, Any], source_list: str) -> str:
    values = [str(value).strip().lower() for value in _flatten_values(row)]
    if any(_contains_marker(value, _FALLBACK_MARKERS) for value in values):
        return "fallback"
    if source_list == "top_advisory_opportunities" or any(_contains_marker(value, _ADVISORY_MARKERS) for value in values):
        return "advisory"
    if source_list in {"top_executable_opportunities", "ranked_opportunities", "selected_candidates"}:
        return "executable"
    if any(_contains_marker(value, _EXECUTABLE_MARKERS) for value in values):
        return "executable"
    if bool(row.get("is_executable")) and not any(_contains_marker(value, _ADVISORY_MARKERS) for value in values):
        return "executable"
    return "unknown"


def _flatten_values(value: Any) -> Iterable[Any]:
    if isinstance(value, Mapping):
        for nested in value.values():
            yield from _flatten_values(nested)
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        for nested in value:
            yield from _flatten_values(nested)
    else:
        yield value


def _contains_marker(value: str, markers: set[str]) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in markers)


def _requested_allocation(row: Mapping[str, Any], policy: CapitalSelectionPolicy) -> float:
    explicit = _first_positive_float(
        row.get("requested_allocation"),
        row.get("proposed_allocation"),
        row.get("capital_requested"),
        row.get("capital_at_risk"),
        row.get("capital_required"),
    )
    if explicit is not None:
        return explicit
    entry = _first_positive_float(row.get("execution_entry"), row.get("entry_price"), row.get("display_entry"), row.get("entry"))
    qty = _first_positive_float(row.get("qty_units"), row.get("qty"), row.get("quantity"))
    if entry is not None and qty is not None:
        return round(float(entry) * float(qty), 6)
    return policy.default_allocation_per_candidate


def _first_positive_float(*values: Any) -> float | None:
    for value in values:
        try:
            if value in (None, "", "None"):
                continue
            parsed = float(value)
        except Exception:
            continue
        if parsed > 0 and parsed == parsed:
            return float(parsed)
    return None


def _blocked_reason(bucket: str) -> str:
    if bucket == "fallback":
        return "fallback_or_stale_data_advisory_only"
    if bucket == "advisory":
        return "advisory_or_display_only_candidate"
    return "not_execution_eligible"


__all__ = [
    "CAPITAL_SELECTION_POLICY_SCHEMA_VERSION",
    "CapitalSelectionPolicy",
    "CapitalSelectionPolicyReport",
    "CapitalSelectionRecord",
    "explain_capital_selection_policy",
]
