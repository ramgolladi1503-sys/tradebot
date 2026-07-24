from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research.option_e2e_recertification_v4.all_strategy_source_census_v1.census import (
    build_all_strategy_census,
    verify_input_bundle,
)


def _write_bundle(bundle: Path, candidates: list[dict[str, object]], *, manifest_sha: str = "abc") -> None:
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "run_status.json").write_text(json.dumps({"status": "COMPLETE"}), encoding="utf-8")
    summary = {
        "conclusion": "SIGNAL_SOURCE_RESOLVED",
        "reason_codes": [],
        "candidate_count": len(candidates),
        "accepted_candidate_count": sum(1 for row in candidates if row.get("accepted")),
        "unresolved_candidate_count": sum(1 for row in candidates if row.get("unresolved")),
    }
    (bundle / "source_search_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    manifest = {
        "candidate_count": summary["candidate_count"],
        "accepted_candidate_count": summary["accepted_candidate_count"],
        "unresolved_candidate_count": summary["unresolved_candidate_count"],
        "semantic_sha256": manifest_sha,
    }
    (bundle / "source_search_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundle / "source_search_manifest.json.sha256").write_text(
        f"{manifest_sha}  source_search_manifest.json\n", encoding="utf-8"
    )
    (bundle / "root_inventory.json").write_text(
        json.dumps([{"root_id": "ROOT", "available": True, "is_directory": True}]),
        encoding="utf-8",
    )
    (bundle / "git_search_manifest.json").write_text("[]", encoding="utf-8")
    with (bundle / "candidate_inventory.jsonl").open("w", encoding="utf-8") as handle:
        for row in candidates:
            handle.write(json.dumps(row) + "\n")


