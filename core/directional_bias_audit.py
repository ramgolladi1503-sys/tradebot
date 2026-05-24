"""Read-only directional-bias audit for ranked/top opportunity rows.

This module does not select, score, tune, allocate, or execute trades.  It only
summarizes whether ranked/top opportunity payloads are directionally concentrated
around BUY/SELL and CE/PE/CALL/PUT labels, and whether fallback/advisory rows are
contributing to that concentration.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Sequence

DIRECTIONAL_BIAS_AUDIT_SCHEMA_VERSION = 1

_BUY_LABELS = {"BUY", "LONG", "B", "BUY_TO_OPEN", "BTO"}
_SELL_LABELS = {"SELL", "SHORT", "S", "SELL_TO_OPEN", "STO"}
_CALL_LABELS = {"CE", "CALL", "CALLS"}
_PUT_LABELS = {"PE", "PUT", "PUTS"}
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


@dataclass(frozen=True)
class DirectionalBiasRecord:
    """Per-row direction extraction evidence."""

    row_id: str
    source_list: str
    action: str
    option_side: str
    composite_direction: str
    bucket: str
    warnings: tuple[str, ...]
    raw_direction_fields: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DirectionalBiasAuditReport:
    """Read-only directional-bias audit result."""

    is_order_action = False
    broker_api_called = False
    live_order_action = False
    broker_order_action = False
    append = False

    schema_version: int
    read_only: bool
    total_rows: int
    executable_rows: int
    advisory_rows: int
    fallback_rows: int
    unknown_direction_rows: int
    inconsistent_direction_rows: int
    action_counts: dict[str, int]
    option_side_counts: dict[str, int]
    composite_direction_counts: dict[str, int]
    executable_action_counts: dict[str, int]
    executable_option_side_counts: dict[str, int]
    executable_composite_direction_counts: dict[str, int]
    advisory_composite_direction_counts: dict[str, int]
    fallback_composite_direction_counts: dict[str, int]
    warnings: tuple[str, ...]
    records: tuple[DirectionalBiasRecord, ...]
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
            "total_rows": self.total_rows,
            "executable_rows": self.executable_rows,
            "advisory_rows": self.advisory_rows,
            "fallback_rows": self.fallback_rows,
            "unknown_direction_rows": self.unknown_direction_rows,
            "inconsistent_direction_rows": self.inconsistent_direction_rows,
            "action_counts": dict(self.action_counts),
            "option_side_counts": dict(self.option_side_counts),
            "composite_direction_counts": dict(self.composite_direction_counts),
            "executable_action_counts": dict(self.executable_action_counts),
            "executable_option_side_counts": dict(self.executable_option_side_counts),
            "executable_composite_direction_counts": dict(self.executable_composite_direction_counts),
            "advisory_composite_direction_counts": dict(self.advisory_composite_direction_counts),
            "fallback_composite_direction_counts": dict(self.fallback_composite_direction_counts),
            "warnings": list(self.warnings),
            "records": [record.to_dict() for record in self.records],
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def audit_directional_bias(
    rows_or_payload: Mapping[str, Any] | Iterable[Mapping[str, Any]] | None,
    *,
    min_skew_count: int = 2,
    skew_ratio: float = 0.80,
) -> DirectionalBiasAuditReport:
    """Audit directional concentration in ranked/top opportunity rows.

    The audit is intentionally read-only. Unknown or inconsistent direction does
    not become executable truth; it is surfaced as a fail-closed warning.
    """

    rows = _extract_rows(rows_or_payload)
    records = tuple(_classify_row(row, source_list=source_list) for source_list, row in rows)

    action_counts = _counts(record.action for record in records if record.action != "UNKNOWN")
    option_counts = _counts(record.option_side for record in records if record.option_side != "UNKNOWN")
    composite_counts = _counts(record.composite_direction for record in records if record.composite_direction != "UNKNOWN")

    executable = [record for record in records if record.bucket == "executable"]
    advisory = [record for record in records if record.bucket == "advisory"]
    fallback = [record for record in records if record.bucket == "fallback"]

    executable_action_counts = _counts(record.action for record in executable if record.action != "UNKNOWN")
    executable_option_counts = _counts(record.option_side for record in executable if record.option_side != "UNKNOWN")
    executable_composite_counts = _counts(record.composite_direction for record in executable if record.composite_direction != "UNKNOWN")
    advisory_composite_counts = _counts(record.composite_direction for record in advisory if record.composite_direction != "UNKNOWN")
    fallback_composite_counts = _counts(record.composite_direction for record in fallback if record.composite_direction != "UNKNOWN")

    warnings = set(_row_warnings(records))
    warnings.update(_skew_warnings("option_side", executable_option_counts, min_skew_count=min_skew_count, skew_ratio=skew_ratio))
    warnings.update(_skew_warnings("composite_direction", executable_composite_counts, min_skew_count=min_skew_count, skew_ratio=skew_ratio))

    # BUY/SELL concentration is useful, but in long-option systems every valid
    # CE/PE candidate may be BUY. Do not call that directional bias if option
    # side exposure is itself balanced.
    if not _has_balanced_ce_pe(executable_option_counts):
        warnings.update(_skew_warnings("action", executable_action_counts, min_skew_count=min_skew_count, skew_ratio=skew_ratio))

    if fallback and fallback_composite_counts:
        dominant = _dominant_label(fallback_composite_counts)
        if dominant:
            warnings.add(f"fallback_rows_contribute_directional_bias:{dominant}")
    if advisory and advisory_composite_counts:
        dominant = _dominant_label(advisory_composite_counts)
        if dominant:
            warnings.add(f"advisory_rows_directional_concentration:{dominant}")

    unknown_rows = sum(1 for record in records if "missing_or_unknown_direction" in record.warnings)
    inconsistent_rows = sum(1 for record in records if "inconsistent_direction_labels" in record.warnings)

    return DirectionalBiasAuditReport(
        schema_version=DIRECTIONAL_BIAS_AUDIT_SCHEMA_VERSION,
        read_only=True,
        total_rows=len(records),
        executable_rows=len(executable),
        advisory_rows=len(advisory),
        fallback_rows=len(fallback),
        unknown_direction_rows=unknown_rows,
        inconsistent_direction_rows=inconsistent_rows,
        action_counts=action_counts,
        option_side_counts=option_counts,
        composite_direction_counts=composite_counts,
        executable_action_counts=executable_action_counts,
        executable_option_side_counts=executable_option_counts,
        executable_composite_direction_counts=executable_composite_counts,
        advisory_composite_direction_counts=advisory_composite_counts,
        fallback_composite_direction_counts=fallback_composite_counts,
        warnings=tuple(sorted(warnings)),
        records=records,
        metadata={
            "contract": "directional_bias_audit_v1",
            "scope": "read_only_no_strategy_tuning_no_broker_no_order",
            "min_skew_count": int(min_skew_count),
            "skew_ratio": float(skew_ratio),
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
            "top_advisory_opportunities",
            "ranked_opportunities",
            "candidates",
            "rows",
            "items",
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


def _classify_row(row: Mapping[str, Any], *, source_list: str) -> DirectionalBiasRecord:
    raw_fields = _raw_direction_fields(row)
    actions = _extract_action_labels(raw_fields.values())
    option_sides = _extract_option_side_labels(raw_fields.values())

    action = _single_or_unknown(actions)
    option_side = _single_or_unknown(option_sides)
    warnings: set[str] = set()
    if not actions and not option_sides:
        warnings.add("missing_or_unknown_direction")
    if len(actions) > 1 or len(option_sides) > 1:
        warnings.add("inconsistent_direction_labels")

    composite_direction = _composite_direction(action, option_side)
    bucket = _bucket(row, source_list)

    return DirectionalBiasRecord(
        row_id=str(row.get("trade_id") or row.get("candidate_id") or row.get("advisory_id") or row.get("symbol") or ""),
        source_list=str(source_list),
        action=action,
        option_side=option_side,
        composite_direction=composite_direction,
        bucket=bucket,
        warnings=tuple(sorted(warnings)),
        raw_direction_fields=raw_fields,
    )


def _raw_direction_fields(row: Mapping[str, Any]) -> dict[str, str]:
    keys = (
        "direction",
        "direction_label",
        "trade_direction",
        "side",
        "action",
        "order_side",
        "transaction_type",
        "option_type",
        "instrument_type",
        "right",
        "contract_type",
        "symbol",
        "tradingsymbol",
        "trading_symbol",
    )
    return {key: str(row.get(key)).strip().upper() for key in keys if row.get(key) not in (None, "")}


def _extract_action_labels(values: Iterable[str]) -> set[str]:
    labels: set[str] = set()
    for value in values:
        tokens = _tokens(value)
        if tokens & _BUY_LABELS:
            labels.add("BUY")
        if tokens & _SELL_LABELS:
            labels.add("SELL")
    return labels


def _extract_option_side_labels(values: Iterable[str]) -> set[str]:
    labels: set[str] = set()
    for value in values:
        tokens = _tokens(value)
        if tokens & _CALL_LABELS:
            labels.add("CE")
        if tokens & _PUT_LABELS:
            labels.add("PE")
    return labels


def _tokens(value: str) -> set[str]:
    normalized = value.replace("-", "_").replace("/", "_").replace(".", "_").replace(" ", "_")
    parts = {part for part in normalized.split("_") if part}
    parts.add(normalized)
    return parts


def _single_or_unknown(labels: set[str]) -> str:
    if len(labels) == 1:
        return next(iter(labels))
    return "UNKNOWN"


def _composite_direction(action: str, option_side: str) -> str:
    if action != "UNKNOWN" and option_side != "UNKNOWN":
        return f"{action}_{option_side}"
    if option_side != "UNKNOWN":
        return option_side
    if action != "UNKNOWN":
        return action
    return "UNKNOWN"


def _bucket(row: Mapping[str, Any], source_list: str) -> str:
    values = [str(value).strip().lower() for value in row.values() if value is not None]
    if source_list == "top_advisory_opportunities" or any(_contains_marker(value, _ADVISORY_MARKERS) for value in values):
        return "advisory"
    if any(_contains_marker(value, _FALLBACK_MARKERS) for value in values):
        return "fallback"
    if source_list == "top_executable_opportunities" or any(_contains_marker(value, _EXECUTABLE_MARKERS) for value in values):
        return "executable"
    return "advisory"


def _contains_marker(value: str, markers: set[str]) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in markers)


def _counts(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _row_warnings(records: Sequence[DirectionalBiasRecord]) -> set[str]:
    warnings: set[str] = set()
    if any("missing_or_unknown_direction" in record.warnings for record in records):
        warnings.add("missing_or_unknown_direction_fail_closed")
    if any("inconsistent_direction_labels" in record.warnings for record in records):
        warnings.add("inconsistent_direction_labels_fail_closed")
    return warnings


def _skew_warnings(label: str, counts: Mapping[str, int], *, min_skew_count: int, skew_ratio: float) -> set[str]:
    if not counts:
        return set()
    total = sum(counts.values())
    if total < min_skew_count:
        return set()
    dominant = max(counts.items(), key=lambda item: (item[1], item[0]))
    if dominant[1] / total >= skew_ratio:
        return {f"directional_skew:{label}:{dominant[0]}:{dominant[1]}/{total}"}
    return set()


def _dominant_label(counts: Mapping[str, int]) -> str | None:
    if not counts:
        return None
    total = sum(counts.values())
    dominant = max(counts.items(), key=lambda item: (item[1], item[0]))
    if total and dominant[1] == total:
        return dominant[0]
    return None


def _has_balanced_ce_pe(counts: Mapping[str, int]) -> bool:
    ce = counts.get("CE", 0)
    pe = counts.get("PE", 0)
    return ce > 0 and pe > 0 and ce == pe and sum(counts.values()) == ce + pe


__all__ = [
    "DIRECTIONAL_BIAS_AUDIT_SCHEMA_VERSION",
    "DirectionalBiasAuditReport",
    "DirectionalBiasRecord",
    "audit_directional_bias",
]
