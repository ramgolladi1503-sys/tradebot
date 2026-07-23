from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .adapter_contract import SignalLedgerContract


def certify_ledger(records: list[SignalLedgerContract]) -> dict[str, Any]:
    failures: list[str] = []
    for record in records:
        if record.source_kind == "CURRENT_MASTER_DIAGNOSTIC_ONLY":
            failures.append("CURRENT_MASTER_NOT_HISTORICAL_AUTHORITY")
        if record.source_kind == "DATED_HISTORICAL_SNAPSHOT" and not record.source_artifact_hash:
            failures.append("DATED_SOURCE_HASH_MISSING")
    return {
        "verdict": "SIGNAL_LEDGER_CERTIFIED" if not failures else "SIGNAL_LEDGER_NOT_CERTIFIED",
        "failures": sorted(set(failures)),
        "records": [asdict(record) for record in records],
    }
