from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

CERTIFIED = "ORB_PHASE1_V2_CANDIDATE_LEDGER_CERTIFIED"
NOT_CERTIFIED = "ORB_PHASE1_V2_CANDIDATE_LEDGER_NOT_CERTIFIED"


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _candidate_sort_key(record: dict[str, Any]) -> tuple[str, str, str, str, str]:
    core = record.get("candidate_core") or {}
    return (
        str(core.get("session_date") or ""),
        str(core.get("symbol") or ""),
        str(core.get("proposal_ready_at_iso") or ""),
        str(core.get("direction") or ""),
        str(core.get("setup_id") or ""),
    )


def _semantic_path_is_portable(value: Any) -> bool:
    text = str(value or "")
    return bool(text) and not Path(text).is_absolute() and ".." not in Path(text).parts and text.startswith("runtime/upstox_candidate_replay/")


def audit_candidate_ledger_standalone(candidate_ledger: dict[str, Any], source_manifest: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    records = list(candidate_ledger.get("records") or [])
    source_records = list(source_manifest.get("records") or [])
    source_by_id = {str(record.get("source_record_id")): record for record in source_records}
    source_ids = set(source_by_id)
    complete_provenance = 0
    candidate_id_failures = 0
    source_reference_failures = 0
    causality_failures = 0

    if candidate_ledger.get("source_manifest_version") != "v2":
        failures.append("CANDIDATE_V1_MANIFEST_REFERENCE")
    if candidate_ledger.get("source_manifest_semantic_hash") != source_manifest.get("source_manifest_semantic_hash"):
        failures.append("CANDIDATE_SOURCE_MANIFEST_HASH_MISMATCH")
    if candidate_ledger.get("candidate_count") != len(records):
        failures.append("CANDIDATE_COUNT_MISMATCH")
    if not records:
        failures.append("CANDIDATE_ZERO_COUNT")
    if records != sorted(records, key=_candidate_sort_key):
        failures.append("CANDIDATE_ORDERING_MISMATCH")

    candidate_ids: list[str] = []
    referenced_sources: list[str] = []
    for record in records:
        core = record.get("candidate_core") or {}
        provenance = record.get("source_provenance") or {}
        candidate_ids.append(str(record.get("candidate_id") or ""))
        required_core = {
            "strategy_id",
            "symbol",
            "direction",
            "status",
            "raw_score",
            "entry_trigger",
            "invalid_if",
            "rank_reason",
            "proposal_ready_at_iso",
            "setup_id",
            "history_hash",
            "session_date",
        }
        required_provenance = {
            "source_manifest_version",
            "source_manifest_semantic_hash",
            "source_logical_path",
            "source_actual_sha256",
            "source_session_date",
            "source_symbol",
            "source_record_id",
        }
        if not required_core.issubset(core) or not required_provenance.issubset(provenance):
            failures.append("CANDIDATE_PROVENANCE_INCOMPLETE")
            source_reference_failures += 1
            continue
        complete_provenance += 1
        source_record = source_by_id.get(str(provenance.get("source_record_id")))
        if source_record is None:
            failures.append("CANDIDATE_SOURCE_RECORD_ABSENT")
            source_reference_failures += 1
        else:
            referenced_sources.append(str(provenance.get("source_record_id")))
            if provenance.get("source_actual_sha256") != source_record.get("actual_sha256"):
                failures.append("CANDIDATE_SOURCE_SHA_MISMATCH")
                source_reference_failures += 1
            if provenance.get("source_symbol") != source_record.get("symbol") or provenance.get("source_symbol") != core.get("symbol"):
                failures.append("CANDIDATE_SOURCE_SYMBOL_MISMATCH")
                source_reference_failures += 1
            if provenance.get("source_session_date") != source_record.get("session_date") or provenance.get("source_session_date") != core.get("session_date"):
                failures.append("CANDIDATE_SOURCE_SESSION_MISMATCH")
                source_reference_failures += 1
            if provenance.get("source_logical_path") != source_record.get("logical_path"):
                failures.append("CANDIDATE_SOURCE_LOGICAL_PATH_MISMATCH")
                source_reference_failures += 1
        if provenance.get("source_manifest_version") != "v2":
            failures.append("CANDIDATE_V1_MANIFEST_REFERENCE")
            source_reference_failures += 1
        if not _semantic_path_is_portable(provenance.get("source_logical_path")):
            failures.append("CANDIDATE_ABSOLUTE_PATH_REFERENCE")
            source_reference_failures += 1
        expected_id = _sha256_bytes(_canonical_json_bytes({"candidate_core": core, "source_provenance": provenance}))
        if expected_id != record.get("candidate_id"):
            failures.append("CANDIDATE_ID_MISMATCH")
            candidate_id_failures += 1
        try:
            proposal_ready = datetime.fromisoformat(str(core.get("proposal_ready_at_iso")))
            if proposal_ready.date().isoformat() != core.get("session_date"):
                failures.append("CANDIDATE_TIMESTAMP_OUTSIDE_SESSION")
                causality_failures += 1
            if (proposal_ready.hour, proposal_ready.minute) < (9, 15) or (proposal_ready.hour, proposal_ready.minute) > (15, 30):
                failures.append("CANDIDATE_ILLEGAL_CAUSAL_READINESS")
                causality_failures += 1
        except Exception:
            failures.append("CANDIDATE_TIMESTAMP_MALFORMED")
            causality_failures += 1

    duplicate_candidate_ids = [candidate_id for candidate_id, count in Counter(candidate_ids).items() if count != 1]
    if duplicate_candidate_ids:
        failures.append("DUPLICATE_CANDIDATE_ID")
        candidate_id_failures += len(duplicate_candidate_ids)
    unselected = sorted(set(referenced_sources) - source_ids)
    if unselected:
        failures.append("CANDIDATE_UNSELECTED_SOURCE_REFERENCE")
        source_reference_failures += len(unselected)

    core_hash = _sha256_bytes(_canonical_json_bytes([record.get("candidate_core") for record in records]))
    provenance_hash = _sha256_bytes(_canonical_json_bytes(records))
    if core_hash != candidate_ledger.get("candidate_core_semantic_hash"):
        failures.append("CANDIDATE_CORE_HASH_MISMATCH")
    if provenance_hash != candidate_ledger.get("candidate_provenance_semantic_hash"):
        failures.append("CANDIDATE_PROVENANCE_HASH_MISMATCH")

    return {
        "verdict": CERTIFIED if not failures else NOT_CERTIFIED,
        "failures": sorted(set(failures)),
        "candidate_count": len(records),
        "candidates_with_complete_source_provenance": complete_provenance,
        "candidate_id_failures": candidate_id_failures,
        "candidate_source_reference_failures": source_reference_failures,
        "causality_failures": causality_failures,
        "candidate_core_semantic_hash_recomputed": core_hash,
        "candidate_provenance_semantic_hash_recomputed": provenance_hash,
        "independence_boundary": "standalone_candidate_oracle_no_generator_imports",
    }
