from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


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


def load_authority_closure_inputs(*, full_run_a: Path, full_run_b: Path, compact_census_dir: Path | None = None) -> AuthorityClosureSnapshot:
    first = _load_run(full_run_a)
    second = _load_run(full_run_b)
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


def load_all_strategy_authority_closure(repo_root: Path, *, full_run_a: Path, full_run_b: Path, compact_census_dir: Path | None = None) -> AuthorityClosureSnapshot:
    del repo_root
    return load_authority_closure_inputs(full_run_a=full_run_a, full_run_b=full_run_b, compact_census_dir=compact_census_dir)


def _dataset_family_reviews(snapshot: AuthorityClosureSnapshot) -> list[dict[str, Any]]:
    family_by_id = _index_by(snapshot.logical_dataset_family_registry, "dataset_family_id")
    families = []
    for family_id, row in family_by_id.items():
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
                "partition_ids": list(row.get("partition_ids", [])),
                "version_ids": list(row.get("versions", [])),
                "partition_count": row.get("partition_count"),
                "version_count": len(row.get("versions", [])),
                "physical_candidate_ids": [],
                "physical_file_count": row.get("physical_file_count"),
                "exact_blob_ids": [],
                "exact_copy_count": row.get("exact_copy_count"),
                "first_timestamp": row.get("first_timestamp"),
                "last_timestamp": row.get("last_timestamp"),
                "date_range": [row.get("first_timestamp"), row.get("last_timestamp")],
                "session_count": row.get("session_count"),
                "session_set_hash": row.get("session_set_hash"),
                "provenance_status": "PROVEN" if row.get("identity_status") == "PROVISIONAL" else "PARTIALLY_PROVEN",
                "temporal_semantics_status": "UNKNOWN" if row.get("bar_interval") == "unknown" else "PROVEN",
                "roll_methodology_status": "NOT_APPLICABLE" if row.get("instrument_type") == "spot" else "UNRESOLVED",
                "volume_semantics_status": "UNRESOLVED",
                "authority_status": authority_status,
                "authority_reason_codes": [authority_reason],
                "quality_limitations": [],
                "supporting_evidence": {
                    "partition_count": row.get("partition_count"),
                    "physical_file_count": row.get("physical_file_count"),
                    "exact_copy_count": row.get("exact_copy_count"),
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
        if status == "CANONICAL_DATASET_VERSION":
            authority_decision = "PROMOTE_TO_CANONICAL_DATASET_VERSION"
        elif status == "USABLE_WITH_LIMITATIONS":
            authority_decision = "KEEP_USABLE_WITH_LIMITATIONS"
        elif status == "EXPLORATORY_ONLY":
            authority_decision = "DOWNGRADE_TO_EXPLORATORY_ONLY"
        elif status == "UNRESOLVED_DATASET_VERSION":
            authority_decision = "DOWNGRADE_TO_UNRESOLVED"
        elif status == "INVALIDATED":
            authority_decision = "INVALIDATE_DATASET_VERSION"
        else:
            authority_decision = "DERIVED_DUPLICATE"
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
                "authority_decision": authority_decision,
                "authority_reason_codes": [f"dataset_version_status_{status.lower() or 'unknown'}"],
                "supporting_evidence": row,
                "allowed_strategy_categories": ["research_only"],
                "prohibited_strategy_categories": ["live", "paper", "execution"],
            }
        )
    return decisions


