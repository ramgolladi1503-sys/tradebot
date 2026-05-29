from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

LATENCY_HOTPATH_EVIDENCE_SOURCE = "latency_hotpath_evidence_v1"
LATENCY_EVIDENCE_MISSING_TIMING = "latency_evidence_incomplete_timing"
LATENCY_EVIDENCE_INCONSISTENT_TIMING = "latency_evidence_inconsistent_timing"

_DEFAULT_TOP_N = 5
_REQUIRED_NUMERIC_FIELDS = ("full_cycle_ms", "decision_critical_path_ms")


@dataclass(frozen=True)
class LatencyOperationEvidence:
    name: str
    duration_ms: float
    category: str = "unknown"

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "duration_ms": self.duration_ms,
            "category": self.category,
        }


def build_latency_hotpath_evidence(
    timings: Mapping[str, Any] | None,
    *,
    operations: Iterable[Mapping[str, Any] | LatencyOperationEvidence] | None = None,
    top_n: int = _DEFAULT_TOP_N,
) -> dict[str, Any]:
    """Build read-only latency evidence separating decision work from other cycle work.

    The function only normalizes evidence. It does not tune thresholds or change runtime decisions.
    """

    raw = dict(timings or {})
    full_cycle_ms = _float_or_none(raw.get("full_cycle_ms", raw.get("cycle_ms")))
    decision_critical_path_ms = _float_or_none(
        raw.get("decision_critical_path_ms", raw.get("critical_path_ms"))
    )
    background_overhead_ms = _float_or_none(raw.get("background_overhead_ms"))

    blockers: list[str] = []
    if full_cycle_ms is None or decision_critical_path_ms is None:
        blockers.append(LATENCY_EVIDENCE_MISSING_TIMING)
    if background_overhead_ms is None and full_cycle_ms is not None and decision_critical_path_ms is not None:
        background_overhead_ms = max(0.0, full_cycle_ms - decision_critical_path_ms)
    if (
        full_cycle_ms is not None
        and decision_critical_path_ms is not None
        and decision_critical_path_ms > full_cycle_ms
    ):
        blockers.append(LATENCY_EVIDENCE_INCONSISTENT_TIMING)

    top_operations = _top_operations(operations or (), top_n=top_n)
    status = "UNKNOWN" if blockers else "OK"

    return {
        "source": LATENCY_HOTPATH_EVIDENCE_SOURCE,
        "status": status,
        "fail_closed": bool(blockers),
        "blockers": _dedupe(blockers),
        "full_cycle_ms": full_cycle_ms,
        "decision_critical_path_ms": decision_critical_path_ms,
        "background_overhead_ms": background_overhead_ms,
        "top_operations": [operation.to_payload() for operation in top_operations],
        "raw_timing_keys": sorted(str(key) for key in raw.keys()),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
    }


def _top_operations(
    operations: Iterable[Mapping[str, Any] | LatencyOperationEvidence], *, top_n: int
) -> tuple[LatencyOperationEvidence, ...]:
    normalized: list[LatencyOperationEvidence] = []
    for row in operations:
        if isinstance(row, LatencyOperationEvidence):
            normalized.append(row)
            continue
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or row.get("operation") or "").strip()
        duration_ms = _float_or_none(row.get("duration_ms", row.get("ms")))
        if not name or duration_ms is None:
            continue
        normalized.append(
            LatencyOperationEvidence(
                name=name,
                duration_ms=duration_ms,
                category=str(row.get("category") or "unknown").strip() or "unknown",
            )
        )
    limit = max(0, int(top_n))
    return tuple(sorted(normalized, key=lambda item: item.duration_ms, reverse=True)[:limit])


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


__all__ = [
    "LATENCY_EVIDENCE_INCONSISTENT_TIMING",
    "LATENCY_EVIDENCE_MISSING_TIMING",
    "LATENCY_HOTPATH_EVIDENCE_SOURCE",
    "LatencyOperationEvidence",
    "build_latency_hotpath_evidence",
]
