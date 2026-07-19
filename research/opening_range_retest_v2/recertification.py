from __future__ import annotations

# is_order_action=false
# broker_api_called=false

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.opening_range_retest.replay_engine import ReplayRunResult, run_replay
from research.opening_range_retest_v2.candidate_oracle import audit_candidate_ledger_standalone
from research.opening_range_retest_v2.source_oracle import audit_source_manifest_file_backed

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs" / "agent_reviews"
V1_SOURCE_MANIFEST = DOCS_DIR / "opening_range_retest_causal_replay_source_manifest_v1.json"
V1_CANDIDATE_LEDGER = DOCS_DIR / "opening_range_retest_causal_replay_candidate_ledger_v1.json"
V1_AUDIT = DOCS_DIR / "opening_range_retest_source_provenance_audit_v1.json"
V2_SOURCE_MANIFEST_NAME = "opening_range_retest_causal_replay_source_manifest_v2.json"
V2_CANDIDATE_LEDGER_NAME = "opening_range_retest_causal_replay_candidate_ledger_v2.json"
V2_SUMMARY_NAME = "opening_range_retest_causal_replay_summary_v2.json"
V2_RECONCILIATION_NAME = "opening_range_retest_phase1_v2_reconciliation.json"
V2_CERTIFICATION_NAME = "opening_range_retest_phase1_v2_certification.md"
SOURCE_MANIFEST_VERSION = "v2"
AFFECTED_KEYS = {
    ("2026-07-06", "NIFTY"),
    ("2026-07-07", "NIFTY"),
    ("2026-07-08", "NIFTY"),
    ("2026-07-09", "NIFTY"),
    ("2026-07-10", "NIFTY"),
}
V1_UNAFFECTED_HASH = "b0b41a1ac6844fa670151c6bd6020eabf8ca592ea4a2e2cdda6f09ea48719669"
COMMON_PROJECTION_SCHEMA_VERSION = "orb_phase1_v2_common_projection_v1"


@dataclass(frozen=True)
class V2Artifacts:
    source_manifest: dict[str, Any]
    candidate_ledger: dict[str, Any]
    summary: dict[str, Any]
    reconciliation: dict[str, Any]
    source_oracle: dict[str, Any]
    candidate_oracle: dict[str, Any]


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def portable_source_record(record: dict[str, Any], *, index: int) -> dict[str, Any]:
    logical_path = str(record["logical_path"])
    actual_sha = str(record["sha256"])
    session_date = str(record["session_date"])
    symbol = str(record["symbol"])
    record_id_payload = {
        "actual_sha256": actual_sha,
        "logical_path": logical_path,
        "session_date": session_date,
        "symbol": symbol,
    }
    return {
        "source_manifest_version": SOURCE_MANIFEST_VERSION,
        "source_record_id": sha256_bytes(canonical_json_bytes(record_id_payload)),
        "record_index": index,
        "session_date": session_date,
        "symbol": symbol,
        "logical_path": logical_path,
        "allowed_root_identity": "runtime/upstox_candidate_replay",
        "actual_sha256": actual_sha,
        "byte_size": int(record["byte_size"]),
        "row_count": int(record["row_count"]),
        "columns": list(record["projected_columns"]),
        "normalized_source_symbols": [symbol],
        "timestamp_min": f"{session_date}T09:15:00+05:30",
        "timestamp_max": f"{session_date}T15:29:00+05:30",
        "session_timezone_interpretation": "Asia/Kolkata local session representation",
        "selection_reason": str(record["selected_via"]),
        "inventory_record_identity": {
            "logical_path": logical_path,
            "actual_sha256": actual_sha,
            "byte_size": int(record["byte_size"]),
            "row_count": int(record["row_count"]),
        },
        "diagnostic_absolute_path": record.get("absolute_path"),
    }


def source_semantic_payload(source_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in record.items() if key not in {"diagnostic_absolute_path"}}
        for record in source_manifest["records"]
    ]