def _signal_ledger_review(snapshot: AuthorityClosureSnapshot) -> dict[str, Any]:
    audit = snapshot.canonical_signal_ledger_audit[0] if snapshot.canonical_signal_ledger_audit else {}
    registry = snapshot.canonical_signal_ledger_registry[0] if snapshot.canonical_signal_ledger_registry else {}
    return {
        "signal_ledger_id": registry.get("canonical_signal_ledger_id"),
        "candidate_id": audit.get("canonical_signal_ledger_id"),
        "path": audit.get("exact_path"),
        "physical_hash": audit.get("physical_sha256"),
        "canonical_strategy_id": snapshot.strategy_implementation_inventory[0]["canonical_strategy_id"] if snapshot.strategy_implementation_inventory else None,
        "aliases": snapshot.strategy_alias_registry[0]["aliases"] if snapshot.strategy_alias_registry else [],
        "row_count": audit.get("row_count"),
        "session_count": audit.get("session_count"),
        "signal_id_uniqueness": audit.get("signal_id_unique"),
        "feature_cutoff_timestamp_status": "UNRESOLVED" if audit.get("feature_cutoff_ts") is None else "PROVEN",
        "signal_timestamp_status": "UNRESOLVED" if audit.get("signal_ts") is None else "PROVEN",
        "earliest_legal_entry_timestamp_status": "UNRESOLVED" if audit.get("earliest_entry_ts") is None else "PROVEN",
        "causal_ordering_status": "UNRESOLVED",
        "implementation_path": snapshot.strategy_implementation_inventory[0].get("implementation_path") if snapshot.strategy_implementation_inventory else None,
        "implementation_hash": snapshot.strategy_implementation_inventory[0].get("implementation_blob_hash") if snapshot.strategy_implementation_inventory else None,
        "implementation_authority": "UNRESOLVED",
        "parameter_owner": snapshot.strategy_implementation_inventory[0].get("parameter_owner") if snapshot.strategy_implementation_inventory else None,
        "parameter_hash": audit.get("parameter_hash"),
        "parameter_authority": "UNRESOLVED",
        "dataset_family_id": snapshot.all_strategy_execution_readiness[0].get("selected_canonical_dataset") if snapshot.all_strategy_execution_readiness else None,
        "dataset_version_id": snapshot.all_strategy_execution_readiness[0].get("selected_canonical_dataset") if snapshot.all_strategy_execution_readiness else None,
        "dataset_hash": snapshot.census_summary.get("input_bundle", {}).get("candidate_inventory_sha256"),
        "dataset_authority": "BLOCKED",
        "fold_identity": audit.get("fold_identity"),
        "development_validation_holdout_identity": audit.get("is_holdout"),
        "split_authority": "UNRESOLVED",
        "pre_outcome_freeze_provenance": audit.get("pre_outcome_freeze_provenance"),
        "generation_command": "loaded from canonical signal ledger registry",
        "outcome_or_pnl_contamination": "UNRESOLVED",
        "option_price_contamination": "UNRESOLVED",
        "historical_invalidation_status": registry.get("status"),
        "authority_conclusion": "INSUFFICIENT_PROVENANCE" if registry.get("status") == "INSUFFICIENT_PROVENANCE" else "INVALID_SIGNAL_LEDGER",
        "authority_reason_codes": ["no_signal_ledger_has_canonical_provenance"],
        "supporting_evidence": {"registry": registry, "audit": audit},
        "canonical_signal_ledger_count": snapshot.signal_ledger_summary["canonical_signal_ledger_count"],
        "insufficient_provenance_ledgers": snapshot.signal_ledger_summary["insufficient_provenance_ledgers"],
        "valid_signal_ledger_with_limitations_count": snapshot.signal_ledger_summary["valid_signal_ledger_with_limitations_count"],
        "canonical_signal_ledger_registry": snapshot.canonical_signal_ledger_registry,
        "canonical_signal_ledger_audit": snapshot.canonical_signal_ledger_audit,
    }


