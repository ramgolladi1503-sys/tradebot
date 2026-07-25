from __future__ import annotations


def certify_ledger(records: list[dict[str, object]]) -> dict[str, object]:
    if not records:
        return {"verdict": "SOURCE_BLOCKED", "records": [], "failures": ["NO_VERTICAL_SLICE_RECORDS"]}
    if all(record.get("status") == "SOURCE_BLOCKED" for record in records):
        blockers = sorted({blocker for record in records for blocker in record.get("blockers", [])})
        return {"verdict": "SOURCE_BLOCKED", "records": records, "failures": blockers}
    return {"verdict": "SIGNAL_LEDGER_CERTIFIED", "records": records, "failures": []}

