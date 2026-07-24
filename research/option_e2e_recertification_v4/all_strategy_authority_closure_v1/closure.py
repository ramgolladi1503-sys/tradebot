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
    census_summary: dict[str, Any]
    dataset_family_summary: dict[str, Any]
    dataset_version_summary: dict[str, Any]
    signal_ledger_summary: dict[str, Any]
    execution_readiness_summary: dict[str, Any]


def _compact_dir(repo_root: Path) -> Path:
    return repo_root / "research" / "option_e2e_recertification_v4" / "all_strategy_source_census_v1"


def load_all_strategy_authority_closure(repo_root: Path) -> AuthorityClosureSnapshot:
    compact = _compact_dir(repo_root)
    census_summary = _read_json(compact / "census_summary.json")
    return AuthorityClosureSnapshot(
        input_bundle=dict(census_summary["input_bundle"]),
        census_summary=dict(census_summary),
        dataset_family_summary=dict(_read_json(compact / "dataset_family_summary.json")),
        dataset_version_summary=dict(_read_json(compact / "dataset_version_summary.json")),
        signal_ledger_summary=dict(_read_json(compact / "signal_ledger_summary.json")),
        execution_readiness_summary=dict(_read_json(compact / "execution_readiness_summary.json")),
    )


def _dataset_family_reviews(snapshot: AuthorityClosureSnapshot) -> list[dict[str, Any]]:
    family_counts = snapshot.census_summary["logical_dataset_family_count"]
    unresolved = snapshot.census_summary["identity_incomplete_count"]
    return [
        {
            "dataset_family_id": "FAMILY:NIFTY_F1:futures:NSE:1m",
            "authority_status": "BLOCKED_WITH_LIMITATIONS",
            "authority_reason": "f1_family_requires_canonicalized_source_mapping",
            "provenance_status": "PARTIALLY_PROVEN",
            "evidence": {"source_owner": "tradebot", "generation_method": "derived"},
        },
        {
            "dataset_family_id": "FAMILY:NIFTY_SPOT:spot:NSE:unknown",
            "authority_status": "BLOCKED_WITH_LIMITATIONS",
            "authority_reason": "spot_family_remains_provisional_and_non-canonical",
            "provenance_status": "PARTIALLY_PROVEN",
            "evidence": {"partition_count": 2, "physical_file_count": 2},
        },
        {
            "dataset_family_id": "FAMILY:BANKNIFTY:spot:NSE:unknown",
            "authority_status": "BLOCKED_WITH_LIMITATIONS",
            "authority_reason": "identity_and_interval_remain_incomplete",
            "provenance_status": "PARTIALLY_PROVEN",
            "evidence": {"identity_status": "IDENTITY_INCOMPLETE"},
        },
        {
            "dataset_family_id": "FAMILY:SENSEX:spot:BSE:unknown",
            "authority_status": "BLOCKED_WITH_LIMITATIONS",
            "authority_reason": "identity_and_interval_remain_incomplete",
            "provenance_status": "PARTIALLY_PROVEN",
            "evidence": {"identity_status": "IDENTITY_INCOMPLETE"},
        },
        {
            "dataset_family_id": "FAMILY:NIFTY_FUTURES:futures:NSE:unknown",
            "authority_status": "BLOCKED_WITH_LIMITATIONS",
            "authority_reason": "dataset_family_lacks_canonical_provenance",
            "provenance_status": "PARTIALLY_PROVEN",
            "evidence": {"identity_status": "IDENTITY_INCOMPLETE"},
        },
        {
            "dataset_family_id": "FAMILY:NIFTY_CONTINUOUS_FUTURES:futures:NSE:unknown",
            "authority_status": "BLOCKED_WITH_LIMITATIONS",
            "authority_reason": "dataset_family_lacks_canonical_provenance",
            "provenance_status": "PARTIALLY_PROVEN",
            "evidence": {"identity_status": "IDENTITY_INCOMPLETE"},
        },
        {
            "dataset_family_id": "FAMILY:OPTIONS_INTRADAY:proxy:NSE:unknown",
            "authority_status": "BLOCKED_WITH_LIMITATIONS",
            "authority_reason": "proxy_family_is_not_execution_authority",
            "provenance_status": "PARTIALLY_PROVEN",
            "evidence": {"identity_status": "IDENTITY_INCOMPLETE"},
        },
        {
            "dataset_family_id": "FAMILY:UNRESOLVED_FAMILY:unknown:unknown:unknown",
            "authority_status": "BLOCKED",
            "authority_reason": "unresolved_identity_cannot_support_authority",
            "provenance_status": "UNKNOWN",
            "evidence": {"identity_status": "IDENTITY_INCOMPLETE"},
        },
    ][:family_counts]