def _unresolved_source_review(snapshot: AuthorityClosureSnapshot) -> dict[str, Any]:
    return {
        "authority_status": "BLOCKED",
        "unresolved_candidate_count": snapshot.input_bundle["unresolved_candidate_count"],
        "material_truncated_roots": snapshot.census_summary["material_truncated_roots"],
        "unresolved_candidate_resolution": snapshot.unresolved_candidate_resolution,
        "truncation_review": snapshot.truncation_review,
        "reason": "candidate_search_remains_truncated_and_unresolved",
        "provenance_status": "UNKNOWN",
        "remaining_blockers": ["SOURCE_SEARCH_INCOMPLETE", "DECLARED_BLIND_SPOT"],
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


def _authority_matrix(snapshot: AuthorityClosureSnapshot, families: list[dict[str, Any]], versions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for family in families:
        rows.append(
            {
                "authority_target": family["dataset_family_id"],
                "authority_kind": "dataset_family",
                "authority_status": family["authority_status"],
                "blocker": family["authority_reason_codes"][0],
            }
        )
    for row in snapshot.strategy_implementation_inventory:
        readiness = next(item for item in snapshot.all_strategy_execution_readiness if item["canonical_strategy_id"] == row["canonical_strategy_id"])
        rows.append(
            {
                "authority_target": row["canonical_strategy_id"],
                "authority_kind": "strategy_hypothesis",
                "authority_status": readiness["status"],
                "blocker": readiness["remaining_blocker"],
            }
        )
    rows.append(
        {
            "authority_target": "canonical_signal_ledgers",
            "authority_kind": "signal_ledger",
            "authority_status": snapshot.signal_ledger_summary["canonical_signal_ledger_count"] and "PROVEN" or "BLOCKED",
            "blocker": "insufficient_provenance",
        }
    )
    rows.append(
        {
            "authority_target": "unresolved_sources",
            "authority_kind": "source_search",
            "authority_status": "BLOCKED",
            "blocker": "truncated_search_bundle",
        }
    )
    rows.append(
        {
            "authority_target": "strategy_execution",
            "authority_kind": "execution_readiness",
            "authority_status": "BLOCKED",
            "blocker": "no_ready_for_causal_execution_lanes",
        }
    )
    assert versions
    return rows


def _blocker_ledger(snapshot: AuthorityClosureSnapshot) -> list[dict[str, Any]]:
    blockers = snapshot.execution_readiness_summary["blocked_lanes_by_blocker_class"]
    return [
        {"blocker_class": name, "blocked_lane_count": count, "authority_status": "BLOCKED"}
        for name, count in sorted(blockers.items())
    ]


def _strategy_prioritization(snapshot: AuthorityClosureSnapshot) -> list[dict[str, Any]]:
    ranking = []
    for item in snapshot.all_strategy_execution_readiness:
        priority = 1 if item["remaining_blocker"] == "INSUFFICIENT_SIGNAL_PROVENANCE" else 2 if item["remaining_blocker"] == "SOURCE_SEARCH_INCOMPLETE" else 3
        ranking.append(
            {
                "canonical_strategy_id": item["canonical_strategy_id"],
                "priority": priority,
                "authority_status": item["status"],
                "remaining_blocker": item["remaining_blocker"],
                "selected_canonical_dataset": item["selected_canonical_dataset"],
                "selected_canonical_signal_ledger": item["selected_canonical_signal_ledger"],
            }
        )
    return sorted(ranking, key=lambda row: (row["priority"], row["canonical_strategy_id"]))


def build_all_strategy_authority_closure(*, snapshot: AuthorityClosureSnapshot, output_dir: Path) -> AuthorityClosureBuildResult:
    families = _dataset_family_reviews(snapshot)
    versions = _dataset_version_decisions(snapshot)
    matrix = _authority_matrix(snapshot, families, versions)
    payloads = {
        "input_census_integrity.json": dict(snapshot.input_bundle),
        "dataset_family_authority_reviews.json": families,
        "dataset_version_authority_decisions.json": versions,
        "aeron7_nifty_f1_authority_review.json": _aeron7_review(snapshot),
        "unresolved_source_authority_review.json": _unresolved_source_review(snapshot),
        "signal_ledger_authority_review.json": _signal_ledger_review(snapshot),
        "all_strategy_authority_matrix.json": matrix,
        "authority_blocker_ledger.json": _blocker_ledger(snapshot),
        "strategy_authority_prioritization.json": _strategy_prioritization(snapshot),
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
        },
        "external_evidence_manifest.json": {
            "input_census_integrity": payloads["input_census_integrity.json"],
            "dataset_family_count": len(families),
            "dataset_version_count": len(versions),
            "authority_status": "BLOCKED_WITH_DECLARED_GAPS",
            "research_only": True,
            "read_only": True,
            "allowed_for_live_execution": False,
            "broker_api_called": False,
            "is_order_action": False,
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
