#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _check_sha256(path: Path) -> None:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.exists():
        raise SystemExit(f"missing_sidecar:{sidecar}")
    expected = sidecar.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(path.read_bytes().rstrip(b"\n")).hexdigest()
    if expected != actual:
        raise SystemExit(f"sha256_mismatch:{path.name}:expected={expected}:actual={actual}")


def _record_key(record: dict[str, object]) -> tuple[str, str, str, str]:
    return (
        str(record.get("symbol") or ""),
        str(record.get("session_date") or ""),
        str(record.get("logical_path") or ""),
        str(record.get("sha256") or ""),
    )


def _canonical_session_key(record: dict[str, object]) -> str:
    return json.dumps(
        {
            "logical_path": str(record.get("logical_path") or ""),
            "selected_source_sha256": str(record.get("sha256") or ""),
            "session_date": str(record.get("session_date") or ""),
            "symbol": str(record.get("symbol") or ""),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _partition_assignment(record: dict[str, object], *, shard_count: int) -> int:
    digest = hashlib.sha256(_canonical_session_key(record).encode("utf-8")).hexdigest()
    return int(digest, 16) % shard_count


def _ledger_key(entry: dict[str, object]) -> tuple[str, str, str, str, str]:
    return (
        str(entry.get("session_date") or ""),
        str(entry.get("symbol") or ""),
        str(entry.get("proposal_ready_at_iso") or ""),
        str(entry.get("direction") or ""),
        str(entry.get("setup_id") or ""),
    )


def _normalized_shard_metadata(metadata: dict[str, object], *, kind: str) -> dict[str, object]:
    if kind == "summary":
        before = metadata.get("selected_file_count_before_sharding")
        after = metadata.get("selected_file_count_after_sharding")
    elif kind == "manifest":
        before = metadata.get("selected_record_count_before_sharding")
        after = metadata.get("selected_record_count_after_sharding")
    else:
        raise ValueError(f"unsupported_shard_metadata_kind:{kind}")
    return {
        "shard_count": metadata.get("shard_count"),
        "shard_index": metadata.get("shard_index"),
        "is_sharded_run": metadata.get("is_sharded_run"),
        "merged_from_shards": metadata.get("merged_from_shards", False),
        "selected_count_before_sharding": before,
        "selected_count_after_sharding": after,
        "merged_shard_indexes": list(metadata.get("merged_shard_indexes") or []),
    }


def _git_execution_state() -> tuple[str | None, bool]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if head.returncode != 0:
        return None, False
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0:
        return head.stdout.strip() or None, False
    return head.stdout.strip() or None, not bool(status.stdout.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit bounded opening-range-retest replay artifacts.")
    parser.add_argument("--artifact-dir", type=Path, default=Path("docs/agent_reviews"))
    args = parser.parse_args()

    summary_path = args.artifact_dir / "opening_range_retest_causal_replay_summary_v1.json"
    contract_path = args.artifact_dir / "opening_range_retest_causal_replay_contract_v1.json"
    source_manifest_path = args.artifact_dir / "opening_range_retest_causal_replay_source_manifest_v1.json"
    ledger_path = args.artifact_dir / "opening_range_retest_causal_replay_ledger_v1.json"
    for path in (summary_path, contract_path, source_manifest_path):
        _check_sha256(path)
    if not ledger_path.exists():
        raise SystemExit(f"missing_ledger:{ledger_path}")
    _check_sha256(ledger_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    shard_metadata = dict(summary.get("shard_metadata") or {})
    manifest_shard_metadata = dict(source_manifest.get("shard_metadata") or {})
    shard_count = int(shard_metadata.get("shard_count") or 1)
    shard_index = shard_metadata.get("shard_index")
    merged_from_shards = bool(shard_metadata.get("merged_from_shards"))
    merged_indexes = list(shard_metadata.get("merged_shard_indexes") or [])
    if shard_count < 1:
        raise SystemExit(f"invalid_shard_count:{shard_count}")
    if _normalized_shard_metadata(manifest_shard_metadata, kind="manifest") != _normalized_shard_metadata(
        shard_metadata, kind="summary"
    ):
        raise SystemExit("summary_manifest_shard_metadata_mismatch")
    is_sharded_run = bool(shard_metadata.get("is_sharded_run"))
    if merged_from_shards:
        if not is_sharded_run:
            raise SystemExit("merged_run_must_be_sharded")
        expected = list(range(shard_count))
        if sorted(int(value) for value in merged_indexes) != expected:
            raise SystemExit(f"merged_shard_coverage_invalid:{merged_indexes}:expected={expected}")
        if shard_index is not None:
            raise SystemExit(f"merged_summary_must_not_have_shard_index:{shard_index}")
    else:
        if shard_index is None:
            raise SystemExit("non_merged_summary_missing_shard_index")
        if not 0 <= int(shard_index) < shard_count:
            raise SystemExit(f"shard_index_out_of_range:{shard_index}:{shard_count}")
        if shard_count == 1 and int(shard_index) == 0:
            if is_sharded_run:
                raise SystemExit("unsharded_run_must_not_be_marked_sharded")
            if merged_indexes != [0]:
                raise SystemExit(f"unsharded_merged_indexes_invalid:{merged_indexes}")
        elif not is_sharded_run:
            raise SystemExit("child_shard_must_be_marked_sharded")
        elif merged_indexes != [int(shard_index)]:
            raise SystemExit(f"child_shard_merged_indexes_invalid:{merged_indexes}:expected={[int(shard_index)]}")
    execution_identity = {
        "strategy_id": str(contract["strategy_id"]),
        "contract_hash": str(contract["contract_hash"]),
        "contract_version": str(contract["temporal_contract_version"]),
        "production_module": str(contract["production_module"]),
        "production_callable": str(contract["production_callable"]),
        "production_file_sha256": str(contract["production_file_sha256"]),
        "requested_profile_id": str(contract["requested_profile_id"]),
        "resolved_profile_id": str(contract["resolved_profile_id"]),
        "profile_resolution_source": str(contract["profile_resolution_source"]),
        "runtime_profile_hash": str(contract["runtime_profile_hash"]),
        "dataset_manifest_hash": str(summary["dataset_manifest_hash"]),
        "inventory_sha256": str(summary.get("inventory_sha256")),
        "git_commit_sha": str(summary.get("git_commit_sha") or ""),
        "worktree_clean": bool(summary.get("worktree_clean")),
    }
    if dict(summary.get("execution_identity") or {}) != execution_identity:
        raise SystemExit("execution_identity_mismatch")
    live_git_sha, live_worktree_clean = _git_execution_state()
    if str(execution_identity.get("git_commit_sha") or "") != str(live_git_sha or ""):
        raise SystemExit("git_commit_sha_mismatch")
    if bool(execution_identity.get("worktree_clean")) is not bool(live_worktree_clean):
        raise SystemExit("worktree_clean_mismatch")
    records = list(source_manifest.get("records") or [])
    if len(records) != int(summary.get("selected_file_count") or 0):
        raise SystemExit("selected_file_count_mismatch")
    if len({_record_key(record) for record in records}) != len(records):
        raise SystemExit("duplicate_source_record")
    assignments = list(source_manifest.get("partition_assignments") or [])
    if len(assignments) != len(records):
        raise SystemExit("partition_assignment_count_mismatch")
    assignment_by_key = {
        (
            str(item.get("symbol") or ""),
            str(item.get("session_date") or ""),
            str(item.get("logical_path") or ""),
            str(item.get("selected_source_sha256") or ""),
        ): item
        for item in assignments
    }
    if len(assignment_by_key) != len(assignments):
        raise SystemExit("duplicate_partition_assignment")
    for record in records:
        assignment = assignment_by_key.get(_record_key(record))
        if assignment is None:
            raise SystemExit("partition_assignment_missing_record")
        expected_key = _canonical_session_key(record)
        if str(assignment.get("canonical_session_key") or "") != expected_key:
            raise SystemExit("partition_assignment_session_key_mismatch")
        expected_index = _partition_assignment(record, shard_count=shard_count)
        if int(assignment.get("shard_index") or -1) != expected_index:
            raise SystemExit("partition_assignment_shard_index_mismatch")
        if not merged_from_shards and int(assignment.get("shard_index") or -1) != int(shard_index):
            raise SystemExit("record_not_assigned_to_current_shard")
    manifest_selection_summary = dict(source_manifest.get("selection_summary") or {})
    if int(manifest_selection_summary.get("selected_file_count") or 0) != len(records):
        raise SystemExit("manifest_selection_count_mismatch")
    ordered_records = sorted(records, key=_record_key)
    manifest_selection_hash = hashlib.sha256(_canonical_json_bytes(ordered_records)).hexdigest()
    if manifest_selection_hash != str(manifest_selection_summary.get("semantic_hash") or ""):
        raise SystemExit("manifest_selection_hash_mismatch")
    full_source_universe = dict(source_manifest.get("full_source_universe") or {})
    if dict(summary.get("full_source_universe") or {}) != full_source_universe:
        raise SystemExit("summary_full_source_universe_mismatch")
    if int(full_source_universe.get("selected_record_count_before_sharding") or 0) < len(records):
        raise SystemExit("full_source_universe_count_invalid")
    if merged_from_shards and int(full_source_universe.get("selected_record_count_before_sharding") or 0) != len(records):
        raise SystemExit("merged_source_universe_incomplete")
    full_source_hash = hashlib.sha256(_canonical_json_bytes(ordered_records)).hexdigest()
    if merged_from_shards and full_source_hash != str(full_source_universe.get("semantic_hash") or ""):
        raise SystemExit("merged_source_universe_hash_mismatch")
    ordered_ledger = sorted(ledger, key=_ledger_key)
    if ordered_ledger != ledger:
        raise SystemExit("ledger_not_canonical_order")
    if len({_ledger_key(entry) for entry in ledger}) != len(ledger):
        raise SystemExit("duplicate_ledger_emission")
    if len(ledger) != int(summary.get("candidate_count") or 0):
        raise SystemExit("ledger_candidate_count_mismatch")
    ledger_hash = hashlib.sha256(_canonical_json_bytes(ledger)).hexdigest()
    if ledger_hash != str(summary.get("candidate_semantic_hash") or ""):
        raise SystemExit("ledger_candidate_hash_mismatch")
    candidate_counts_by_symbol: dict[str, int] = {}
    candidate_counts_by_direction: dict[str, int] = {}
    candidate_counts_by_session: dict[str, int] = {}
    for entry in ledger:
        candidate_counts_by_symbol[str(entry.get("symbol") or "")] = candidate_counts_by_symbol.get(str(entry.get("symbol") or ""), 0) + 1
        candidate_counts_by_direction[str(entry.get("direction") or "")] = candidate_counts_by_direction.get(str(entry.get("direction") or ""), 0) + 1
        candidate_counts_by_session[str(entry.get("session_date") or "")] = candidate_counts_by_session.get(str(entry.get("session_date") or ""), 0) + 1
    if dict(sorted(candidate_counts_by_symbol.items())) != dict(summary.get("candidate_counts_by_symbol") or {}):
        raise SystemExit("candidate_counts_by_symbol_mismatch")
    if dict(sorted(candidate_counts_by_direction.items())) != dict(summary.get("candidate_counts_by_direction") or {}):
        raise SystemExit("candidate_counts_by_direction_mismatch")
    if dict(sorted(candidate_counts_by_session.items())) != dict(summary.get("candidate_counts_by_session") or {}):
        raise SystemExit("candidate_counts_by_session_mismatch")
    earliest = min((str(entry.get("proposal_ready_at_iso") or "") for entry in ledger), default=None)
    latest = max((str(entry.get("proposal_ready_at_iso") or "") for entry in ledger), default=None)
    if earliest != summary.get("earliest_proposal_ready_timestamp"):
        raise SystemExit("earliest_proposal_ready_timestamp_mismatch")
    if latest != summary.get("latest_proposal_ready_timestamp"):
        raise SystemExit("latest_proposal_ready_timestamp_mismatch")
    if bool(summary.get("diagnostic_mode")) and summary.get("phase1_verdict") == "OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY":
        raise SystemExit("diagnostic_mode_cannot_certify")
    if not bool(summary.get("authoritative_inventory_resolved")) and summary.get("phase1_verdict") == "OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY":
        raise SystemExit("missing_authoritative_inventory_for_certifying_verdict")
    if int(summary["oracle_mismatch_count"]) != 0:
        raise SystemExit(f"oracle_mismatch_count_nonzero:{summary['oracle_mismatch_count']}")
    if int(summary["future_mutation_control_totals"]["failed"]) != 0:
        raise SystemExit(f"future_mutation_failures_nonzero:{summary['future_mutation_control_totals']['failed']}")
    if int(summary["future_mutation_control_totals"]["checked"]) != int(summary["future_mutation_control_totals"]["passed"]):
        raise SystemExit("future_mutation_checked_passed_mismatch")
    if int(summary["source_immutability_totals"]["mismatched"]) != 0:
        raise SystemExit(f"source_immutability_mismatches_nonzero:{summary['source_immutability_totals']['mismatched']}")
    if int(dict(summary.get("malformed_sessions_by_reason") or {}).get("rejected", 0)) != 0:
        raise SystemExit("malformed_session_rejections_nonzero")
    print(summary["phase1_verdict"])
    print(f"candidate_semantic_hash={summary['candidate_semantic_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
