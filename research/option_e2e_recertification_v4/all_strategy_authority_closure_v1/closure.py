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


FULL_RUN_A = Path("/Users/madhuram/tradebot-ml-evidence/all-strategy-option-e2e-recertification-v4/all_strategy_source_census_v1/20260724-133422_family_model")
FULL_RUN_B = Path("/Users/madhuram/tradebot-ml-evidence/all-strategy-option-e2e-recertification-v4/all_strategy_source_census_v1/20260724-133424_family_model_rerun")


def _compact_dir(repo_root: Path) -> Path:
    return repo_root / "research" / "option_e2e_recertification_v4" / "all_strategy_source_census_v1"


def _full_run_paths() -> tuple[Path, Path]:
    return FULL_RUN_A, FULL_RUN_B


def _semantic_digest(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _load_run(run_dir: Path) -> AuthorityClosureSnapshot:
    return AuthorityClosureSnapshot(
        input_bundle=dict(_read_json(run_dir / "input_bundle_integrity_independent.json")),
        physical_candidate_registry=list(_read_json(run_dir / "physical_candidate_registry.jsonl")),
        exact_content_blob_registry=list(_read_json(run_dir / "exact_content_blob_registry.jsonl")),
        exact_duplicate_groups=list(_read_json(run_dir / "exact_duplicate_groups.jsonl")),
        dataset_partition_registry=list(_read_json(run_dir / "dataset_partition_registry.jsonl")),
        logical_dataset_family_registry=list(_read_json(run_dir / "logical_dataset_family_registry.json")),
        dataset_version_registry=list(_read_json(run_dir / "dataset_version_registry.json")),
        semantic_duplicate_groups=list(_read_json(run_dir / "semantic_duplicate_groups.jsonl")),
        canonical_signal_ledger_registry=list(_read_json(run_dir / "canonical_signal_ledger_registry.json")),
        canonical_signal_ledger_audit=list(_read_json(run_dir / "canonical_signal_ledger_audit.json")),
        aeron7_nifty_f1_dataset_family=list(_read_json(run_dir / "aeron7_nifty_f1_dataset_family.json")),
        unresolved_candidate_resolution=list(_read_json(run_dir / "unresolved_candidate_resolution.json")),
        truncation_review=list(_read_json(run_dir / "truncation_review.json")),
        strategy_implementation_inventory=list(_read_json(run_dir / "strategy_implementation_inventory.json")),
        strategy_alias_registry=list(_read_json(run_dir / "strategy_alias_registry.json")),
        all_strategy_execution_readiness=list(_read_json(run_dir / "all_strategy_execution_readiness.json")),
        determinism=dict(_read_json(run_dir / "determinism.json")),
        current_986_breakdown=dict(_read_json(run_dir / "current_986_breakdown.json")),
        census_summary=dict(_read_json(run_dir / "census_summary.json")),
        dataset_family_summary={},
        dataset_version_summary={},
        signal_ledger_summary={},
        execution_readiness_summary={},
    )


def _verify_full_run_pair() -> tuple[AuthorityClosureSnapshot, AuthorityClosureSnapshot]:
    run_a, run_b = _full_run_paths()
    if not run_a.exists() or not run_b.exists():
        raise FileNotFoundError("AUTHORITY_CLOSURE_INPUT_INCOMPLETE")
    first = _load_run(run_a)
    second = _load_run(run_b)
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
        assert _semantic_digest(_read_json(run_a / name)) == _semantic_digest(_read_json(run_b / name))
    return first, second


def _family_authority_status(row: dict[str, Any]) -> tuple[str, str]:
    if row.get("identity_status") == "IDENTITY_INCOMPLETE":
        return "BLOCKED_WITH_LIMITATIONS", "identity_status_is_incomplete"
    if row.get("dataset_family_id") == "FAMILY:NIFTY_F1:futures:NSE:1m":
        return "BLOCKED_WITH_LIMITATIONS", "derived_source_requires_authority_closure"
    return "BLOCKED_WITH_LIMITATIONS", "no_canonical_family_authority"


def load_all_strategy_authority_closure(repo_root: Path) -> AuthorityClosureSnapshot:
    first, second = _verify_full_run_pair()
    # keep compact census as an anchor but do not rely on it as the primary truth source
    compact = _compact_dir(repo_root)
    census_summary = dict(_read_json(compact / "census_summary.json"))
    dataset_family_summary = dict(_read_json(compact / "dataset_family_summary.json"))
    dataset_version_summary = dict(_read_json(compact / "dataset_version_summary.json"))
    signal_ledger_summary = dict(_read_json(compact / "signal_ledger_summary.json"))
    execution_readiness_summary = dict(_read_json(compact / "execution_readiness_summary.json"))
    assert _semantic_digest(first.census_summary) == _semantic_digest(second.census_summary)
    assert census_summary["raw_candidates"] == first.census_summary["raw_candidates"]
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


def _dataset_family_reviews(snapshot: AuthorityClosureSnapshot) -> list[dict[str, Any]]:
    families = []
    for row in snapshot.logical_dataset_family_registry:
        authority_status, authority_reason = _family_authority_status(row)
        families.append(
            {
                "dataset_family_id": row["dataset_family_id"],
                "authority_status": authority_status,
                "authority_reason": authority_reason,
                "provenance_status": "PROVEN" if row.get("identity_status") == "PROVISIONAL" else "PARTIALLY_PROVEN",
                "evidence": {
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
    for row in snapshot.dataset_version_registry:
        decisions.append(
            {
                "dataset_version_id": row["dataset_version_id"],
                "dataset_family_id": row["dataset_family_id"],
                "authority_status": row["status"],
                "authority_reason": "provenance_not_canonical" if row["status"] == "USABLE_WITH_LIMITATIONS" else "no_canonical_point_in_time_provenance",
                "provenance_status": "PROVEN" if row["status"] == "CANONICAL_DATASET_VERSION" else "PARTIALLY_PROVEN",
                "limitations": list(row.get("limitations", [])),
                "partition_ids": list(row.get("partition_ids", [])),
                "source_provenance": row.get("source_provenance"),
            }
        )
    return decisions


def _signal_ledger_review(snapshot: AuthorityClosureSnapshot) -> dict[str, Any]:
    return {
        "authority_status": "BLOCKED",
        "canonical_signal_ledger_count": snapshot.signal_ledger_summary["canonical_signal_ledger_count"],
        "insufficient_provenance_ledgers": snapshot.signal_ledger_summary["insufficient_provenance_ledgers"],
        "valid_signal_ledger_with_limitations_count": snapshot.signal_ledger_summary["valid_signal_ledger_with_limitations_count"],
        "canonical_signal_ledger_registry": snapshot.canonical_signal_ledger_registry,
        "canonical_signal_ledger_audit": snapshot.canonical_signal_ledger_audit,
        "reason": "no_signal_ledger_has_canonical_provenance",
        "provenance_status": "UNKNOWN",
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
                "blocker": family["authority_reason"],
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


def build_all_strategy_authority_closure(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    snapshot = load_all_strategy_authority_closure(repo_root)
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
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in payloads.items():
        _write_json_with_sidecar(output_dir / filename, payload)
    return {
        "authority_status": "BLOCKED_WITH_DECLARED_GAPS",
        "input_census_integrity": payloads["input_census_integrity.json"],
        "dataset_family_count": len(families),
        "dataset_version_count": len(versions),
        "matrix_count": len(matrix),
        "blocked_lane_count": snapshot.census_summary["blocked_lanes"],
        "ready_for_causal_execution_lanes": snapshot.census_summary["ready_for_causal_execution_lanes"],
        "valid_precomputed_signals_lanes": snapshot.census_summary["valid_precomputed_signals_lanes"],
    }
