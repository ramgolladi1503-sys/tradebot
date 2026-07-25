from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from .adapter_contract import SignalLedgerContract

_HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def certify_ledger(records: list[SignalLedgerContract]) -> dict[str, Any]:
    failures: list[str] = []
    if not records:
        failures.append("EMPTY_SIGNAL_LEDGER")
    for record in records:
        required_fields = {
            "feature_cutoff_ts": record.feature_cutoff_ts,
            "signal_ts": record.signal_ts,
            "earliest_entry_ts": record.earliest_entry_ts,
            "direction": record.direction,
            "signal_strength": record.signal_strength,
            "params_hash": record.params_hash,
            "source_artifact_hash": record.source_artifact_hash,
            "implementation_sha": record.implementation_sha,
            "dataset_hash": record.dataset_hash,
            "fold_id": record.fold_id,
        }
        for field_name, value in required_fields.items():
            if not value:
                failures.append(f"MISSING_{field_name.upper()}")
        if record.direction == "UNKNOWN":
            failures.append("UNKNOWN_DIRECTION")
        if not _HEX_SHA256_RE.fullmatch(record.implementation_sha):
            failures.append("INVALID_IMPLEMENTATION_SHA")
        if record.source_kind != "STRATEGY_SIGNAL_SOURCE_CANDIDATE":
            failures.append("NON_STRATEGY_SIGNAL_SOURCE")
        if record.oracle_status != "SIGNAL_SOURCE_RESOLVED":
            failures.append("SIGNAL_SOURCE_NOT_RESOLVED")
    return {
        "verdict": "SIGNAL_LEDGER_CERTIFIED" if not failures else "SIGNAL_LEDGER_NOT_CERTIFIED",
        "failures": sorted(set(failures)),
        "records": [asdict(record) for record in records],
    }