def test_verify_input_bundle_detects_counts_and_sidecar(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _write_bundle(
        bundle,
        [
            {
                "accepted": True,
                "unresolved": False,
                "sha256": "a",
                "classification": "UNDERLYING_CANDLE_DATASET",
                "size": 1,
            },
            {
                "accepted": False,
                "unresolved": True,
                "sha256": "b",
                "classification": "OVERSIZED_CANDIDATE",
                "size": 2,
            },
        ],
    )

    integrity = verify_input_bundle(bundle)

    assert integrity.status == "INPUT_BUNDLE_INTEGRITY_PASSED"
    assert integrity.candidate_count == 2
    assert integrity.accepted_candidate_count == 1
    assert integrity.unresolved_candidate_count == 1


def test_census_collapses_duplicates_and_flags_minimal_ledgers(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "strategies").mkdir()
    strategy = repo / "strategies" / "vwap_reclaim.py"
    strategy.write_text("def run():\n    return 1\n", encoding="utf-8")

    bundle = tmp_path / "bundle"
    _write_bundle(
        bundle,
        [
            {
                "root_id": "A",
                "relative_path": "data/NIFTY.csv",
                "accepted": True,
                "unresolved": False,
                "sha256": "dup",
                "classification": "UNDERLYING_CANDLE_DATASET",
                "size": 10,
                "row_count": 1,
            },
            {
                "root_id": "B",
                "relative_path": "copy/NIFTY.csv",
                "accepted": True,
                "unresolved": False,
                "sha256": "dup",
                "classification": "UNDERLYING_CANDLE_DATASET",
                "size": 10,
                "row_count": 1,
            },
            {
                "root_id": "A",
                "relative_path": "signals/minimal.jsonl",
                "accepted": False,
                "unresolved": False,
                "sha256": "sig",
                "classification": "PRE_OUTCOME_SIGNAL_LEDGER",
                "size": 12,
                "row_count": 1,
                "columns": [
                    "strategy_or_hypothesis_id",
                    "signal_id",
                    "signal_ts",
                    "earliest_entry_ts",
                    "direction",
                ],
            },
        ],
    )

    output = tmp_path / "output"
    summary = build_all_strategy_census(bundle, repo, output)

    exact = json.loads((output / "exact_duplicate_groups.jsonl").read_text(encoding="utf-8"))
    semantic = json.loads((output / "semantic_duplicate_groups.jsonl").read_text(encoding="utf-8"))
    ledgers = json.loads((output / "canonical_signal_ledger_registry.json").read_text(encoding="utf-8"))
    families = json.loads((output / "logical_dataset_family_registry.json").read_text(encoding="utf-8"))
    versions = json.loads((output / "dataset_version_registry.json").read_text(encoding="utf-8"))
    readiness = json.loads((output / "all_strategy_execution_readiness.json").read_text(encoding="utf-8"))

    assert summary["raw_candidates"] == 3
    assert summary["exact_unique_sources"] == 1
    assert exact[0]["copy_count"] == 2
    assert exact[0]["selected_canonical_copy"]["relative_path"] == "data/NIFTY.csv"
    assert semantic[0]["copy_count"] == 2
    assert ledgers[0]["status"] == "INVALID_SIGNAL_LEDGER"
    assert families[0]["dataset_family_id"] == "FAMILY:NIFTY_SPOT:spot:NSE:unknown"
    assert versions[0]["status"] == "UNRESOLVED_DATASET_VERSION"
    assert summary["logical_dataset_families"] == 1
    assert summary["dataset_versions"] == 1
    assert any(row["canonical_strategy_id"] == "VWAP_RECLAIM" for row in readiness)
    assert summary["implementation_direction"] == "PROVISIONAL_CENSUS_WITH_DECLARED_GAPS"
    assert summary["canonical_signal_ledgers"] == 0
    assert summary["ready_for_causal_execution_lanes"] == 0
    assert summary["valid_precomputed_signals_lanes"] == 0
    assert summary["blocked_lanes"] >= 1
    assert summary["canonical_dataset_version_count"] == 0
    assert summary["logical_dataset_family_count"] == 1
    assert summary["dataset_version_count"] == 1
    assert "fixed_economics" not in summary
    assert summary["raw_candidates"] != 4


def test_canonical_selection_is_independent_of_input_order(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    bundle = tmp_path / "bundle"
    _write_bundle(
        bundle,
        [
            {
                "root_id": "B",
                "relative_path": "copy/NIFTY.csv",
                "accepted": True,
                "unresolved": False,
                "sha256": "dup",
                "classification": "UNDERLYING_CANDLE_DATASET",
                "size": 10,
                "row_count": 1,
            },
            {
                "root_id": "A",
                "relative_path": "data/NIFTY.csv",
                "accepted": True,
                "unresolved": False,
                "sha256": "dup",
                "classification": "UNDERLYING_CANDLE_DATASET",
                "size": 10,
                "row_count": 1,
            },
        ],
    )

    out_one = tmp_path / "out_one"
    out_two = tmp_path / "out_two"
    build_all_strategy_census(bundle, repo, out_one)
    build_all_strategy_census(bundle, repo, out_two)

    first = json.loads((out_one / "logical_dataset_family_registry.json").read_text(encoding="utf-8"))
    second = json.loads((out_two / "logical_dataset_family_registry.json").read_text(encoding="utf-8"))

    assert first == second
    assert first[0]["partition_count"] == 2


def test_committed_compact_evidence_contract_is_self_consistent() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    compact = (
        repo_root
        / "research"
        / "option_e2e_recertification_v4"
        / "all_strategy_source_census_v1"
    )
    names = (
        "schema.json",
        "census_summary.json",
        "dataset_family_summary.json",
        "dataset_version_summary.json",
        "signal_ledger_summary.json",
        "execution_readiness_summary.json",
        "external_evidence_manifest.json",
    )

    for name in names:
        artifact = compact / name
        sidecar = compact / f"{name}.sha256"
        expected_sha = sidecar.read_text(encoding="utf-8").split()[0]
        actual_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert actual_sha == expected_sha

    summary = json.loads((compact / "census_summary.json").read_text(encoding="utf-8"))
    family_summary = json.loads((compact / "dataset_family_summary.json").read_text(encoding="utf-8"))
    version_summary = json.loads((compact / "dataset_version_summary.json").read_text(encoding="utf-8"))
    ledger_summary = json.loads((compact / "signal_ledger_summary.json").read_text(encoding="utf-8"))
    readiness_summary = json.loads((compact / "execution_readiness_summary.json").read_text(encoding="utf-8"))

    assert summary["raw_candidates"] == 6119
    assert family_summary["raw_candidate_file_count"] == summary["raw_candidates"]
    assert family_summary["logical_dataset_family_count"] == 8
    assert version_summary["dataset_version_count"] == 986
    assert version_summary["canonical_dataset_version_count"] == 0
    assert ledger_summary["canonical_signal_ledger_count"] == 0
    assert readiness_summary["ready_for_causal_execution_lanes"] == 0
    assert readiness_summary["valid_precomputed_signals_lanes"] == 0
    assert summary["implementation_direction"] == "PROVISIONAL_CENSUS_WITH_DECLARED_GAPS"
    assert "canonical_dataset_count" not in summary
