from __future__ import annotations


def reconcile(records: list[dict[str, object]], audit: dict[str, object]) -> dict[str, object]:
    return {
        "status": "SIGNAL_EXECUTION_BLOCKED" if not records else "SIGNAL_LEDGER_RECONCILED",
        "signal_count": len(records),
        "legacy_option_replay_audit_record_count": len(audit.get("legacy_option_replay_audit_records", [])),
        "invalidated_historical_record_count": len(audit.get("invalidated_historical_records", [])),
    }

