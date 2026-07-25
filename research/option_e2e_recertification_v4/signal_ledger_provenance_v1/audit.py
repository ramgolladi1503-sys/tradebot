from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


EXPECTED_LEDGER_SHA256 = "b9736aa6af68a07c32a01dbc2bc60220acf8337181e3878940abfab540398bed"
EXPECTED_ROW_COUNT = 24
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


def _binding(evidence: Mapping[str, Any], name: str, ledger_sha256: str) -> Mapping[str, Any] | None:
    value = evidence.get(name)
    if not isinstance(value, Mapping) or value.get("ledger_sha256") != ledger_sha256:
        return None
    return value


def _all_nonempty(records: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> bool:
    return bool(records) and all(all(record.get(field) not in (None, "") for field in fields) for record in records)


def _causal_ordering(records: Sequence[Mapping[str, Any]]) -> str:
    fields = ("feature_cutoff_ts", "signal_ts", "earliest_entry_ts")
    if not _all_nonempty(records, fields):
        return "UNRESOLVED"
    if all(record[fields[0]] <= record[fields[1]] < record[fields[2]] for record in records):
        return "CAUSAL_ORDERING_PROVEN"
    return "INVALID_CAUSAL_ORDERING"


def _parameters_complete(binding: Mapping[str, Any] | None) -> bool:
    if not binding or binding.get("complete") is not True or not binding.get("owner"):
        return False
    parameters = binding.get("parameters")
    return bool(parameters) and all(
        isinstance(parameter, Mapping)
        and set(parameter) >= {"name", "value", "type"}
        and parameter.get("name")
        and parameter.get("type")
        for parameter in parameters
    )


def _dataset_complete(binding: Mapping[str, Any] | None) -> bool:
    if not binding:
        return False
    return (
        str(binding.get("dataset_family_id", "")).startswith("FAMILY:")
        and str(binding.get("dataset_version_id", "")).startswith("VERSION:")
        and len(str(binding.get("dataset_content_sha256", ""))) == 64
        and len(str(binding.get("session_set_hash", ""))) == 64
        and all(binding.get(field) not in (None, "") for field in ("date_range", "row_count", "instrument_identity", "timezone", "bar_interval"))
    )


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

    embedded_owners = sorted({str(record.get("strategy_or_hypothesis_id") or "") for record in records})
    embedded_owners = [owner for owner in embedded_owners if owner]
    owner_binding = _binding(evidence, "ownership_manifest", ledger_sha256)
    manifest_owners = sorted(set(owner_binding.get("canonical_strategy_ids", []))) if owner_binding else []
    conflicting_owner = bool(owner_binding and manifest_owners != embedded_owners)
    filename_or_directory_only = evidence.get("ownership_basis") in {"FILENAME_ONLY", "DIRECTORY_ONLY"}
    if conflicting_owner:
        ownership_status = "CONFLICTING"
    elif embedded_owners and not filename_or_directory_only:
        ownership_status = "PROVEN_WITH_LIMITATIONS"
    else:
        ownership_status = "UNRESOLVED"

    implementation = _binding(evidence, "implementation_manifest", ledger_sha256)
    parameters = _binding(evidence, "parameter_manifest", ledger_sha256)
    dataset = _binding(evidence, "dataset_manifest", ledger_sha256)
    freeze = _binding(evidence, "freeze_manifest", ledger_sha256)
    temporal_complete = _all_nonempty(records, ("feature_cutoff_ts", "signal_ts", "earliest_entry_ts"))
    causal_ordering = _causal_ordering(records)
    split_manifest = _binding(evidence, "split_manifest", ledger_sha256)
    split_complete = _all_nonempty(records, ("fold_id",)) and bool(split_manifest and split_manifest.get("split_identity"))
    invalidation = _binding(evidence, "historical_invalidation", ledger_sha256)
    contamination = evidence.get("contamination_evidence", {})

    contamination_states = {
        "outcome_contamination_authority": contamination.get("outcome", "UNRESOLVED"),
        "option_price_contamination_authority": contamination.get("option_price", "UNRESOLVED"),
        "tuning_contamination_authority": contamination.get("tuning", "UNRESOLVED"),
        "holdout_contamination_authority": contamination.get("holdout", "UNRESOLVED"),
        "historical_invalidation_authority": "CONFIRMED" if invalidation else "UNRESOLVED",
    }
    confirmed_contamination = any(value == "CONFIRMED" for key, value in contamination_states.items() if key != "historical_invalidation_authority")

    if conflicting_owner or causal_ordering == "INVALID_CAUSAL_ORDERING" or invalidation or confirmed_contamination:
        verdict = "SIGNAL_LEDGER_INVALIDATED"
    elif ownership_status == "UNRESOLVED":
        verdict = "SIGNAL_LEDGER_PROVENANCE_BLOCKED"
    elif not all((implementation, _parameters_complete(parameters), _dataset_complete(dataset), temporal_complete, split_complete, freeze)) or "UNRESOLVED" in contamination_states.values():
        verdict = "SIGNAL_LEDGER_OWNERSHIP_PROVEN_BUT_PROVENANCE_INCOMPLETE"
    else:
        verdict = "SIGNAL_LEDGER_PROVENANCE_ESTABLISHED_WITH_LIMITATIONS"

    result = {
        "schema_version": "signal_ledger_provenance_v1",
        **SAFETY_FLAGS,
        "ledger": {
            "canonical_signal_ledger_id": f"{ledger_sha256}:{len(records)}",
            "physical_sha256": ledger_sha256,
            "row_count": len(records),
        },
        "ownership": {
            "ownership_status": ownership_status,
            "canonical_strategy_id": None,
            "canonical_strategy_ids": embedded_owners,
            "aliases": [],
            "ownership_evidence": ["HASH_PROTECTED_EMBEDDED_ROW_OWNER"] if embedded_owners else [],
            "ownership_reason_codes": ["AGGREGATE_MULTI_OWNER_BLOCKER_LEDGER", "NOT_EXECUTED_SIGNALS"],
        },
        "implementation": {
            "implementation_authority": "PROVEN_FOR_PLACEHOLDER_GENERATOR_ONLY" if implementation else "UNRESOLVED",
            "ledger_proven_implementation_commit": implementation.get("commit_sha") if implementation else None,
            "ledger_proven_implementation_path": implementation.get("path") if implementation else None,
            "ledger_proven_implementation_blob_hash": implementation.get("git_blob_sha") if implementation else None,
            "generator_sha256": implementation.get("content_sha256") if implementation else None,
            "candidate_current_implementation_hash": evidence.get("candidate_current_implementation_hash"),
        },
        "parameters": {
            "parameter_authority": "PROVEN" if _parameters_complete(parameters) else "UNRESOLVED",
            "parameter_manifest": parameters.get("parameters") if parameters else None,
            "parameter_manifest_sha256": semantic_sha256(parameters) if parameters else None,
            "missing_parameter_fields": [] if _parameters_complete(parameters) else ["names", "values", "types", "owner", "ledger_binding"],
        },
        "dataset": {
            "dataset_authority": "PROVEN" if _dataset_complete(dataset) else "UNRESOLVED",
            "dataset_family_id": dataset.get("dataset_family_id") if dataset else None,
            "dataset_version_id": dataset.get("dataset_version_id") if dataset else None,
            "dataset_manifest_sha256": semantic_sha256(dataset) if dataset else None,
            "dataset_content_sha256": dataset.get("dataset_content_sha256") if dataset else None,
            "dataset_binding_evidence": dataset.get("binding_evidence", []) if dataset else [],
        },
        "temporal_split": {
            "temporal_authority": "PROVEN" if temporal_complete and causal_ordering == "CAUSAL_ORDERING_PROVEN" else "UNRESOLVED" if causal_ordering == "UNRESOLVED" else "INVALID",
            "split_authority": "PROVEN" if split_complete else "UNRESOLVED",
            "causal_ordering_result": causal_ordering,
            "fold_identity": sorted({record.get("fold_id") for record in records}) if split_complete else None,
            "split_identity": split_manifest.get("split_identity") if split_complete else None,
        },
        "freeze_contamination": {
            "freeze_authority": "PROVEN" if freeze else "UNRESOLVED",
            **contamination_states,
        },
        "historical_invalidation": dict(invalidation) if invalidation else None,
        "verdict": verdict,
    }
    return result