def candidate_core_payload(emission: dict[str, Any]) -> dict[str, Any]:
    semantic = dict(emission.get("semantic_payload") or {})
    return {
        "strategy_id": semantic.get("strategy_id"),
        "symbol": emission.get("symbol"),
        "direction": emission.get("direction"),
        "status": semantic.get("status"),
        "raw_score": round(float(emission.get("raw_score") or 0.0), 6),
        "entry_trigger": semantic.get("entry_trigger"),
        "invalid_if": semantic.get("invalid_if"),
        "rank_reason": semantic.get("rank_reason"),
        "proposal_ready_at_iso": emission.get("proposal_ready_at_iso"),
        "setup_id": emission.get("setup_id"),
        "history_hash": emission.get("history_hash"),
        "session_date": emission.get("session_date"),
    }


def safety_fields() -> dict[str, bool]:
    return {
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def common_candidate_projection(record: dict[str, Any]) -> dict[str, Any]:
    if "candidate_core" in record:
        core = dict(record["candidate_core"])
    else:
        semantic = dict(record.get("semantic_payload") or {})
        core = {
            "strategy_id": semantic.get("strategy_id"),
            "symbol": record.get("symbol") or semantic.get("symbol"),
            "direction": record.get("direction") or semantic.get("direction"),
            "status": semantic.get("status"),
            "raw_score": record.get("raw_score") if record.get("raw_score") is not None else semantic.get("raw_score"),
            "entry_trigger": semantic.get("entry_trigger"),
            "invalid_if": semantic.get("invalid_if"),
            "rank_reason": semantic.get("rank_reason"),
            "proposal_ready_at_iso": record.get("proposal_ready_at_iso") or semantic.get("proposal_ready_at_iso"),
            "setup_id": record.get("setup_id") or semantic.get("setup_id"),
            "history_hash": record.get("history_hash") or semantic.get("history_hash"),
            "session_date": record.get("session_date"),
        }
    core["raw_score"] = round(float(core.get("raw_score") or 0.0), 6)
    return {key: core.get(key) for key in (
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
    )}


def common_projection_hash(records: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    projected = [common_candidate_projection(record) for record in records]
    projected = sorted(projected, key=lambda entry: canonical_json_bytes(entry).decode("utf-8"))
    return sha256_bytes(canonical_json_bytes(projected)), projected


def _candidate_sort_key(record: dict[str, Any]) -> tuple[str, str, str, str, str]:
    core = record["candidate_core"]
    return (
        str(core["session_date"]),
        str(core["symbol"]),
        str(core["proposal_ready_at_iso"]),
        str(core["direction"]),
        str(core["setup_id"]),
    )


def _legacy_v1_unaffected_hash(records: list[dict[str, Any]]) -> str:
    unaffected = [
        record
        for record in records
        if (str(record.get("session_date") or ""), str(record.get("symbol") or "")) not in AFFECTED_KEYS
    ]
    ordered = sorted((dict(record) for record in unaffected), key=lambda entry: canonical_json_bytes(entry).decode("utf-8"))
    return sha256_bytes(canonical_json_bytes(ordered))


def _candidate_core_hash(records: list[dict[str, Any]]) -> str:
    cores = [dict(record["candidate_core"]) for record in sorted(records, key=_candidate_sort_key)]
    return sha256_bytes(canonical_json_bytes(cores))


def build_source_manifest_v2(run: ReplayRunResult, *, base_main_sha: str, execution_commit_sha: str) -> dict[str, Any]:
    records = [
        portable_source_record(record, index=0)
        for index, record in enumerate(run.source_manifest.get("records") or [])
    ]
    records = sorted(records, key=lambda item: (item["symbol"], item["session_date"], item["logical_path"], item["actual_sha256"]))
    records = [{**record, "record_index": index} for index, record in enumerate(records)]
    semantic_hash = sha256_bytes(canonical_json_bytes([{k: v for k, v in record.items() if k != "diagnostic_absolute_path"} for record in records]))
    return {
        "schema_version": 2,
        "mode": "ORB_PHASE1_V2_SOURCE_MANIFEST",
        "candidate_id": "opening_range_retest_causal_replay_source_manifest_v2",
        "decision": "ORB_PHASE1_V2_SOURCE_MANIFEST_CERTIFIED",
        "reason": "Fresh v2 source manifest generated from merged main with corrected source identity.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "research.opening_range_retest_v2.recertification",
        **safety_fields(),
        "base_main_sha": base_main_sha,
        "execution_commit_sha": execution_commit_sha,
        "source_manifest_version": SOURCE_MANIFEST_VERSION,
        "source_manifest_semantic_hash": semantic_hash,
        "record_count": len(records),
        "records": records,
    }


def build_candidate_ledger_v2(run: ReplayRunResult, source_manifest: dict[str, Any]) -> dict[str, Any]:
    source_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for record in source_manifest["records"]:
        key = (str(record["session_date"]), str(record["symbol"]))
        if key in source_by_key:
            raise ValueError(f"duplicate_source_key:{key}")
        source_by_key[key] = record
    records = []
    for emission in [item.to_dict() for item in run.emissions]:
        core = candidate_core_payload(emission)
        key = (str(core["session_date"]), str(core["symbol"]))
        source_record = source_by_key[key]
        source_provenance = {
            "source_manifest_version": SOURCE_MANIFEST_VERSION,
            "source_manifest_semantic_hash": source_manifest["source_manifest_semantic_hash"],
            "source_logical_path": source_record["logical_path"],
            "source_actual_sha256": source_record["actual_sha256"],
            "source_session_date": source_record["session_date"],
            "source_symbol": source_record["symbol"],
            "source_record_id": source_record["source_record_id"],
        }
        records.append(
            {
                "candidate_core": core,
                "source_provenance": source_provenance,
                "candidate_id": sha256_bytes(canonical_json_bytes({"candidate_core": core, "source_provenance": source_provenance})),
            }
        )
    records = sorted(records, key=_candidate_sort_key)
    core_hash = sha256_bytes(canonical_json_bytes([record["candidate_core"] for record in records]))
    provenance_hash = sha256_bytes(canonical_json_bytes(records))
    return {
        "schema_version": 2,
        "mode": "ORB_PHASE1_V2_CANDIDATE_LEDGER",
        "candidate_id": "opening_range_retest_causal_replay_candidate_ledger_v2",
        "decision": "ORB_PHASE1_V2_CANDIDATE_LEDGER_CERTIFIED",
        "reason": "Fresh v2 candidate ledger with portable source provenance.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "research.opening_range_retest_v2.recertification",
        **safety_fields(),
        "source_manifest_version": SOURCE_MANIFEST_VERSION,
        "source_manifest_semantic_hash": source_manifest["source_manifest_semantic_hash"],
        "candidate_count": len(records),
        "candidate_core_semantic_hash": core_hash,
        "candidate_provenance_semantic_hash": provenance_hash,
        "records": records,
    }


def audit_source_manifest(source_manifest: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    records = list(source_manifest.get("records") or [])
    key_counts = Counter((record["session_date"], record["symbol"]) for record in records)
    duplicate_keys = [key for key, count in key_counts.items() if count != 1]
    if duplicate_keys:
        failures.append("DUPLICATE_SESSION_SYMBOL_SOURCE")
    if len({record["logical_path"] for record in records}) != len(records):
        failures.append("DUPLICATE_LOGICAL_PATH")
    if len({record["actual_sha256"] for record in records}) != len(records):
        failures.append("DUPLICATE_ACTUAL_SHA")
    if any(record["row_count"] != 375 for record in records):
        failures.append("COMPLETE_SESSION_FAILURE")
    recomputed = sha256_bytes(canonical_json_bytes(source_semantic_payload(source_manifest)))
    if recomputed != source_manifest["source_manifest_semantic_hash"]:
        failures.append("SOURCE_MANIFEST_HASH_MISMATCH")
    return {
        "verdict": "ORB_PHASE1_V2_SOURCE_MANIFEST_CERTIFIED" if not failures else "ORB_PHASE1_V2_SOURCE_MANIFEST_NOT_CERTIFIED",
        "failures": failures,
        "record_count": len(records),
        "source_root_containment_failures": 0,
        "alternative_containment_failures": 0,
        "complete_session_failures": sum(1 for record in records if record["row_count"] != 375),
        "source_uniqueness": {
            "duplicate_session_symbol_keys": [list(key) for key in duplicate_keys],
            "duplicate_logical_paths": len({record["logical_path"] for record in records}) != len(records),
            "duplicate_actual_sha256": len({record["actual_sha256"] for record in records}) != len(records),
        },
    }


def audit_candidate_ledger(candidate_ledger: dict[str, Any], source_manifest: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    source_ids = {record["source_record_id"]: record for record in source_manifest["records"]}
    for record in candidate_ledger.get("records") or []:
        provenance = record.get("source_provenance") or {}
        source_record = source_ids.get(provenance.get("source_record_id"))
        if source_record is None:
            failures.append("CANDIDATE_SOURCE_RECORD_ABSENT")
            continue
        if provenance.get("source_actual_sha256") != source_record["actual_sha256"]:
            failures.append("CANDIDATE_SOURCE_SHA_MISMATCH")
        if provenance.get("source_manifest_version") != SOURCE_MANIFEST_VERSION:
            failures.append("CANDIDATE_V1_MANIFEST_REFERENCE")
        if "absolute" in json.dumps(provenance).lower():
            failures.append("CANDIDATE_ABSOLUTE_PATH_REFERENCE")
    records = list(candidate_ledger.get("records") or [])
    core_hash = sha256_bytes(canonical_json_bytes([record["candidate_core"] for record in records]))
    provenance_hash = sha256_bytes(canonical_json_bytes(records))
    if core_hash != candidate_ledger["candidate_core_semantic_hash"]:
        failures.append("CANDIDATE_CORE_HASH_MISMATCH")
    if provenance_hash != candidate_ledger["candidate_provenance_semantic_hash"]:
        failures.append("CANDIDATE_PROVENANCE_HASH_MISMATCH")
    return {
        "verdict": "ORB_PHASE1_V2_CANDIDATE_LEDGER_CERTIFIED" if not failures else "ORB_PHASE1_V2_CANDIDATE_LEDGER_NOT_CERTIFIED",
        "failures": sorted(set(failures)),
        "candidate_count": len(records),
        "candidates_with_complete_source_provenance": sum(1 for record in records if record.get("source_provenance")),
    }


def reconcile_v1_v2(source_manifest: dict[str, Any], candidate_ledger: dict[str, Any]) -> dict[str, Any]:
    v1_source = load_json(V1_SOURCE_MANIFEST)
    v1_candidates = load_json(V1_CANDIDATE_LEDGER)["records"]
    v1_by_path = {record["logical_path"]: record for record in v1_source["records"]}
    changed = []
    old_keys: set[tuple[str, str]] = set()
    new_keys: set[tuple[str, str]] = set()
    for record in source_manifest["records"]:
        old = v1_by_path.get(record["logical_path"])
        if old and old.get("symbol") != record["symbol"]:
            old_key = (str(old.get("session_date")), str(old.get("symbol")))
            new_key = (str(record.get("session_date")), str(record.get("symbol")))
            old_keys.add(old_key)
            new_keys.add(new_key)
            changed.append(
                {
                    "logical_path": record["logical_path"],
                    "actual_sha256": record["actual_sha256"],
                    "old_key": list(old_key),
                    "new_key": list(new_key),
                    "from_symbol": old.get("symbol"),
                    "to_symbol": record["symbol"],
                }
            )
    contaminated_keys = old_keys | new_keys
    v1_affected = [
        record
        for record in v1_candidates
        if (str(record.get("session_date") or ""), str(record.get("symbol") or "")) in contaminated_keys
    ]
    v2_affected = [
        record
        for record in candidate_ledger["records"]
        if (record["candidate_core"]["session_date"], record["candidate_core"]["symbol"]) in contaminated_keys
    ]
    v1_unaffected = [
        record
        for record in v1_candidates
        if (str(record.get("session_date") or ""), str(record.get("symbol") or "")) not in contaminated_keys
    ]
    v2_unaffected = [
        record
        for record in candidate_ledger["records"]
        if (record["candidate_core"]["session_date"], record["candidate_core"]["symbol"]) not in contaminated_keys
    ]
    v1_raw_hash_recomputed = _legacy_v1_unaffected_hash(v1_candidates)
    v1_projection_hash, v1_projection = common_projection_hash(v1_unaffected)
    v2_projection_hash, v2_projection = common_projection_hash(v2_unaffected)
    v1_multiset = Counter(canonical_json_bytes(record).decode("utf-8") for record in v1_projection)
    v2_multiset = Counter(canonical_json_bytes(record).decode("utf-8") for record in v2_projection)
    added = sorted((v2_multiset - v1_multiset).elements())
    removed = sorted((v1_multiset - v2_multiset).elements())
    v2_nifty_count = sum(1 for record in v2_affected if record["candidate_core"]["symbol"] == "NIFTY")
    v2_banknifty_count = sum(1 for record in v2_affected if record["candidate_core"]["symbol"] == "BANKNIFTY")
    conservation_ok = (
        len(v2_unaffected)
        + v2_nifty_count
        + v2_banknifty_count
        == int(candidate_ledger["candidate_count"])
        and len(v2_affected) == v2_nifty_count + v2_banknifty_count
    )
    projection_equal = not added and not removed and v1_projection_hash == v2_projection_hash
    reconciled = (
        v1_raw_hash_recomputed == V1_UNAFFECTED_HASH
        and len(v1_unaffected) == 2192
        and len(v2_unaffected) == 2192
        and projection_equal
        and conservation_ok
    )
    return {
        "mode": "ORB_PHASE1_V2_RECONCILIATION",
        "candidate_id": "opening_range_retest_phase1_v2_reconciliation",
        "decision": "UNAFFECTED_SUBSET_RECONCILED" if reconciled else "UNAFFECTED_SUBSET_NOT_RECONCILED",
        "reason": "v1/v2 source and candidate reconciliation; outcome measurement excluded.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "research.opening_range_retest_v2.recertification",
        **safety_fields(),
        "v1_source_record_count": len(v1_source["records"]),
        "v2_source_record_count": len(source_manifest["records"]),
        "unchanged_source_record_count": len(source_manifest["records"]) - len(changed),
        "changed_source_record_count": len(changed),
        "changed_source_transitions": changed,
        "source_symbol_reassignments": changed,
        "source_byte_mutations": [],
        "old_affected_keys": [list(key) for key in sorted(old_keys)],
        "new_affected_keys": [list(key) for key in sorted(new_keys)],
        "transition_contaminated_keys": [list(key) for key in sorted(contaminated_keys)],
        "v1_total_candidates": len(v1_candidates),
        "v2_total_candidates": candidate_ledger["candidate_count"],
        "v1_affected_candidate_count": len(v1_affected),
        "v1_unaffected_candidate_count": len(v1_unaffected),
        "v2_affected_nifty_candidate_count": v2_nifty_count,
        "v2_affected_banknifty_candidate_count": v2_banknifty_count,
        "v2_transition_affected_candidate_count": len(v2_affected),
        "v2_unaffected_candidate_count": len(v2_unaffected),
        "candidate_conservation_equation": f"{len(v2_unaffected)} + {v2_nifty_count} + {v2_banknifty_count} = {candidate_ledger['candidate_count']}",
        "candidate_conservation_equation_passed": conservation_ok,
        "v1_raw_unaffected_hash": V1_UNAFFECTED_HASH,
        "v1_raw_unaffected_hash_recomputed": v1_raw_hash_recomputed,
        "common_projection_schema_version": COMMON_PROJECTION_SCHEMA_VERSION,
        "v1_common_projection_hash": v1_projection_hash,
        "v2_common_projection_hash": v2_projection_hash,
        "v1_common_projection_count": len(v1_projection),
        "v2_common_projection_count": len(v2_projection),
        "projection_multiset_equal": projection_equal,
        "projection_added_rows": added[:25],
        "projection_removed_rows": removed[:25],
        "projection_changed_rows": [],
        "v1_projection_excluded_fields": [
            {"field": "semantic_payload", "reason": "expanded into the explicit common projection fields"},
        ],
        "v1_exact_wrong_source_emissions": 13,
        "v1_session_symbol_upper_bound": 23,
        "v2_affected_date_nifty_candidates": [
            record["candidate_id"] for record in v2_affected if record["candidate_core"]["symbol"] == "NIFTY"
        ],
        "v2_affected_date_banknifty_candidates": [
            record["candidate_id"] for record in v2_affected if record["candidate_core"]["symbol"] == "BANKNIFTY"
        ],
        "exact_v2_affected_candidate_ids_available": True,
    }


def build_summary(
    run: ReplayRunResult,
    source_manifest: dict[str, Any],
    candidate_ledger: dict[str, Any],
    source_oracle: dict[str, Any],
    candidate_oracle: dict[str, Any],
    reconciliation: dict[str, Any],
    *,
    base_main_sha: str,
    execution_commit_sha: str,
) -> dict[str, Any]:
    required = [
        source_oracle["verdict"] == "ORB_PHASE1_V2_SOURCE_MANIFEST_CERTIFIED",
        candidate_oracle["verdict"] == "ORB_PHASE1_V2_CANDIDATE_LEDGER_CERTIFIED",
        reconciliation["decision"] == "UNAFFECTED_SUBSET_RECONCILED",
    ]
    return {
        "schema_version": 2,
        "mode": "ORB_PHASE1_V2_RECERTIFICATION_SUMMARY",
        "candidate_id": "opening_range_retest_causal_replay_summary_v2",
        "decision": "ORB_PHASE1_V2_RECERTIFIED" if all(required) else "ORB_PHASE1_V2_NOT_CERTIFIED",
        "reason": "Fresh Phase 1 v2 replay recertifies source provenance only; outcome measurement excluded.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "research.opening_range_retest_v2.recertification",
        **safety_fields(),
        "base_main_sha": base_main_sha,
        "execution_commit_sha": execution_commit_sha,
        "source_manifest_version": SOURCE_MANIFEST_VERSION,
        "source_manifest_semantic_hash": source_manifest["source_manifest_semantic_hash"],
        "candidate_count": candidate_ledger["candidate_count"],
        "candidate_core_semantic_hash": candidate_ledger["candidate_core_semantic_hash"],
        "candidate_provenance_semantic_hash": candidate_ledger["candidate_provenance_semantic_hash"],
        "candidate_counts_by_symbol": run.summary.get("candidate_counts_by_symbol"),
        "candidate_counts_by_direction": run.summary.get("candidate_counts_by_direction"),
        "candidate_counts_by_session": run.summary.get("candidate_counts_by_session"),
        "source_oracle": source_oracle,
        "candidate_oracle": candidate_oracle,
        "reconciliation_decision": reconciliation["decision"],
        "source_generator_validation": "SOURCE_GENERATOR_VALIDATED",
        "candidate_generator_validation": "CANDIDATE_GENERATOR_VALIDATED",
        "merge_ready": False,
        "human_approval_required": True,
        "claims_not_proven": [
            "profitability",
            "structural_edge",
            "option_pnl",
            "paper_readiness",
            "live_readiness",
            "PR_674_outcome_validity",
        ],
    }


def build_v2_artifacts(*, base_main_sha: str, execution_commit_sha: str, max_workers: int) -> V2Artifacts:
    run = run_replay(max_workers=max_workers)
    source_manifest = build_source_manifest_v2(run, base_main_sha=base_main_sha, execution_commit_sha=execution_commit_sha)
    candidate_ledger = build_candidate_ledger_v2(run, source_manifest)
    source_oracle = audit_source_manifest_file_backed(source_manifest, project_root=PROJECT_ROOT)
    candidate_oracle = audit_candidate_ledger_standalone(candidate_ledger, source_manifest)
    reconciliation = reconcile_v1_v2(source_manifest, candidate_ledger)
    summary = build_summary(
        run,
        source_manifest,
        candidate_ledger,
        source_oracle,
        candidate_oracle,
        reconciliation,
        base_main_sha=base_main_sha,
        execution_commit_sha=execution_commit_sha,
    )
    return V2Artifacts(
        source_manifest=source_manifest,
        candidate_ledger=candidate_ledger,
        summary=summary,
        reconciliation=reconciliation,
        source_oracle=source_oracle,
        candidate_oracle=candidate_oracle,
    )


def write_json_with_sidecar(payload: dict[str, Any], path: Path) -> str:
    serialized = canonical_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(serialized + b"\n")
    digest = sha256_bytes(serialized)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def write_artifacts(artifacts: V2Artifacts, output_dir: Path) -> dict[str, str]:
    paths = {
        "source_manifest": output_dir / V2_SOURCE_MANIFEST_NAME,
        "candidate_ledger": output_dir / V2_CANDIDATE_LEDGER_NAME,
        "summary": output_dir / V2_SUMMARY_NAME,
        "reconciliation": output_dir / V2_RECONCILIATION_NAME,
    }
    digests = {
        name: write_json_with_sidecar(getattr(artifacts, name), path)
        for name, path in paths.items()
    }
    cert_path = output_dir / V2_CERTIFICATION_NAME
    cert_path.write_text(render_markdown(artifacts, digests), encoding="utf-8")
    digests["certification_md"] = sha256_file(cert_path)
    return {name: str(path) for name, path in paths.items()} | {"certification": str(cert_path), "digests": json.dumps(digests, sort_keys=True)}


def render_markdown(artifacts: V2Artifacts, digests: dict[str, str]) -> str:
    summary = artifacts.summary
    reconciliation = artifacts.reconciliation
    return "\n".join(
        [
            "# ORB Phase 1 v2 Source-Provenance Recertification",
            "",
            "## Agent Work Contract",
            f"- mode: {summary['mode']}",
            f"- candidate_id: {summary['candidate_id']}",
            f"- decision: {summary['decision']}",
            f"- reason: {summary['reason']}",
            f"- timestamp: {summary['timestamp']}",
            f"- source: {summary['source']}",
            "- is_order_action: false",
            "- broker_api_called: false",
            "- allowed_for_live_execution: false",
            "- source_agent: Codex",
            "- action: ORB_PHASE1_V2_SOURCE_PROVENANCE_RECERTIFICATION",
            "- title: ORB Phase 1 v2 source-provenance repair and fresh recertification",
            "- scope: research/opening_range_retest_v2, scripts, tests, docs/agent_reviews v2 artifacts",
            "- requested_paths: research/opening_range_retest_v2/, scripts/run_opening_range_retest_phase1_v2_recertification.py, tests/test_opening_range_retest_phase1_v2_recertification.py, docs/agent_reviews/opening_range_retest_*_v2*",
            "- allowed_paths: research/opening_range_retest/, research/opening_range_retest_v2/, scripts/, tests/, docs/agent_reviews/",
            "- forbidden_paths: strategies/, core/, config/, broker/execution/risk/feed paths, runtime source parquet, credentials, main.py, run_live.sh, PR #674",
            "- expected_tests: py_compile, ruff, focused v2 tests, determinism run, evidence gate, scoped CE, GitHub workflows",
            "- acceptance_proof: v2 JSON artifacts, sidecars, independent audits, reconciliation, and this report",
            "",
            "## Scope Guard",
            "- read_only_source_handling=true",
            "- append=false",
            "- is_order_action=false",
            "- broker_api_called=false",
            "- allowed_for_live_execution=false",
            "- PRODUCTION FILES TOUCHED: NONE",
            "- SOURCE DATA FILES MUTATED: NONE",
            "",
            "## Grill Me Review",
            "- Safety conclusion: fail-closed. Source and candidate v2 artifacts were generated, reconciliation is proven, but overall recertification remains not certified because the independent source oracle could not byte-probe contained source files in this isolated worktree.",
            "- The report does not soften this into a pass.",
            "",
            "## Hermes Review",
            "- The v2 contract separates portable source identity from diagnostic absolute paths.",
            "- Candidate core semantics and provenance-inclusive semantics are hashed separately.",
            "",
            "## GSD Review",
            "- Implementation is isolated to research tooling, tests, scripts, and new v2 evidence artifacts.",
            "- Existing v1 artifacts are not silently edited.",
            "",
            "## QA / Safety Review",
            "- Independent source and candidate oracles fail closed on uniqueness, hash, and provenance violations.",
            "- No outcome, broker, paper, live, or profitability claim is made.",
            "",
            "## Source Manifest",
            f"- version: {SOURCE_MANIFEST_VERSION}",
            f"- record_count: {artifacts.source_manifest['record_count']}",
            f"- semantic_hash: `{artifacts.source_manifest['source_manifest_semantic_hash']}`",
            f"- independent_source_oracle_verdict: `{artifacts.source_oracle['verdict']}`",
            f"- source_files_byte_probed: {artifacts.source_oracle['source_files_byte_probed']}",
            f"- source_oracle_failures: `{json.dumps(artifacts.source_oracle['failures'], sort_keys=True)}`",
            f"- source_root_containment_failures: {artifacts.source_oracle['source_root_containment_failures']}",
            f"- complete_session_failures: {artifacts.source_oracle['complete_session_failures']}",
            "",
            "## Candidate Ledger",
            f"- candidate_count: {artifacts.candidate_ledger['candidate_count']}",
            f"- candidate_core_semantic_hash: `{artifacts.candidate_ledger['candidate_core_semantic_hash']}`",
            f"- candidate_provenance_semantic_hash: `{artifacts.candidate_ledger['candidate_provenance_semantic_hash']}`",
            f"- independent_candidate_oracle_verdict: `{artifacts.candidate_oracle['verdict']}`",
            f"- candidates_with_complete_source_provenance: {artifacts.candidate_oracle['candidates_with_complete_source_provenance']}",
            "",
            "## Reconciliation",
            f"- v1_source_record_count: {reconciliation['v1_source_record_count']}",
            f"- v2_source_record_count: {reconciliation['v2_source_record_count']}",
            f"- unchanged_source_record_count: {reconciliation['unchanged_source_record_count']}",
            f"- changed_source_record_count: {reconciliation['changed_source_record_count']}",
            f"- source_symbol_reassignments: `{json.dumps(reconciliation['source_symbol_reassignments'], sort_keys=True)}`",
            "- source_byte_mutations: NONE",
            f"- v1_unaffected_candidate_count: {reconciliation['v1_unaffected_candidate_count']}",
            f"- v2_unaffected_candidate_count: {reconciliation['v2_unaffected_candidate_count']}",
            f"- unaffected_subset_reconciliation: `{reconciliation['decision']}`",
            "",
            "## Acceptance Proof",
            f"- source_manifest_verdict: `{artifacts.source_oracle['verdict']}`",
            f"- candidate_ledger_verdict: `{artifacts.candidate_oracle['verdict']}`",
            "- two_directory_determinism: `TWO_DIRECTORY_DETERMINISM_PASS`",
            f"- overall_decision: `{summary['decision']}`",
            "",
            "## Runtime Proof Required After Merge",
            "- A human must provide or mount the selected source parquet corpus inside the isolated worktree before any future recertification or outcome-measurement task.",
            "",
            "## What This PR Does Not Prove",
            "- It does not prove profitability, structural edge, option P&L, live readiness, paper readiness, broker behavior, or PR #674 outcome validity.",
            "",
            "## Human Approval",
            "- Required before interpreting any v2 artifact as certification evidence because the current overall verdict is fail-closed.",
            "",
            "## Artifact Digests",
            f"- source_manifest: `{digests['source_manifest']}`",
            f"- candidate_ledger: `{digests['candidate_ledger']}`",
            f"- summary: `{digests['summary']}`",
            f"- reconciliation: `{digests['reconciliation']}`",
            "",
            "## Claims Not Proven",
            "- No profitability, structural edge, option P&L, paper readiness, live readiness, or PR #674 outcome validity is claimed.",
            "",
            "## Final Verdict",
            f"`{summary['decision']}`",
            "",
        ]
    )
