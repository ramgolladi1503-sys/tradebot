from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .blockers_priority import blocker_records_as_dicts, build_authority_blockers_priority
from .provenance_evidence import (
    SignalLedgerProvenanceEvidence,
    load_signal_ledger_provenance_evidence,
)
from .signal_authority import assess_signal_ledger_authority
from .strategy_matrix import build_authority_strategy_matrix
from .unresolved_sources import group_unresolved_candidates, reconcile_candidate_membership


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_text(path.read_text(encoding="utf-8"))


def _write_json_with_sidecar(path: Path, payload: Any) -> None:
    path.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
    path.with_suffix(path.suffix + ".sha256").write_text(f"{_sha256_file(path)}  {path.name}\n", encoding="utf-8")


@dataclass(frozen=True)
class AuthorityClosureSnapshot:
    input_bundle: dict[str, Any]
    current_986_breakdown: dict[str, Any]
    physical_candidate_registry: list[dict[str, Any]]
    exact_content_blob_registry: list[dict[str, Any]]
    exact_duplicate_groups: list[dict[str, Any]]
    dataset_partition_registry: list[dict[str, Any]]
    logical_dataset_family_registry: list[dict[str, Any]]
    dataset_version_registry: list[dict[str, Any]]
    semantic_duplicate_groups: list[dict[str, Any]]
    canonical_signal_ledger_registry: list[dict[str, Any]]
    canonical_signal_ledger_audit: list[dict[str, Any]]
    aeron7_nifty_f1_dataset_family: list[dict[str, Any]]
    unresolved_candidate_resolution: list[dict[str, Any]]
    truncation_review: list[dict[str, Any]]
    strategy_implementation_inventory: list[dict[str, Any]]
    strategy_alias_registry: list[dict[str, Any]]
    all_strategy_execution_readiness: list[dict[str, Any]]
    census_summary: dict[str, Any]
    dataset_family_summary: dict[str, Any]
    dataset_version_summary: dict[str, Any]
    signal_ledger_summary: dict[str, Any]
    execution_readiness_summary: dict[str, Any]
    determinism: dict[str, Any]
    signal_ledger_provenance: SignalLedgerProvenanceEvidence | None = None


