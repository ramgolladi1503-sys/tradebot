from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from .git_provenance import EXPECTED_LEDGER_SHA256, EXPECTED_ROW_COUNT

SAFETY_FLAGS = {
    "research_only": True,
    "read_only": True,
    "broker_api_called": False,
    "is_order_action": False,
    "allowed_for_live_execution": False,
    "outcomes_read": False,
    "pnl_read": False,
    "holdout_outcomes_read": False,
}


class AuditError(ValueError):
    pass


def semantic_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def physical_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _all_nonempty(records: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> bool:
    return bool(records) and all(all(record.get(field) not in (None, "") for field in fields) for record in records)


def _causal_ordering(records: Sequence[Mapping[str, Any]]) -> str:
    fields = ("feature_cutoff_ts", "signal_ts", "earliest_entry_ts")
    if not _all_nonempty(records, fields):
        return "UNRESOLVED"
    if all(record[fields[0]] <= record[fields[1]] < record[fields[2]] for record in records):
        return "CAUSAL_ORDERING_PROVEN"
    return "INVALID_CAUSAL_ORDERING"


def audit_signal_ledger(
    ledger_content: bytes,
    evidence: Mapping[str, Any],
    *,
    expected_sha256: str = EXPECTED_LEDGER_SHA256,
    expected_row_count: int = EXPECTED_ROW_COUNT,
) -> dict[str, Any]:
    ledger_sha256 = physical_sha256(ledger_content)
    if ledger_sha256 != expected_sha256:
        raise AuditError("LEDGER_PHYSICAL_HASH_MISMATCH")
    payload = json.loads(ledger_content)
    records = payload.get("records")
    if not isinstance(records, list) or len(records) != expected_row_count:
        raise AuditError("LEDGER_ROW_COUNT_MISMATCH")
    if any(not isinstance(record, Mapping) for record in records):
        raise AuditError("LEDGER_RECORD_INVALID")

    ownership = dict(evidence.get("ownership", {}))
    historical_binding = dict(evidence.get("historical_binding", {}))
    invalidation = dict(evidence.get("invalidation", {}))
    search_records = list(evidence.get("search_records", []))
    causal_ordering = _causal_ordering(records)
    temporal_complete = _all_nonempty(records, ("feature_cutoff_ts", "signal_ts", "earliest_entry_ts"))
    split_complete = _all_nonempty(records, ("fold_id",)) and bool(evidence.get("split_manifest"))

    derived_invalidation = invalidation.get("derived_ledger_invalidation_authority") == "CONFIRMED"
    direct_invalidation = invalidation.get("direct_ledger_invalidation_authority") == "CONFIRMED"
    if causal_ordering == "INVALID_CAUSAL_ORDERING" or direct_invalidation or derived_invalidation:
        verdict = "SIGNAL_LEDGER_INVALIDATED"
    elif ownership.get("embedded_row_owner_field_authority") != "PROVEN":
        verdict = "SIGNAL_LEDGER_PROVENANCE_BLOCKED"
    else:
        verdict = "SIGNAL_LEDGER_OWNERSHIP_PROVEN_BUT_PROVENANCE_INCOMPLETE"

    return {
        "schema_version": "signal_ledger_provenance_v1",
        **SAFETY_FLAGS,
        "ledger": {
            "canonical_signal_ledger_id": f"{ledger_sha256}:{len(records)}",
            "physical_sha256": ledger_sha256,
            "row_count": len(records),
            "artifact_kind": "MULTI_OWNER_BLOCKED_PLACEHOLDER_INVENTORY",
        },
        "ownership": ownership,
        "implementation": {
            "implementation_authority": (
                "PROVEN_FOR_PLACEHOLDER_GENERATOR_ONLY"
                if historical_binding.get("generator_output_binding", {}).get("status") == "PROVEN"
                else "UNRESOLVED"
            ),
            "historical_binding": historical_binding,
        },
        "parameters": {
            "parameter_authority": "UNRESOLVED",
            "parameter_manifest": None,
            "parameter_manifest_sha256": None,
            "missing_parameter_fields": ["names", "values", "types", "owner", "ledger_binding"],
        },
        "dataset": {
            "dataset_authority": "UNRESOLVED",
            "dataset_family_id": None,
            "dataset_version_id": None,
            "dataset_manifest_sha256": None,
            "dataset_content_sha256": None,
            "dataset_binding_evidence": [],
        },
        "temporal_split": {
            "temporal_authority": "PROVEN" if temporal_complete and causal_ordering == "CAUSAL_ORDERING_PROVEN" else "INVALID" if causal_ordering == "INVALID_CAUSAL_ORDERING" else "UNRESOLVED",
            "split_authority": "PROVEN" if split_complete else "UNRESOLVED",
            "causal_ordering_result": causal_ordering,
            "fold_identity": sorted({record.get("fold_id") for record in records}) if split_complete else None,
            "split_identity": evidence.get("split_manifest", {}).get("split_identity") if split_complete else None,
        },
        "freeze_contamination": {
            "freeze_authority": "UNRESOLVED",
            "outcome_contamination_authority": "UNRESOLVED",
            "option_price_contamination_authority": "UNRESOLVED",
            "tuning_contamination_authority": "UNRESOLVED",
            "holdout_contamination_authority": "UNRESOLVED",
            "direct_ledger_invalidation_authority": invalidation.get("direct_ledger_invalidation_authority", "UNRESOLVED"),
            "implementation_invalidation_authority": invalidation.get("implementation_invalidation_authority", "UNRESOLVED"),
            "derived_ledger_invalidation_authority": invalidation.get("derived_ledger_invalidation_authority", "UNRESOLVED"),
        },
        "historical_invalidation": invalidation,
        "source_searches": search_records,
        "verdict": verdict,
    }
