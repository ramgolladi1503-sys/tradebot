from __future__ import annotations


def reconcile_lanes(records: list[dict[str, object]]) -> dict[str, object]:
    exact_blockers = sorted({blocker for record in records for blocker in record.get("blockers", [])})
    return {
        "record_count": len(records),
        "status": "SOURCE_BLOCKED" if records else "SOURCE_BLOCKED",
        "exact_blockers": exact_blockers,
    }

