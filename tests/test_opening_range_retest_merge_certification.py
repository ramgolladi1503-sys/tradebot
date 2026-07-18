from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from research.opening_range_retest.replay_contract import build_replay_contract_matrix, canonical_json_bytes
from research.opening_range_retest.replay_engine import (
    CONTRACT_ARTIFACT_FILENAME,
    LEDGER_ARTIFACT_FILENAME,
    SOURCE_MANIFEST_ARTIFACT_FILENAME,
    SUMMARY_ARTIFACT_FILENAME,
    merge_replay_artifacts,
)
from research.opening_range_retest.replay_controls import ReplaySourceSelectionError


def _summary_to_manifest_shard_metadata(summary_metadata: dict[str, object]) -> dict[str, object]:
    return {
        "shard_count": summary_metadata.get("shard_count"),
        "shard_index": summary_metadata.get("shard_index"),
        "is_sharded_run": summary_metadata.get("is_sharded_run"),
        "merged_from_shards": summary_metadata.get("merged_from_shards", False),
        "selected_record_count_before_sharding": summary_metadata.get("selected_file_count_before_sharding"),
        "selected_record_count_after_sharding": summary_metadata.get("selected_file_count_after_sharding"),
        "merged_shard_indexes": list(summary_metadata.get("merged_shard_indexes") or []),
    }


def _normalized_for_contract(metadata: dict[str, object], *, kind: str) -> dict[str, object]:
    if kind == "summary":
        before = metadata.get("selected_file_count_before_sharding")
        after = metadata.get("selected_file_count_after_sharding")
    elif kind == "manifest":
        before = metadata.get("selected_record_count_before_sharding")
        after = metadata.get("selected_record_count_after_sharding")
    else:
        raise ValueError(kind)
    return {
        "shard_count": metadata.get("shard_count"),
        "shard_index": metadata.get("shard_index"),
        "is_sharded_run": metadata.get("is_sharded_run"),
        "merged_from_shards": metadata.get("merged_from_shards", False),
        "selected_count_before_sharding": before,
        "selected_count_after_sharding": after,
        "merged_shard_indexes": list(metadata.get("merged_shard_indexes") or []),
    }


def _write_sidecar(path: Path) -> None:
    sha = hashlib.sha256(path.read_bytes().rstrip(b"\n")).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(f"{sha}  {path.name}\n", encoding="utf-8")


def _rewrite_json(path: Path, payload: object) -> None:
    path.write_bytes(canonical_json_bytes(payload) + b"\n")