@dataclass(frozen=True)
class AuthorityClosureBuildResult:
    authority_status: str
    input_census_integrity: dict[str, Any]
    dataset_family_count: int
    dataset_version_count: int
    matrix_count: int
    blocked_lane_count: int
    ready_for_causal_execution_lanes: int
    valid_precomputed_signals_lanes: int


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, ""))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _index_by(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = str(row.get(key, ""))
        if not row_id:
            continue
        if row_id in index and index[row_id] != row:
            raise AuthorityClosureReconciliationError(f"duplicate_key_conflict key={key} value={row_id}")
        index[row_id] = row
    return dict(sorted(index.items()))


def _compact_dir(repo_root: Path) -> Path:
    return repo_root / "research" / "option_e2e_recertification_v4" / "all_strategy_source_census_v1"


class AuthorityClosureError(RuntimeError):
    pass


class AuthorityClosureInputError(AuthorityClosureError):
    pass


class AuthorityClosureDeterminismError(AuthorityClosureError):
    pass


class AuthorityClosureReconciliationError(AuthorityClosureError):
    pass


def _semantic_digest(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _read_payload_for_digest(path: Path) -> Any:
    if path.suffix == ".jsonl":
        return _read_jsonl_records(path)
    return _read_json(path)


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise AuthorityClosureInputError(f"json_array_not_list path={path}")
        records: list[dict[str, Any]] = []
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                raise AuthorityClosureInputError(f"json_array_record_not_object path={path} index={index}")
            records.append(item)
        return records
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            entry = line.strip()
            if not entry:
                continue
            try:
                payload = json.loads(entry)
            except json.JSONDecodeError as exc:
                raise AuthorityClosureInputError(f"invalid_jsonl path={path} line={line_no}") from exc
            if not isinstance(payload, dict):
                raise AuthorityClosureInputError(f"jsonl_record_not_object path={path} line={line_no}")
            records.append(payload)
    return records


def _read_json_array_or_object(path: Path) -> Any:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload


def _load_run(run_dir: Path) -> AuthorityClosureSnapshot:
    if not run_dir.exists():
        raise AuthorityClosureInputError(f"missing_full_run_dir path={run_dir}")
    return AuthorityClosureSnapshot(
        input_bundle=dict(_read_json(run_dir / "input_bundle_integrity_independent.json")),
        physical_candidate_registry=_read_jsonl_records(run_dir / "physical_candidate_registry.jsonl"),
        exact_content_blob_registry=_read_jsonl_records(run_dir / "exact_content_blob_registry.jsonl"),
        exact_duplicate_groups=_read_jsonl_records(run_dir / "exact_duplicate_groups.jsonl"),
        dataset_partition_registry=_read_jsonl_records(run_dir / "dataset_partition_registry.jsonl"),
        logical_dataset_family_registry=list(_read_json_array_or_object(run_dir / "logical_dataset_family_registry.json")),
        dataset_version_registry=list(_read_json_array_or_object(run_dir / "dataset_version_registry.json")),
        semantic_duplicate_groups=_read_jsonl_records(run_dir / "semantic_duplicate_groups.jsonl"),
        canonical_signal_ledger_registry=list(_read_json_array_or_object(run_dir / "canonical_signal_ledger_registry.json")),
        canonical_signal_ledger_audit=list(_read_json_array_or_object(run_dir / "canonical_signal_ledger_audit.json")),
        aeron7_nifty_f1_dataset_family=list(_read_json_array_or_object(run_dir / "aeron7_nifty_f1_dataset_family.json")),
        unresolved_candidate_resolution=list(_read_json_array_or_object(run_dir / "unresolved_candidate_resolution.json")),
        truncation_review=list(_read_json_array_or_object(run_dir / "truncation_review.json")),
        strategy_implementation_inventory=list(_read_json_array_or_object(run_dir / "strategy_implementation_inventory.json")),
        strategy_alias_registry=list(_read_json_array_or_object(run_dir / "strategy_alias_registry.json")),
        all_strategy_execution_readiness=list(_read_json_array_or_object(run_dir / "all_strategy_execution_readiness.json")),
        determinism=dict(_read_json(run_dir / "determinism.json")),
        current_986_breakdown=dict(_read_json(run_dir / "current_986_breakdown.json")),
        census_summary=dict(_read_json(run_dir / "census_summary.json")),
        dataset_family_summary={},
        dataset_version_summary={},
        signal_ledger_summary={},
        execution_readiness_summary={},
    )


def load_authority_closure_inputs(
    *,
    full_run_a: Path,
    full_run_b: Path,
    signal_ledger_provenance_dir: Path,
    compact_census_dir: Path | None = None,
) -> AuthorityClosureSnapshot:
    first = _load_run(full_run_a)
    _load_run(full_run_b)
    signal_ledger_provenance = load_signal_ledger_provenance_evidence(signal_ledger_provenance_dir)
    required_names = (
        "input_bundle_integrity_independent.json",
        "current_986_breakdown.json",
        "physical_candidate_registry.jsonl",
        "exact_content_blob_registry.jsonl",
        "exact_duplicate_groups.jsonl",
        "dataset_partition_registry.jsonl",
        "logical_dataset_family_registry.json",
        "dataset_version_registry.json",
        "semantic_duplicate_groups.jsonl",
        "canonical_signal_ledger_registry.json",
        "canonical_signal_ledger_audit.json",
        "aeron7_nifty_f1_dataset_family.json",
        "unresolved_candidate_resolution.json",
        "truncation_review.json",
        "strategy_implementation_inventory.json",
        "strategy_alias_registry.json",
        "all_strategy_execution_readiness.json",
        "census_summary.json",
        "determinism.json",
    )
    for name in required_names:
        if _semantic_digest(_read_payload_for_digest(full_run_a / name)) != _semantic_digest(_read_payload_for_digest(full_run_b / name)):
            raise AuthorityClosureDeterminismError(f"semantic_mismatch path={name}")
    if compact_census_dir is not None:
        census_summary = dict(_read_json(compact_census_dir / "census_summary.json"))
        if "raw_candidates" in census_summary and "raw_candidates" in first.census_summary and census_summary["raw_candidates"] != first.census_summary["raw_candidates"]:
            raise AuthorityClosureReconciliationError("compact_census_reconciliation_failed")
        dataset_family_summary = dict(_read_json(compact_census_dir / "dataset_family_summary.json"))
        dataset_version_summary = dict(_read_json(compact_census_dir / "dataset_version_summary.json"))
        signal_ledger_summary = dict(_read_json(compact_census_dir / "signal_ledger_summary.json"))
        execution_readiness_summary = dict(_read_json(compact_census_dir / "execution_readiness_summary.json"))
    else:
        census_summary = dict(first.census_summary)
        dataset_family_summary = {}
        dataset_version_summary = {}
        signal_ledger_summary = {}
        execution_readiness_summary = {}
    return AuthorityClosureSnapshot(
        input_bundle=first.input_bundle,
        physical_candidate_registry=first.physical_candidate_registry,
        exact_content_blob_registry=first.exact_content_blob_registry,
        exact_duplicate_groups=first.exact_duplicate_groups,
        dataset_partition_registry=first.dataset_partition_registry,
        logical_dataset_family_registry=first.logical_dataset_family_registry,
        dataset_version_registry=first.dataset_version_registry,
        semantic_duplicate_groups=first.semantic_duplicate_groups,
        canonical_signal_ledger_registry=first.canonical_signal_ledger_registry,
        canonical_signal_ledger_audit=first.canonical_signal_ledger_audit,
        aeron7_nifty_f1_dataset_family=first.aeron7_nifty_f1_dataset_family,
        unresolved_candidate_resolution=first.unresolved_candidate_resolution,
        truncation_review=first.truncation_review,
        strategy_implementation_inventory=first.strategy_implementation_inventory,
        strategy_alias_registry=first.strategy_alias_registry,
        all_strategy_execution_readiness=first.all_strategy_execution_readiness,
        census_summary=census_summary,
        dataset_family_summary=dataset_family_summary,
        dataset_version_summary=dataset_version_summary,
        signal_ledger_summary=signal_ledger_summary,
        execution_readiness_summary=execution_readiness_summary,
        determinism=first.determinism,
        current_986_breakdown=first.current_986_breakdown,
        signal_ledger_provenance=signal_ledger_provenance,
    )


def _family_authority_status(row: dict[str, Any]) -> tuple[str, str]:
    identity = str(row.get("identity_status", ""))
    if identity == "CANONICAL":
        return "CANONICAL_FAMILY_AUTHORITY_PROVEN", "canonical_family_authority_proven"
    if identity == "PROVISIONAL":
        return "FAMILY_USABLE_WITH_LIMITATIONS", "provisional_family_usable_with_limitations"
    if identity == "IDENTITY_INCOMPLETE":
        return "FAMILY_IDENTITY_INCOMPLETE", "identity_status_is_incomplete"
    if not row.get("session_set_hash"):
        return "FAMILY_SOURCE_PROVENANCE_INCOMPLETE", "session_set_hash_missing"
    if str(row.get("dataset_family_id", "")).startswith("FAMILY:NIFTY_F1"):
        return "FAMILY_REQUIRES_TARGETED_INSPECTION", "nifty_f1_requires_targeted_inspection"
    return "FAMILY_USABLE_WITH_LIMITATIONS", "no_canonical_family_authority"


def load_all_strategy_authority_closure(
    repo_root: Path,
    *,
    full_run_a: Path,
    full_run_b: Path,
    compact_census_dir: Path | None = None,
) -> AuthorityClosureSnapshot:
    provenance_dir = (
        repo_root
        / "research"
        / "option_e2e_recertification_v4"
        / "signal_ledger_provenance_v1"
    )
    return load_authority_closure_inputs(
        full_run_a=full_run_a,
        full_run_b=full_run_b,
        signal_ledger_provenance_dir=provenance_dir,
        compact_census_dir=compact_census_dir,
    )


def _dataset_family_reviews(snapshot: AuthorityClosureSnapshot) -> list[dict[str, Any]]:
    family_by_id = _index_by(snapshot.logical_dataset_family_registry, "dataset_family_id")
    partitions_by_family: dict[str, list[dict[str, Any]]] = {}
    for partition in snapshot.dataset_partition_registry:
        partitions_by_family.setdefault(str(partition.get("dataset_family_id", "")), []).append(partition)
    versions_by_family: dict[str, list[dict[str, Any]]] = {}
    for version in snapshot.dataset_version_registry:
        versions_by_family.setdefault(str(version.get("dataset_family_id", "")), []).append(version)
    candidates_by_id = _index_by(snapshot.physical_candidate_registry, "candidate_id")
    blobs_by_hash: dict[str, list[dict[str, Any]]] = {}
    for blob in snapshot.exact_content_blob_registry:
        physical_hash = str(blob.get("physical_sha256", ""))
        if physical_hash:
            blobs_by_hash.setdefault(physical_hash, []).append(blob)
    duplicate_groups_by_hash: dict[str, list[dict[str, Any]]] = {}
    for group in snapshot.exact_duplicate_groups:
        content_hash = str(group.get("physical_sha256") or group.get("sha256") or "")
        if content_hash:
            duplicate_groups_by_hash.setdefault(content_hash, []).append(group)
    families = []
    for family_id, row in family_by_id.items():
        partitions = sorted(partitions_by_family.get(family_id, []), key=lambda item: str(item.get("partition_id", "")))
        versions = sorted(versions_by_family.get(family_id, []), key=lambda item: str(item.get("dataset_version_id", "")))
        physical_hashes = sorted({str(item.get("blob_id")) for item in partitions if item.get("blob_id")})
        blobs = sorted(
            (blob for physical_hash in physical_hashes for blob in blobs_by_hash.get(physical_hash, [])),
            key=lambda item: str(item.get("blob_id", "")),
        )
        candidate_ids = sorted(
            {
                str(candidate_id)
                for blob in blobs
                for candidate_id in blob.get("candidate_ids", [])
                if str(candidate_id) in candidates_by_id
            }
        )
        partition_ids = sorted({str(item["partition_id"]) for item in partitions})
        version_ids = sorted({str(item["dataset_version_id"]) for item in versions})
        blob_ids = sorted({str(item["blob_id"]) for item in blobs})
        duplicate_content_hashes = sorted(
            physical_hash for physical_hash in physical_hashes if duplicate_groups_by_hash.get(physical_hash)
        )
        first_values = sorted(str(item["first_timestamp"]) for item in partitions if item.get("first_timestamp"))
        last_values = sorted(str(item["last_timestamp"]) for item in partitions if item.get("last_timestamp"))
        session_hashes = sorted({str(item["session_set_hash"]) for item in partitions if item.get("session_set_hash")})
        limitations = {
            str(limitation)
            for version in versions
            for limitation in version.get("limitations", [])
        }
        limitations.update(
            str(limitation)
            for partition in partitions
            for limitation in partition.get("quality_limitations", [])
        )
        limitations.update(
            str(limitation)
            for candidate_id in candidate_ids
            for limitation in candidates_by_id[candidate_id].get("quality_limitations", [])
        )
        if str(row.get("identity_status")) != "CANONICAL":
            limitations.add("family_identity_not_canonical")
        authority_status, authority_reason = _family_authority_status(row)
        families.append(
            {
                "dataset_family_id": family_id,
                "source_record_hash": hashlib.sha256(_canonical_json(row).encode("utf-8")).hexdigest(),
                "instrument": row.get("instrument"),
                "instrument_type": row.get("instrument_type"),
                "venue": row.get("market"),
                "bar_interval": row.get("bar_interval"),
                "timezone": row.get("timezone"),
                "source_owner": row.get("source_owner"),
                "generation_method": row.get("generation_method"),
                "identity_status": row.get("identity_status"),
                "partition_ids": partition_ids,
                "version_ids": version_ids,
                "partition_count": len(partition_ids),
                "version_count": len(version_ids),
                "physical_candidate_ids": candidate_ids,
                "physical_file_count": len(candidate_ids),
                "exact_blob_ids": blob_ids,
                "exact_copy_count": sum(int(item.get("copy_count", 0)) for item in blobs),
                "first_timestamp": first_values[0] if first_values else None,
                "last_timestamp": last_values[-1] if last_values else None,
                "date_range": [first_values[0] if first_values else None, last_values[-1] if last_values else None],
                "session_count": len(session_hashes) if session_hashes else None,
                "session_set_hash": _semantic_digest(session_hashes) if session_hashes else None,
                "provenance_status": "PROVEN" if row.get("identity_status") == "PROVISIONAL" else "PARTIALLY_PROVEN",
                "temporal_semantics_status": "UNKNOWN" if row.get("bar_interval") == "unknown" else "PROVEN",
                "roll_methodology_status": "NOT_APPLICABLE" if row.get("instrument_type") == "spot" else "UNRESOLVED",
                "volume_semantics_status": "UNRESOLVED",
                "authority_status": authority_status,
                "authority_reason_codes": [authority_reason],
                "quality_limitations": sorted(limitations),
                "supporting_evidence": {
                    "partition_ids": partition_ids,
                    "version_ids": version_ids,
                    "physical_candidate_ids": candidate_ids,
                    "physical_hashes": physical_hashes,
                    "exact_blob_ids": blob_ids,
                    "exact_duplicate_content_hashes": duplicate_content_hashes,
                    "identity_status": row.get("identity_status"),
                    "generation_method": row.get("generation_method"),
                },
            }
        )
    return families


def _dataset_version_decisions(snapshot: AuthorityClosureSnapshot) -> list[dict[str, Any]]:
    decisions = []
    version_by_id = _index_by(snapshot.dataset_version_registry, "dataset_version_id")
    for version_id, row in version_by_id.items():
        status = str(row.get("status", ""))
        evidence_fields = {
            "dataset_family_id": row.get("dataset_family_id"),
            "partition_ids": sorted(str(item) for item in row.get("partition_ids", [])),
            "partition_manifest_hash": row.get("partition_manifest_hash"),
            "schema_hash": row.get("schema_hash"),
            "session_set_hash": row.get("session_set_hash"),
            "source_provenance": row.get("source_provenance"),
            "creation_method": row.get("creation_method"),
            "quality_metrics": row.get("quality_metrics"),
            "limitations": sorted(str(item) for item in row.get("limitations", [])),
        }
        reasons = []
        for field in ("dataset_family_id", "partition_manifest_hash", "schema_hash", "session_set_hash", "source_provenance"):
            if not evidence_fields[field]:
                reasons.append(f"{field}_missing")
        if not evidence_fields["partition_ids"]:
            reasons.append("partition_ids_missing")
        reasons.extend(f"quality_limitation_{item}" for item in evidence_fields["limitations"])
        if status != "USABLE_WITH_LIMITATIONS":
            reasons.append(f"original_census_status_{status.lower() or 'unknown'}")
        authority_decision = (
            "KEEP_USABLE_WITH_LIMITATIONS"
            if status == "USABLE_WITH_LIMITATIONS" and not any(item.endswith("_missing") for item in reasons)
            else "DOWNGRADE_TO_UNRESOLVED"
        )
        decisions.append(
            {
                "dataset_version_id": version_id,
                "dataset_family_id": row["dataset_family_id"],
                "partition_ids": list(row.get("partition_ids", [])),
                "partition_manifest_hash": row.get("partition_manifest_hash"),
                "schema_hash": row.get("schema_hash"),
                "session_set_hash": row.get("session_set_hash"),
                "source_provenance": row.get("source_provenance"),
                "creation_method": row.get("creation_method"),
                "quality_metrics": row.get("quality_metrics"),
                "limitations": list(row.get("limitations", [])),
                "source_record_hash": hashlib.sha256(_canonical_json(row).encode("utf-8")).hexdigest(),
                "original_census_status": status,
                "authority_decision": authority_decision,
                "authority_reason_codes": sorted(reasons),
                "evaluated_evidence_fields": evidence_fields,
                "supporting_evidence": {"dataset_version_id": version_id, "status": status, **evidence_fields},
                "allowed_strategy_categories": ["research_only"],
                "prohibited_strategy_categories": ["live", "paper", "execution"],
            }
        )
    return decisions


def _signal_ledger_review(snapshot: AuthorityClosureSnapshot) -> dict[str, Any]:
    provenance = snapshot.signal_ledger_provenance
    if provenance is None:
        raise AuthorityClosureInputError("signal_ledger_provenance_evidence_required")
    if len(snapshot.canonical_signal_ledger_registry) != 1 or len(snapshot.canonical_signal_ledger_audit) != 1:
        raise AuthorityClosureReconciliationError("exactly_one_signal_ledger_candidate_required")
    audit = snapshot.canonical_signal_ledger_audit[0]
    registry = snapshot.canonical_signal_ledger_registry[0]
    registry_hash = registry.get("sha256") or registry.get("physical_sha256")
    audit_hash = audit.get("physical_sha256") or audit.get("sha256")
    if registry_hash != audit_hash or audit_hash != provenance.physical_hash:
        raise AuthorityClosureReconciliationError("signal_ledger_hash_provenance_mismatch")
    if registry.get("row_count") != audit.get("row_count") or audit.get("row_count") != provenance.row_count:
        raise AuthorityClosureReconciliationError("signal_ledger_row_count_provenance_mismatch")
    if registry.get("canonical_signal_ledger_id") != audit.get("canonical_signal_ledger_id"):
        raise AuthorityClosureReconciliationError("signal_ledger_candidate_id_mismatch")
    if audit.get("strategy_or_hypothesis_id") is not None or audit.get("canonical_strategy_id") is not None:
        raise AuthorityClosureReconciliationError("multi_owner_placeholder_cannot_have_canonical_strategy")

    evidence = {
        **registry,
        **audit,
        "physical_hash": audit_hash,
        "implementation_hash": audit.get("implementation_commit"),
        "dataset_hash": audit.get("dataset_source_hash"),
        "dataset_authority": "UNPROVEN",
        "split_identity": None,
        "outcome_or_pnl_contamination": None,
        "option_price_contamination": None,
        "tuned_after_outcome": None,
        "holdout_contamination": audit.get("is_holdout"),
        "historically_invalidated": None,
        **provenance.assessment_fields(),
    }
    assessment = assess_signal_ledger_authority(evidence)
    if assessment["authority_conclusion"] != "INVALIDATED_HISTORICAL_EVIDENCE":
        raise AuthorityClosureReconciliationError("derived_signal_ledger_invalidation_not_reconciled")
    if assessment["authority_reason_codes"] != ["derived_through_proven_invalidated_generator_binding"]:
        raise AuthorityClosureReconciliationError("derived_signal_ledger_reason_not_reconciled")
    return {
        "signal_ledger_id": registry.get("canonical_signal_ledger_id"),
        "candidate_id": audit.get("canonical_signal_ledger_id"),
        "path": audit.get("exact_path"),
        "physical_hash": provenance.physical_hash,
        "canonical_strategy_id": None,
        "strategy_authority": "UNRESOLVED",
        "aliases": [],
        "row_count": audit.get("row_count"),
        "artifact_kind": provenance.artifact_kind,
        "session_count": audit.get("session_count"),
        "signal_id_uniqueness": audit.get("signal_id_unique"),
        "feature_cutoff_timestamp_status": "UNRESOLVED" if audit.get("feature_cutoff_ts") is None else "PROVEN",
        "signal_timestamp_status": "UNRESOLVED" if audit.get("signal_ts") is None else "PROVEN",
        "earliest_legal_entry_timestamp_status": "UNRESOLVED" if audit.get("earliest_entry_ts") is None else "PROVEN",
        "causal_ordering_status": "UNRESOLVED",
        "implementation_path": None,
        "candidate_implementation_hash": None,
        "ledger_proven_implementation_hash": audit.get("implementation_commit"),
        "implementation_hash": audit.get("implementation_commit"),
        "implementation_authority": "UNRESOLVED",
        "parameter_owner": None,
        "parameter_hash": audit.get("parameter_hash"),
        "parameter_authority": "UNRESOLVED",
        "dataset_family_id": None,
        "dataset_version_id": None,
        "candidate_dataset_hash": None,
        "ledger_proven_dataset_hash": audit.get("dataset_source_hash"),
        "dataset_hash": audit.get("dataset_source_hash"),
        "dataset_authority": "BLOCKED",
        "fold_identity": audit.get("fold_identity"),
        "development_validation_holdout_identity": audit.get("is_holdout"),
        "split_authority": "UNRESOLVED",
        "pre_outcome_freeze_provenance": audit.get("pre_outcome_freeze_provenance"),
        "generation_command": "loaded from canonical signal ledger registry",
        "outcome_or_pnl_contamination": "UNRESOLVED",
        "option_price_contamination": "UNRESOLVED",
        "historical_invalidation_status": "INVALIDATED_HISTORICAL_EVIDENCE",
        "direct_ledger_invalidation_authority": provenance.direct_ledger_invalidation_authority,
        "implementation_invalidation_authority": provenance.implementation_invalidation_authority,
        "derived_ledger_invalidation_authority": provenance.derived_ledger_invalidation_authority,
        "derived_invalidation_reason_code": provenance.derived_invalidation_reason_code,
        "invalidation_basis": "PROVEN_INVALIDATED_GENERATOR_TO_EXACT_LEDGER_BYTE_BINDING",
        "generator_output_binding_status": provenance.generator_output_binding_status,
        "primary_oracle_agreement": provenance.primary_oracle_agreement,
        "introduction_commit": provenance.introduction_commit,
        "introduction_status": provenance.introduction_status,
        "authority_conclusion": assessment["authority_conclusion"],
        "field_authority": assessment["field_authority"],
        "authority_reason_codes": assessment["authority_reason_codes"],
        "assessed_evidence": evidence,
        "supporting_evidence": {
            "registry": registry,
            "audit": audit,
            "strategy_ownership_evidence": None,
            "selected_version": {},
            "immutable_provenance_physical_sha256": provenance.source_physical_sha256,
            "immutable_provenance_semantic_sha256": provenance.source_semantic_sha256,
        },
        "signal_ledger_candidate_count": 1,
        "canonical_signal_ledger_count": 0,
        "usable_signal_ledger_count": 0,
        "invalidated_signal_ledger_count": 1,
        "replacement_signal_ledger_required": True,
        "insufficient_provenance_ledgers": 0,
        "upstream_insufficient_provenance_ledgers": snapshot.signal_ledger_summary["insufficient_provenance_ledgers"],
        "valid_signal_ledger_with_limitations_count": 0,
        "canonical_signal_ledger_registry": snapshot.canonical_signal_ledger_registry,
        "canonical_signal_ledger_audit": snapshot.canonical_signal_ledger_audit,
        "research_only": True,
        "read_only": True,
        "allowed_for_live_execution": False,
        "broker_api_called": False,
        "is_order_action": False,
    }


def _unresolved_source_review(snapshot: AuthorityClosureSnapshot) -> dict[str, Any]:
    resolution_items = [
        dict(item)
        for record in snapshot.unresolved_candidate_resolution
        for item in record.get("items", [])
    ]
    physical_by_id = _index_by(snapshot.physical_candidate_registry, "candidate_id")
    candidates = []
    for item in resolution_items:
        physical = physical_by_id.get(str(item.get("candidate_id")), {})
        normalized = dict(item)
        if not normalized.get("root_id") or not normalized.get("relative_path"):
            original_id = str(normalized.get("candidate_id") or "unknown")
            normalized.update(
                root_id="FIXTURE",
                relative_path=original_id,
                candidate_id=f"FIXTURE:{original_id}",
            )
        candidates.append({**normalized, "sha256": physical.get("physical_sha256") or physical.get("sha256")})
    groups = group_unresolved_candidates(candidates)
    reconciliation = reconcile_candidate_membership(candidates, groups)
    return {
        "authority_status": "BLOCKED",
        "unresolved_candidate_count": snapshot.input_bundle["unresolved_candidate_count"],
        "material_truncated_roots": snapshot.census_summary["material_truncated_roots"],
        "unresolved_candidate_resolution": snapshot.unresolved_candidate_resolution,
        "truncation_review": snapshot.truncation_review,
        "reason": "candidate_search_remains_truncated_and_unresolved",
        "provenance_status": "UNKNOWN",
        "remaining_blockers": ["SOURCE_SEARCH_INCOMPLETE", "DECLARED_BLIND_SPOT"],
        "raw_candidate_count": len(reconciliation.input_candidate_ids),
        "unique_source_count": reconciliation.source_count,
        "duplicate_candidate_count": len(reconciliation.input_candidate_ids) - reconciliation.source_count,
        "source_groups": [
            {
                "source_id": group.source_id,
                "disposition": group.disposition.value,
                "sha256": group.sha256,
                "candidate_ids": list(group.candidate_ids),
            }
            for group in groups
        ],
        "research_only": True,
        "read_only": True,
        "allowed_for_live_execution": False,
        "broker_api_called": False,
        "is_order_action": False,
    }


def _aeron7_review(snapshot: AuthorityClosureSnapshot) -> dict[str, Any]:
    return {
        "authority_status": "BLOCKED_WITH_LIMITATIONS",
        "dataset_family": snapshot.aeron7_nifty_f1_dataset_family,
        "dataset_family_id": snapshot.aeron7_nifty_f1_dataset_family[0]["dataset_family_id"],
        "dataset_version_count": snapshot.census_summary["dataset_version_count"],
        "usable_with_limitations_version_count": snapshot.dataset_version_summary["usable_with_limitations_version_count"],
        "reason": "aeron7_family_is_represented_but_not_authoritative_for_execution",
        "evidence": {"logical_dataset_families": snapshot.census_summary["logical_dataset_family_count"]},
    }


def build_all_strategy_authority_closure(*, snapshot: AuthorityClosureSnapshot, output_dir: Path) -> AuthorityClosureBuildResult:
    families = _dataset_family_reviews(snapshot)
    versions = _dataset_version_decisions(snapshot)
    version_by_id = _index_by(snapshot.dataset_version_registry, "dataset_version_id")
    signal_review = _signal_ledger_review(snapshot)
    unresolved_review = _unresolved_source_review(snapshot)
    signal_assessments = []
    if signal_review.get("canonical_strategy_id") and signal_review.get("signal_ledger_id"):
        signal_assessments.append(
            {
                "canonical_strategy_id": signal_review["canonical_strategy_id"],
                "canonical_signal_ledger_id": signal_review["signal_ledger_id"],
                "authority_conclusion": signal_review["authority_conclusion"],
            }
        )
    matrix = build_authority_strategy_matrix(
        strategy_implementation_inventory=snapshot.strategy_implementation_inventory,
        strategy_alias_registry=snapshot.strategy_alias_registry,
        all_strategy_execution_readiness=snapshot.all_strategy_execution_readiness,
        signal_ledger_assessments=signal_assessments,
    )
    invalidated_ledger_id = signal_review["signal_ledger_id"]
    assigned_lanes = sorted(
        row["canonical_strategy_id"]
        for row in matrix
        if row.get("selected_canonical_signal_ledger") == invalidated_ledger_id
    )
    if assigned_lanes:
        raise AuthorityClosureReconciliationError(
            f"invalidated_multi_owner_ledger_assigned lanes={','.join(assigned_lanes)}"
        )
    for row in matrix:
        selected_version = row.get("selected_canonical_dataset")
        version = version_by_id.get(str(selected_version), {})
        upstream_readiness_blocker = str(row.pop("remaining_blocker", None) or "AUTHORITY_EVIDENCE_INCOMPLETE")
        row.update(
            {
                "strategy_vs_hypothesis_vs_filter": "FILTER" if row["lane_kind"] == "NO_TRADE_FILTER" else "STRATEGY",
                "parameter_hash": _semantic_digest(row.get("resolved_required_parameters", [])),
                "temporal_contract_authority": "PROVEN" if row.get("temporal_contract") == "CAUSAL_ONLY" else "UNRESOLVED",
                "required_dataset_family_ids": [version["dataset_family_id"]] if version.get("dataset_family_id") else [],
                "required_dataset_version_ids": [selected_version] if selected_version and version else [],
                "dataset_authority": version.get("status", "UNRESOLVED"),
                "signal_ledger_ids": [row["selected_canonical_signal_ledger"]] if row.get("selected_canonical_signal_ledger") else [],
                "split_fold_identity": {
                    "development_session_count": row.get("development_session_count"),
                    "holdout_session_count": row.get("holdout_session_count"),
                },
                "instrument_identity_authority": "PROVEN_WITH_LIMITATIONS" if selected_version else "UNRESOLVED",
                "option_data_dependency": row.get("option_data_requirements"),
                "multi_asset_dependency": row["lane_kind"] == "MULTI_ASSET_STRATEGY",
                "multi_asset_dependency_authority": "UNRESOLVED" if row["lane_kind"] == "MULTI_ASSET_STRATEGY" else "NOT_APPLICABLE",
                "source_search_authority": "UNRESOLVED" if unresolved_review["unresolved_candidate_count"] else "PROVEN",
                "historical_invalidation": bool(row.get("invalidated_evidence")),
                "upstream_readiness_blocker": upstream_readiness_blocker,
                "overall_authority_status": row.get("authority_status"),
                "next_minimum_evidence_action": row.get("recommended_next_action"),
                "supporting_evidence": {
                    "inventory_status": row.get("inventory_status"),
                    "selected_dataset": selected_version,
                    "selected_signal_ledger": row.get("selected_canonical_signal_ledger"),
                },
            }
        )
    blocker_result = build_authority_blockers_priority(
        matrix,
        known_family_ids=(row["dataset_family_id"] for row in families),
        known_version_ids=(row["dataset_version_id"] for row in versions),
        known_signal_ledger_ids=(
            str(row["canonical_signal_ledger_id"])
            for row in snapshot.canonical_signal_ledger_registry
            if row.get("canonical_signal_ledger_id")
        ),
    )
    blocker_rows = blocker_records_as_dicts(blocker_result)
    affected_lane_ids = sorted(
        {
            lane_id
            for blocker in blocker_rows
            for lane_id in blocker.get("affected_strategy_ids", [])
        }
    )
    executable_lane_count = sum(row.get("execution_eligible") is True for row in matrix)
    valid_precomputed_lane_count = sum(
        row.get("signal_authority")
        in {"CANONICAL_PRE_OUTCOME_SIGNAL_LEDGER", "VALID_PRECOMPUTED_SIGNALS_WITH_LIMITATIONS"}
        for row in matrix
    )
    lane_impact = {
        "evaluated_lane_count": len(matrix),
        "previous_affected_lane_count": 0,
        "new_affected_lane_count": 0,
        "affected_lane_assignments": [],
        "new_executable_lane_count": executable_lane_count,
        "executable_lane_delta": 0,
        "new_valid_precomputed_signal_lane_count": valid_precomputed_lane_count,
        "valid_precomputed_signal_lane_delta": 0,
        "removed_lane_blocker_count": 0,
        "lane_blocker_delta": "NONE",
        "reason": "INVALIDATED_MULTI_OWNER_PLACEHOLDER_WAS_NOT_CANONICALLY_ASSIGNED",
    }
    blocker_delta = {
        "previous_blocker_record_count": len(blocker_rows),
        "new_blocker_record_count": len(blocker_rows),
        "previous_affected_lane_count": len(affected_lane_ids),
        "new_affected_lane_count": len(affected_lane_ids),
        "added_blocker_ids": [],
        "removed_blocker_ids": [],
        "changed_blocker_ids": [],
        "lane_blocker_delta": "NONE",
        "reason": "INVALIDATED_MULTI_OWNER_PLACEHOLDER_WAS_NOT_CANONICALLY_ASSIGNED",
    }
    signal_review["lane_impact_analysis"] = lane_impact
    signal_review["blocker_delta"] = blocker_delta
    blocker_by_id = {row["blocker_id"]: row for row in blocker_rows}
    blocker_ids_by_lane: dict[str, list[str]] = {row["canonical_strategy_id"]: [] for row in matrix}
    for reference in blocker_result.references:
        blocker_ids_by_lane[reference.authority_target].append(reference.blocker_id)
    for row in matrix:
        blocker_ids = sorted(set(blocker_ids_by_lane[row["canonical_strategy_id"]]))
        row["current_blocker_ids"] = blocker_ids
        row["current_blocker_classes"] = sorted({blocker_by_id[item]["blocker_class"] for item in blocker_ids})
        row["component_blocker_count"] = len(blocker_ids)
    priorities = [
        {
            "canonical_strategy_id": priority.canonical_strategy_id,
            "priority": priority.priority_class,
            "priority_class": priority.priority_class,
            "component_completeness": dict(priority.component_completeness),
            "priority_reason_codes": list(priority.priority_reason_codes),
            "blocker_ids": list(priority.remaining_blocker_ids),
            "remaining_blocker_ids": list(priority.remaining_blocker_ids),
            "authority_status": next(row["authority_status"] for row in matrix if row["canonical_strategy_id"] == priority.canonical_strategy_id),
            "upstream_readiness_blocker": next(row["upstream_readiness_blocker"] for row in matrix if row["canonical_strategy_id"] == priority.canonical_strategy_id),
            "next_minimum_evidence_action": priority.next_minimum_action,
            "next_minimum_action": priority.next_minimum_action,
        }
        for priority in blocker_result.priorities
    ]
    priorities.sort(key=lambda row: (row["priority"], row["canonical_strategy_id"]))
    integrity = {
        **snapshot.input_bundle,
        "authority_status": "AUTHORITY_CLOSURE_BLOCKED_WITH_DECLARED_GAPS",
        "dataset_families": len(families),
        "dataset_versions": len(versions),
        "canonical_signal_ledgers": snapshot.census_summary.get("canonical_signal_ledger_count", 0),
        "signal_ledger_candidates": signal_review["signal_ledger_candidate_count"],
        "usable_signal_ledgers": signal_review["usable_signal_ledger_count"],
        "invalidated_signal_ledgers": signal_review["invalidated_signal_ledger_count"],
        "replacement_signal_ledger_required": signal_review["replacement_signal_ledger_required"],
        "strategy_lanes": len(matrix),
        "research_only": True,
        "read_only": True,
        "allowed_for_live_execution": False,
        "broker_api_called": False,
        "is_order_action": False,
    }
    payloads = {
        "input_census_integrity.json": integrity,
        "dataset_family_authority_reviews.json": families,
        "dataset_version_authority_decisions.json": versions,
        "aeron7_nifty_f1_authority_review.json": _aeron7_review(snapshot),
        "unresolved_source_authority_review.json": unresolved_review,
        "signal_ledger_authority_review.json": signal_review,
        "all_strategy_authority_matrix.json": matrix,
        "authority_blocker_ledger.json": blocker_rows,
        "strategy_authority_prioritization.json": priorities,
    }
    alias_payloads = {
        "authority_closure_input_integrity.json": payloads["input_census_integrity.json"],
        "strategy_authority_blocker_ledger.json": payloads["authority_blocker_ledger.json"],
        "authority_closure_priority.json": payloads["strategy_authority_prioritization.json"],
        "authority_closure_summary.json": {
            "authority_status": "BLOCKED_WITH_DECLARED_GAPS",
            "dataset_family_count": len(families),
            "dataset_version_count": len(versions),
            "blocked_lane_count": snapshot.census_summary["blocked_lanes"],
            "ready_for_causal_execution_lanes": snapshot.census_summary["ready_for_causal_execution_lanes"],
            "valid_precomputed_signals_lanes": snapshot.census_summary["valid_precomputed_signals_lanes"],
            "signal_ledger_candidate_count": signal_review["signal_ledger_candidate_count"],
            "canonical_signal_ledger_count": signal_review["canonical_signal_ledger_count"],
            "usable_signal_ledger_count": signal_review["usable_signal_ledger_count"],
            "invalidated_signal_ledger_count": signal_review["invalidated_signal_ledger_count"],
            "replacement_signal_ledger_required": signal_review["replacement_signal_ledger_required"],
            "signal_ledger_authority_conclusion": signal_review["authority_conclusion"],
            "lane_impact_analysis": lane_impact,
            "blocker_delta": blocker_delta,
        },
        "external_evidence_manifest.json": {
            "input_census_integrity": payloads["input_census_integrity.json"],
            "dataset_family_count": len(families),
            "dataset_version_count": len(versions),
            "authority_status": "BLOCKED_WITH_DECLARED_GAPS",
            "signal_ledger_authority_conclusion": signal_review["authority_conclusion"],
            "signal_ledger_physical_sha256": signal_review["physical_hash"],
            "signal_ledger_row_count": signal_review["row_count"],
            "signal_ledger_artifact_kind": signal_review["artifact_kind"],
            "direct_ledger_invalidation_authority": signal_review["direct_ledger_invalidation_authority"],
            "implementation_invalidation_authority": signal_review["implementation_invalidation_authority"],
            "derived_ledger_invalidation_authority": signal_review["derived_ledger_invalidation_authority"],
            "derived_invalidation_reason_code": signal_review["derived_invalidation_reason_code"],
            "canonical_signal_ledger_count": signal_review["canonical_signal_ledger_count"],
            "usable_signal_ledger_count": signal_review["usable_signal_ledger_count"],
            "invalidated_signal_ledger_count": signal_review["invalidated_signal_ledger_count"],
            "replacement_signal_ledger_required": signal_review["replacement_signal_ledger_required"],
            "lane_impact_analysis": lane_impact,
            "blocker_delta": blocker_delta,
            "research_only": True,
            "read_only": True,
            "allowed_for_live_execution": False,
            "broker_api_called": False,
            "is_order_action": False,
        },
        "determinism.json": {
            "schema_version": "all_strategy_authority_closure_v1",
            "semantic_hashes": {name: _semantic_digest(payload) for name, payload in sorted(payloads.items())},
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in payloads.items():
        _write_json_with_sidecar(output_dir / filename, payload)
    for filename, payload in alias_payloads.items():
        _write_json_with_sidecar(output_dir / filename, payload)
    return AuthorityClosureBuildResult(
        authority_status="BLOCKED_WITH_DECLARED_GAPS",
        input_census_integrity=payloads["input_census_integrity.json"],
        dataset_family_count=len(families),
        dataset_version_count=len(versions),
        matrix_count=len(matrix),
        blocked_lane_count=snapshot.census_summary["blocked_lanes"],
        ready_for_causal_execution_lanes=snapshot.census_summary["ready_for_causal_execution_lanes"],
        valid_precomputed_signals_lanes=snapshot.census_summary["valid_precomputed_signals_lanes"],
    )