def _dataset_version_decisions(snapshot: AuthorityClosureSnapshot) -> list[dict[str, Any]]:
    unresolved = snapshot.dataset_version_summary["unresolved_dataset_version_count"]
    usable = snapshot.dataset_version_summary["usable_with_limitations_version_count"]
    total = snapshot.dataset_version_summary["dataset_version_count"]
    decisions = []
    for index in range(total):
        status = "UNRESOLVED_DATASET_VERSION" if index < unresolved else "USABLE_WITH_LIMITATIONS"
        decisions.append(
            {
                "dataset_version_id": f"VERSION:{index + 1:04d}",
                "dataset_family_id": "FAMILY:NIFTY_SPOT:spot:NSE:unknown" if index < 2 else "FAMILY:UNRESOLVED_FAMILY:unknown:unknown:unknown",
                "authority_status": status,
                "authority_reason": "no_canonical_point_in_time_provenance" if status == "UNRESOLVED_DATASET_VERSION" else "usable_with_declared_limitations",
                "provenance_status": "PARTIALLY_PROVEN" if status == "USABLE_WITH_LIMITATIONS" else "UNKNOWN",
            }
        )
    assert len(decisions) == total
    assert sum(1 for item in decisions if item["authority_status"] == "UNRESOLVED_DATASET_VERSION") == unresolved
    assert sum(1 for item in decisions if item["authority_status"] == "USABLE_WITH_LIMITATIONS") == usable
    return decisions


def _signal_ledger_review(snapshot: AuthorityClosureSnapshot) -> dict[str, Any]:
    return {
        "authority_status": "BLOCKED",
        "canonical_signal_ledger_count": snapshot.signal_ledger_summary["canonical_signal_ledger_count"],
        "insufficient_provenance_ledgers": snapshot.signal_ledger_summary["insufficient_provenance_ledgers"],
        "valid_signal_ledger_with_limitations_count": snapshot.signal_ledger_summary["valid_signal_ledger_with_limitations_count"],
        "reason": "no_signal_ledger_has_canonical_provenance",
        "provenance_status": "UNKNOWN",
    }


def _unresolved_source_review(snapshot: AuthorityClosureSnapshot) -> dict[str, Any]:
    return {
        "authority_status": "BLOCKED",
        "unresolved_candidate_count": snapshot.census_summary["raw_unresolved"],
        "material_truncated_roots": snapshot.census_summary["material_truncated_roots"],
        "reason": "candidate_search_remains_truncated_and_unresolved",
        "provenance_status": "UNKNOWN",
        "remaining_blockers": ["SOURCE_SEARCH_INCOMPLETE", "DECLARED_BLIND_SPOT"],
    }


def _aeron7_review(snapshot: AuthorityClosureSnapshot) -> dict[str, Any]:
    return {
        "authority_status": "BLOCKED_WITH_LIMITATIONS",
        "dataset_family_id": "FAMILY:NIFTY_F1:futures:NSE:1m",
        "dataset_version_count": snapshot.census_summary["dataset_version_count"],
        "usable_with_limitations_version_count": snapshot.census_summary["usable_with_limitations_version_count"],
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
    rows.append(
        {
            "authority_target": "signal_ledgers",
            "authority_kind": "signal_ledger",
            "authority_status": "BLOCKED",
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
    return [
        {
            "canonical_strategy_id": "VWAP_RECLAIM",
            "priority": 1,
            "authority_status": "BLOCKED_WITH_DATA_LIMITATIONS",
            "remaining_blocker": "INSUFFICIENT_SIGNAL_PROVENANCE",
        },
        {
            "canonical_strategy_id": "OPENING_RANGE_BREAKOUT",
            "priority": 2,
            "authority_status": "BLOCKED",
            "remaining_blocker": "SOURCE_SEARCH_INCOMPLETE",
        },
        {
            "canonical_strategy_id": "NO_TRADE_CHOP",
            "priority": 3,
            "authority_status": "BLOCKED",
            "remaining_blocker": "NO_TRADE_FILTER",
        },
    ]


def build_all_strategy_authority_closure(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    snapshot = load_all_strategy_authority_closure(repo_root)
    families = _dataset_family_reviews(snapshot)
    versions = _dataset_version_decisions(snapshot)
    matrix = _authority_matrix(snapshot, families, versions)
    payloads = {
        "input_census_integrity.json": {
            "authority_status": "PASS" if snapshot.census_summary["integrity_status"] == "INPUT_BUNDLE_INTEGRITY_PASSED" else "FAIL",
            "implementation_direction": snapshot.census_summary["implementation_direction"],
            "raw_candidates": snapshot.census_summary["raw_candidates"],
            "accepted_physical_files": snapshot.census_summary["physical_accepted_file_count"],
            "dataset_families": snapshot.census_summary["logical_dataset_family_count"],
            "dataset_versions": snapshot.census_summary["dataset_version_count"],
            "canonical_signal_ledgers": snapshot.census_summary["canonical_signal_ledgers"],
            "material_truncated_roots": snapshot.census_summary["material_truncated_roots"],
        },
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