def _align_summary_to_live_git_state(artifact_dir: Path) -> None:
    summary_path = artifact_dir / SUMMARY_ARTIFACT_FILENAME
    contract = build_replay_contract_matrix().to_dict()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    live_sha = subprocess.check_output(
        ["git", "-C", str(Path(__file__).resolve().parents[1]), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    live_clean = not bool(
        subprocess.check_output(
            ["git", "-C", str(Path(__file__).resolve().parents[1]), "status", "--porcelain=v1"],
            text=True,
        ).splitlines()
    )
    summary["git_commit_sha"] = live_sha
    summary["worktree_clean"] = live_clean
    summary["execution_identity"] = {
        **_execution_identity(contract, inventory_sha256=str(summary["inventory_sha256"])),
        "git_commit_sha": live_sha,
        "worktree_clean": live_clean,
    }
    _rewrite_json(summary_path, summary)
    _write_sidecar(summary_path)


def _record(*, symbol: str, session_date: str, logical_path: str, source_root: str, sha256: str) -> dict[str, object]:
    return {
        "absolute_path": f"/tmp/{logical_path}",
        "logical_path": logical_path,
        "symbol": symbol,
        "session_date": session_date,
        "source_root": source_root,
        "sha256": sha256,
        "row_count": 375,
        "byte_size": 1024,
        "projected_columns": ["timestamp", "symbol", "open", "high", "low", "close", "volume"],
        "selected_via": "inventory_verified_repo_relative",
    }


def _selection_summary(records: list[dict[str, object]]) -> dict[str, object]:
    ordered = sorted(records, key=lambda item: (str(item["symbol"]), str(item["session_date"]), str(item["logical_path"]), str(item["sha256"])))
    symbol_counts: dict[str, int] = {}
    for record in ordered:
        symbol_counts[str(record["symbol"])] = symbol_counts.get(str(record["symbol"]), 0) + 1
    return {
        "selected_file_count": len(ordered),
        "symbol_counts": dict(sorted(symbol_counts.items())),
        "earliest_session": min((str(record["session_date"]) for record in ordered), default=None),
        "latest_session": max((str(record["session_date"]) for record in ordered), default=None),
        "selected_via": {"inventory_verified_repo_relative": len(ordered)},
        "projected_columns": ["timestamp", "symbol", "open", "high", "low", "close", "volume"],
        "semantic_hash": hashlib.sha256(canonical_json_bytes(ordered)).hexdigest(),
    }


def _execution_identity(contract: dict[str, object], *, inventory_sha256: str) -> dict[str, str]:
    return {
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
        "dataset_manifest_hash": str(contract["dataset_manifest_sha256"]),
        "inventory_sha256": inventory_sha256,
        "git_commit_sha": "f743620eda4eafccaff43a1ae70a7a7336f839d2",
        "worktree_clean": True,
    }


def _ledger_entry(
    *,
    symbol: str,
    session_date: str,
    direction: str,
    proposal_ready_at_iso: str,
    setup_id: str,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "session_date": session_date,
        "direction": direction,
        "proposal_ready_at_iso": proposal_ready_at_iso,
        "setup_id": setup_id,
        "history_hash": f"history-{setup_id}",
        "raw_score": 1.0,
        "semantic_payload": {
            "strategy_id": "opening_range_retest_v1",
            "symbol": symbol,
            "direction": direction,
            "status": "TRUTHFUL",
            "raw_score": 1.0,
            "entry_trigger": "continuation",
            "invalid_if": "orb_break_fails",
            "rank_reason": "certification-test",
            "proposal_ready_at_iso": proposal_ready_at_iso,
            "setup_id": setup_id,
            "history_hash": f"history-{setup_id}",
        },
    }


def _build_shard_artifacts(tmp_path: Path, *, shard_count: int = 2) -> list[Path]:
    contract = build_replay_contract_matrix().to_dict()
    inventory_sha = "1" * 64
    inventory_resolution = {
        "original_inventory_provenance_path": "/tmp/upstox_corpus_inventory_v2.json",
        "resolved_inventory_path": "/tmp/upstox_corpus_inventory_v2.json",
        "inventory_sha256": inventory_sha,
        "inventory_sidecar_verification": True,
        "inventory_resolution_mode": "repo_relative_canonical",
    }
    combined_records = [
        _record(
            symbol="BANKNIFTY",
            session_date="2026-07-15",
            logical_path="runtime/upstox_candidate_replay/20260715/underlying/BANKNIFTY_20260715.parquet",
            source_root="/tmp/runtime/upstox_candidate_replay",
            sha256="b" * 64,
        ),
        _record(
            symbol="NIFTY",
            session_date="2026-07-14",
            logical_path="runtime/upstox_candidate_replay/20260714/underlying/NIFTY_20260714.parquet",
            source_root="/tmp/runtime/upstox_candidate_replay",
            sha256="a" * 64,
        ),
    ]
    combined_records = sorted(
        combined_records,
        key=lambda item: (str(item["symbol"]), str(item["session_date"]), str(item["logical_path"]), str(item["sha256"])),
    )
    full_source_universe = {
        "selected_record_count_before_sharding": len(combined_records),
        "semantic_hash": hashlib.sha256(canonical_json_bytes(combined_records)).hexdigest(),
    }
    shard_ledgers = {
        0: [
            _ledger_entry(
                symbol="BANKNIFTY",
                session_date="2026-07-15",
                direction="BUY_CALL",
                proposal_ready_at_iso="2026-07-15T09:34:00+05:30",
                setup_id="setup-banknifty",
            )
        ],
        1: [
            _ledger_entry(
                symbol="NIFTY",
                session_date="2026-07-14",
                direction="BUY_CALL",
                proposal_ready_at_iso="2026-07-14T09:34:00+05:30",
                setup_id="setup-nifty",
            )
        ],
    }
    artifact_dirs: list[Path] = []
    for shard_index in range(shard_count):
        shard_records = [record for index, record in enumerate(combined_records) if index % shard_count == shard_index]
        ledger = shard_ledgers.get(shard_index, [])
        candidate_hash = hashlib.sha256(canonical_json_bytes(ledger)).hexdigest()
        is_sharded_run = shard_count > 1
        source_manifest = {
            "schema_version": 1,
            "strategy_id": contract["strategy_id"],
            "inventory_resolution": inventory_resolution,
            "records": shard_records,
            "partition_assignments": [
                {
                    "symbol": record["symbol"],
                    "session_date": record["session_date"],
                    "logical_path": record["logical_path"],
                    "selected_source_sha256": record["sha256"],
                    "canonical_session_key": canonical_json_bytes(
                        {
                            "logical_path": record["logical_path"],
                            "selected_source_sha256": record["sha256"],
                            "session_date": record["session_date"],
                            "symbol": record["symbol"],
                        }
                    ).decode("utf-8"),
                    "shard_index": shard_index,
                }
                for record in shard_records
            ],
            "selection_summary": _selection_summary(shard_records),
            "full_source_universe": dict(full_source_universe),
            "shard_metadata": {
                "shard_count": shard_count,
                "shard_index": shard_index,
                "is_sharded_run": is_sharded_run,
                "selected_record_count_before_sharding": len(combined_records),
                "selected_record_count_after_sharding": len(shard_records),
                "merged_from_shards": False,
                "merged_shard_indexes": [shard_index],
            },
        }
        summary_shard_metadata = {
            "shard_count": shard_count,
            "shard_index": shard_index,
            "is_sharded_run": is_sharded_run,
            "merged_from_shards": False,
            "selected_file_count_before_sharding": len(combined_records),
            "selected_file_count_after_sharding": len(shard_records),
            "merged_shard_indexes": [shard_index],
        }
        summary = {
            "schema_version": 1,
            "contract_version": contract["temporal_contract_version"],
            "production_strategy_module": contract["production_module"],
            "production_callable": contract["production_callable"],
            "production_file_sha256": contract["production_file_sha256"],
            "runtime_profile_hash": contract["runtime_profile_hash"],
            "dataset_manifest_hash": contract["dataset_manifest_sha256"],
            **inventory_resolution,
            "source_root_identifiers": sorted({str(record["source_root"]) for record in shard_records}),
            "selected_file_count": len(shard_records),
            "rejected_file_count_by_reason": {"malformed_or_unreadable": 0},
            "parquet_read_count": len(shard_records),
            "projected_columns": ["timestamp", "symbol", "open", "high", "low", "close", "volume"],
            "bytes_read": 1024 * len(shard_records),
            "symbol_session_counts": {
                f"{record['symbol']}:{record['session_date']}": 1 for record in shard_records
            },
            "valid_sessions_by_symbol": {
                str(record["symbol"]): 1 for record in shard_records
            },
            "malformed_sessions_by_reason": {"rejected": 0},
            "candidate_count": len(ledger),
            "candidate_counts_by_symbol": {
                str(entry["symbol"]): 1 for entry in ledger
            },
            "candidate_counts_by_direction": {
                str(entry["direction"]): 1 for entry in ledger
            },
            "candidate_counts_by_session": {
                str(entry["session_date"]): 1 for entry in ledger
            },
            "duplicate_suppressions": 0,
            "earliest_session": min((str(record["session_date"]) for record in shard_records), default=None),
            "latest_session": max((str(record["session_date"]) for record in shard_records), default=None),
            "earliest_proposal_ready_timestamp": min((str(entry["proposal_ready_at_iso"]) for entry in ledger), default=None),
            "latest_proposal_ready_timestamp": max((str(entry["proposal_ready_at_iso"]) for entry in ledger), default=None),
            "oracle_reconciliation_totals": {"checked": 1, "matched": 1, "mismatched": 0},
            "oracle_mismatch_count": 0,
            "causal_control_totals": {"prefix_replay_sessions": len(shard_records), "backdated_candidate_violations": 0},
            "future_mutation_control_totals": {"checked": len(ledger), "passed": len(ledger), "failed": 0},
            "source_immutability_totals": {
                "checked": len(shard_records),
                "mismatched": 0,
                "status": "not_mutated",
            },
            "two_directory_determinism_hashes": {
                "contract_hash": contract["contract_hash"],
                "selected_source_manifest_hash": source_manifest["selection_summary"]["semantic_hash"],
                "candidate_semantic_hash": candidate_hash,
            },
            "file_profiles": [],
            "elapsed_runtime_seconds": 0.01,
            "peak_memory_bytes": 1024,
            "limitations": [
                "Signal replay only.",
                "Underlying-candle replay uses VWAP proxy where exact truth is unavailable.",
                "No option execution, fill, slippage, or profitability claim.",
            ],
            "claim_boundary": contract["source_data_claim_boundary"],
            "authoritative_inventory_resolved": True,
            "diagnostic_mode": False,
            "git_commit_sha": "f743620eda4eafccaff43a1ae70a7a7336f839d2",
            "worktree_clean": True,
            "phase1_verdict": "OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY",
            "candidate_semantic_hash": candidate_hash,
            "execution_identity": _execution_identity(contract, inventory_sha256=inventory_sha),
            "full_source_universe": dict(full_source_universe),
            "shard_metadata": summary_shard_metadata,
        }
        summary["canonical_summary_semantic_hash"] = hashlib.sha256(
            canonical_json_bytes(
                {
                    key: value
                    for key, value in summary.items()
                    if key not in {"file_profiles", "elapsed_runtime_seconds", "peak_memory_bytes", "canonical_summary_semantic_hash", "shard_metadata"}
                }
            )
        ).hexdigest()
        artifact_dir = tmp_path / f"artifacts-shard-{shard_index}"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        for filename, payload in (
            (CONTRACT_ARTIFACT_FILENAME, contract),
            (SOURCE_MANIFEST_ARTIFACT_FILENAME, source_manifest),
            (SUMMARY_ARTIFACT_FILENAME, summary),
            (LEDGER_ARTIFACT_FILENAME, ledger),
        ):
            path = artifact_dir / filename
            _rewrite_json(path, payload)
            _write_sidecar(path)
        artifact_dirs.append(artifact_dir)
    return artifact_dirs


def test_merge_replay_artifacts_requires_complete_consistent_authoritative_shards(tmp_path: Path) -> None:
    artifact_dirs = _build_shard_artifacts(tmp_path)

    merged = merge_replay_artifacts(shard_artifact_dirs=artifact_dirs)

    assert merged.summary["phase1_verdict"] == "OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY"
    assert merged.summary["execution_identity"]["strategy_id"] == "opening_range_retest_v1"
    assert merged.summary["shard_metadata"]["merged_from_shards"] is True
    assert merged.summary["full_source_universe"]["selected_record_count_before_sharding"] == 2
    assert merged.source_manifest["selection_summary"]["selected_file_count"] == 2
    assert _normalized_for_contract(merged.summary["shard_metadata"], kind="summary") == _normalized_for_contract(
        merged.source_manifest["shard_metadata"],
        kind="manifest",
    )


def test_shard_metadata_contract_for_unsharded_child_and_merged_states(tmp_path: Path) -> None:
    unsharded_summary = {
        "shard_count": 1,
        "shard_index": 0,
        "is_sharded_run": False,
        "merged_from_shards": False,
        "selected_file_count_before_sharding": 5,
        "selected_file_count_after_sharding": 5,
        "merged_shard_indexes": [0],
    }
    unsharded_manifest = _summary_to_manifest_shard_metadata(unsharded_summary)
    assert _normalized_for_contract(unsharded_summary, kind="summary") == _normalized_for_contract(
        unsharded_manifest,
        kind="manifest",
    )

    child_summary = {
        "shard_count": 12,
        "shard_index": 3,
        "is_sharded_run": True,
        "merged_from_shards": False,
        "selected_file_count_before_sharding": 1512,
        "selected_file_count_after_sharding": 126,
        "merged_shard_indexes": [3],
    }
    child_manifest = _summary_to_manifest_shard_metadata(child_summary)
    assert _normalized_for_contract(child_summary, kind="summary") == _normalized_for_contract(
        child_manifest,
        kind="manifest",
    )

    artifact_dirs = _build_shard_artifacts(tmp_path, shard_count=2)
    merged = merge_replay_artifacts(shard_artifact_dirs=artifact_dirs)
    assert merged.summary["shard_metadata"] == {
        "shard_count": 2,
        "shard_index": None,
        "is_sharded_run": True,
        "partition_rule": "sha256(canonical_session_key) mod shard_count",
        "merged_from_shards": True,
        "selected_file_count_before_sharding": 2,
        "selected_file_count_after_sharding": 2,
        "merged_shard_indexes": [0, 1],
    }
    assert _normalized_for_contract(merged.summary["shard_metadata"], kind="summary") == _normalized_for_contract(
        merged.source_manifest["shard_metadata"],
        kind="manifest",
    )


def test_merge_replay_artifacts_fails_closed_on_tampered_ledger(tmp_path: Path) -> None:
    artifact_dirs = _build_shard_artifacts(tmp_path)
    ledger_path = artifact_dirs[0] / LEDGER_ARTIFACT_FILENAME
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger[0]["setup_id"] = f"{ledger[0]['setup_id']}-tampered"
    _rewrite_json(ledger_path, ledger)

    with pytest.raises(ReplaySourceSelectionError, match="artifact_sidecar_hash_mismatch"):
        merge_replay_artifacts(shard_artifact_dirs=artifact_dirs)


def test_merge_replay_artifacts_fails_closed_on_missing_ledger_sidecar(tmp_path: Path) -> None:
    artifact_dirs = _build_shard_artifacts(tmp_path)
    ledger_sidecar = artifact_dirs[0] / f"{LEDGER_ARTIFACT_FILENAME}.sha256"
    ledger_sidecar.unlink()

    with pytest.raises(ReplaySourceSelectionError, match="missing_sidecar"):
        merge_replay_artifacts(shard_artifact_dirs=artifact_dirs)


def test_merge_replay_artifacts_fails_closed_on_dirty_certifying_shard(tmp_path: Path) -> None:
    artifact_dirs = _build_shard_artifacts(tmp_path)
    summary_path = artifact_dirs[0] / SUMMARY_ARTIFACT_FILENAME
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["worktree_clean"] = False
    summary["execution_identity"]["worktree_clean"] = False
    _rewrite_json(summary_path, summary)
    _write_sidecar(summary_path)

    with pytest.raises(ReplaySourceSelectionError, match="dirty_shard_cannot_merge"):
        merge_replay_artifacts(shard_artifact_dirs=artifact_dirs)


def test_merge_replay_artifacts_fails_closed_on_mixed_code_sha(tmp_path: Path) -> None:
    artifact_dirs = _build_shard_artifacts(tmp_path)
    summary_path = artifact_dirs[1] / SUMMARY_ARTIFACT_FILENAME
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["git_commit_sha"] = "deadbeef"
    summary["execution_identity"]["git_commit_sha"] = "deadbeef"
    _rewrite_json(summary_path, summary)
    _write_sidecar(summary_path)

    with pytest.raises(ReplaySourceSelectionError, match="code_sha_mismatch_across_shards|execution_identity_mismatch"):
        merge_replay_artifacts(shard_artifact_dirs=artifact_dirs)


def test_merge_replay_artifacts_fails_closed_on_candidate_count_mismatch(tmp_path: Path) -> None:
    artifact_dirs = _build_shard_artifacts(tmp_path)
    summary_path = artifact_dirs[0] / SUMMARY_ARTIFACT_FILENAME
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["candidate_count"] = 99
    _rewrite_json(summary_path, summary)
    _write_sidecar(summary_path)

    with pytest.raises(ReplaySourceSelectionError, match="ledger_candidate_count_mismatch|execution_identity_mismatch"):
        merge_replay_artifacts(shard_artifact_dirs=artifact_dirs)


def test_merge_replay_artifacts_fails_closed_on_source_universe_mismatch(tmp_path: Path) -> None:
    artifact_dirs = _build_shard_artifacts(tmp_path)
    source_manifest_path = artifact_dirs[1] / SOURCE_MANIFEST_ARTIFACT_FILENAME
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_manifest["full_source_universe"]["semantic_hash"] = "0" * 64
    _rewrite_json(source_manifest_path, source_manifest)
    _write_sidecar(source_manifest_path)

    with pytest.raises(ReplaySourceSelectionError, match="source_universe_hash_mismatch"):
        merge_replay_artifacts(shard_artifact_dirs=artifact_dirs)


@pytest.mark.parametrize(
    ("target_file", "metadata_field", "tampered_value", "expected"),
    (
        (SOURCE_MANIFEST_ARTIFACT_FILENAME, "shard_count", 2, "summary_manifest_shard_metadata_mismatch"),
        (SUMMARY_ARTIFACT_FILENAME, "shard_count", 2, "summary_manifest_shard_metadata_mismatch"),
        (SUMMARY_ARTIFACT_FILENAME, "shard_index", 1, "summary_manifest_shard_metadata_mismatch"),
        (SUMMARY_ARTIFACT_FILENAME, "is_sharded_run", True, "summary_manifest_shard_metadata_mismatch"),
        (SUMMARY_ARTIFACT_FILENAME, "merged_from_shards", True, "summary_manifest_shard_metadata_mismatch"),
        (SUMMARY_ARTIFACT_FILENAME, "merged_shard_indexes", [], "summary_manifest_shard_metadata_mismatch"),
        (SUMMARY_ARTIFACT_FILENAME, "merged_shard_indexes", [0, 0], "summary_manifest_shard_metadata_mismatch"),
        (SUMMARY_ARTIFACT_FILENAME, "selected_file_count_before_sharding", 99, "summary_manifest_shard_metadata_mismatch"),
        (SUMMARY_ARTIFACT_FILENAME, "selected_file_count_after_sharding", 99, "summary_manifest_shard_metadata_mismatch"),
    ),
)
def test_artifact_auditor_rejects_shard_metadata_mismatches(
    tmp_path: Path,
    target_file: str,
    metadata_field: str,
    tampered_value: object,
    expected: str,
) -> None:
    artifact_dir = _build_shard_artifacts(tmp_path, shard_count=1)[0]
    target_path = artifact_dir / target_file
    payload = json.loads(target_path.read_text(encoding="utf-8"))
    payload["shard_metadata"][metadata_field] = tampered_value
    _rewrite_json(target_path, payload)
    _write_sidecar(target_path)

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts" / "audit_opening_range_retest_causal_replay.py"),
            "--artifact-dir",
            str(artifact_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    assert expected in proc.stderr


@pytest.mark.parametrize(
    ("summary_updates", "expected"),
    (
        ({"is_sharded_run": True}, "unsharded_run_must_not_be_marked_sharded"),
        ({"shard_count": 2, "shard_index": 0, "is_sharded_run": False, "merged_shard_indexes": [0]}, "child_shard_must_be_marked_sharded"),
        ({"shard_count": 2, "shard_index": 0, "is_sharded_run": True, "merged_shard_indexes": [1]}, "child_shard_merged_indexes_invalid"),
    ),
)
def test_artifact_auditor_rejects_internally_matching_illegal_shard_states(
    tmp_path: Path,
    summary_updates: dict[str, object],
    expected: str,
) -> None:
    artifact_dir = _build_shard_artifacts(tmp_path, shard_count=1)[0]
    summary_path = artifact_dir / SUMMARY_ARTIFACT_FILENAME
    manifest_path = artifact_dir / SOURCE_MANIFEST_ARTIFACT_FILENAME
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary["shard_metadata"].update(summary_updates)
    manifest["shard_metadata"].update(_summary_to_manifest_shard_metadata(summary["shard_metadata"]))
    _rewrite_json(summary_path, summary)
    _write_sidecar(summary_path)
    _rewrite_json(manifest_path, manifest)
    _write_sidecar(manifest_path)

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts" / "audit_opening_range_retest_causal_replay.py"),
            "--artifact-dir",
            str(artifact_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    assert expected in proc.stderr


@pytest.mark.parametrize(
    ("mutator", "expected"),
    (
        (
            lambda manifest: manifest["partition_assignments"].pop(),
            "partition_assignment_count_mismatch",
        ),
        (
            lambda manifest: manifest["partition_assignments"][0].update({"canonical_session_key": "{}"}),
            "partition_assignment_session_key_mismatch",
        ),
        (
            lambda manifest: manifest["partition_assignments"][0].update({"shard_index": 99}),
            "partition_assignment_shard_index_mismatch",
        ),
    ),
)
def test_artifact_auditor_rejects_partition_assignment_mismatches(
    tmp_path: Path,
    mutator,
    expected: str,
) -> None:
    artifact_dir = _build_shard_artifacts(tmp_path, shard_count=1)[0]
    _align_summary_to_live_git_state(artifact_dir)
    manifest_path = artifact_dir / SOURCE_MANIFEST_ARTIFACT_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutator(manifest)
    _rewrite_json(manifest_path, manifest)
    _write_sidecar(manifest_path)

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts" / "audit_opening_range_retest_causal_replay.py"),
            "--artifact-dir",
            str(artifact_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    assert expected in proc.stderr


def test_artifact_audit_fails_closed_on_tampered_ledger(tmp_path: Path) -> None:
    artifact_dir = _build_shard_artifacts(tmp_path, shard_count=1)[0]
    ledger_path = artifact_dir / LEDGER_ARTIFACT_FILENAME
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger[0]["setup_id"] = f"{ledger[0]['setup_id']}-tampered"
    _rewrite_json(ledger_path, ledger)

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts" / "audit_opening_range_retest_causal_replay.py"),
            "--artifact-dir",
            str(artifact_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    assert "sha256_mismatch" in proc.stderr or "artifact_sidecar_hash_mismatch" in proc.stderr
