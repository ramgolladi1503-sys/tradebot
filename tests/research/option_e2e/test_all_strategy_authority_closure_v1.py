from __future__ import annotations

import json
import hashlib
from pathlib import Path

from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1 import (
    build_all_strategy_authority_closure,
    load_all_strategy_authority_closure,
)


RUN_A = Path("/Users/madhuram/tradebot-ml-evidence/all-strategy-option-e2e-recertification-v4/all_strategy_source_census_v1/20260724-133422_family_model")
RUN_B = Path("/Users/madhuram/tradebot-ml-evidence/all-strategy-option-e2e-recertification-v4/all_strategy_source_census_v1/20260724-133424_family_model_rerun")


def _semantic_sha(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def test_full_registry_runs_are_semantically_identical() -> None:
    required = (
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

    for name in required:
        assert (RUN_A / name).exists()
        assert (RUN_B / name).exists()
        assert _semantic_sha(RUN_A / name) == _semantic_sha(RUN_B / name)


def test_closure_uses_published_census_counts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    output = tmp_path / "closure"

    result = build_all_strategy_authority_closure(repo_root, output)

    integrity = json.loads((output / "input_census_integrity.json").read_text(encoding="utf-8"))
    families = json.loads((output / "dataset_family_authority_reviews.json").read_text(encoding="utf-8"))
    versions = json.loads((output / "dataset_version_authority_decisions.json").read_text(encoding="utf-8"))
    matrix = json.loads((output / "all_strategy_authority_matrix.json").read_text(encoding="utf-8"))
    blockers = json.loads((output / "authority_blocker_ledger.json").read_text(encoding="utf-8"))
    breakdown = json.loads((output / "input_census_integrity.json").read_text(encoding="utf-8"))

    assert integrity["status"] == "INPUT_BUNDLE_INTEGRITY_PASSED"
    assert breakdown["candidate_count"] == 6119
    assert breakdown["accepted_candidate_count"] == 1055
    assert breakdown["unresolved_candidate_count"] == 24
    assert result["input_census_integrity"]["candidate_count"] == 6119
    assert result["authority_status"] == "BLOCKED_WITH_DECLARED_GAPS"
    assert result["dataset_family_count"] == 8
    assert result["dataset_version_count"] == 986
    assert result["ready_for_causal_execution_lanes"] == 0
    assert result["valid_precomputed_signals_lanes"] == 0
    assert families[0]["dataset_family_id"] == "FAMILY:BANKNIFTY:spot:NSE:unknown"
    assert families[7]["dataset_family_id"] == "FAMILY:UNRESOLVED_FAMILY:unknown:unknown:unknown"
    assert sum(1 for row in families if row["authority_status"] == "BLOCKED_WITH_LIMITATIONS") == 8
    assert sum(1 for row in families if row["authority_status"] == "BLOCKED") == 0
    assert versions[985]["dataset_version_id"].startswith("VERSION:FAMILY:")
    assert sum(1 for row in versions if row["authority_status"] == "UNRESOLVED_DATASET_VERSION") == 961
    assert sum(1 for row in versions if row["authority_status"] == "USABLE_WITH_LIMITATIONS") == 25
    assert matrix[-1]["authority_target"] == "strategy_execution"
    assert any(row["authority_target"] == "VWAP_RECLAIM" for row in matrix)
    assert blockers[0]["blocker_class"] == "INSUFFICIENT_SIGNAL_PROVENANCE"
    assert blockers[0]["blocked_lane_count"] == 7
    assert blockers[1]["blocked_lane_count"] == 1
    assert blockers[2]["blocked_lane_count"] == 8
    assert integrity["status"] != "INPUT_BUNDLE_INTEGRITY_FAILED"
    assert result["blocked_lane_count"] != 0


def test_aeron7_and_signal_reviews_fail_closed(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    output = tmp_path / "closure"
    build_all_strategy_authority_closure(repo_root, output)

    aeron7 = json.loads((output / "aeron7_nifty_f1_authority_review.json").read_text(encoding="utf-8"))
    unresolved = json.loads((output / "unresolved_source_authority_review.json").read_text(encoding="utf-8"))
    signal = json.loads((output / "signal_ledger_authority_review.json").read_text(encoding="utf-8"))
    prioritization = json.loads((output / "strategy_authority_prioritization.json").read_text(encoding="utf-8"))

    assert aeron7["authority_status"] == "BLOCKED_WITH_LIMITATIONS"
    assert aeron7["dataset_family_id"] == "FAMILY:NIFTY_F1:futures:NSE:1m"
    assert aeron7["dataset_family"][0]["exact_copy_count"] == 68
    assert unresolved["authority_status"] == "BLOCKED"
    assert unresolved["unresolved_candidate_count"] == 24
    assert unresolved["material_truncated_roots"] == 27
    assert unresolved["unresolved_candidate_resolution"][0]["input_unresolved_count"] == 24
    assert signal["authority_status"] == "BLOCKED"
    assert signal["canonical_signal_ledger_count"] == 0
    assert signal["insufficient_provenance_ledgers"] == 1
    assert signal["canonical_signal_ledger_registry"][0]["status"] == "INSUFFICIENT_PROVENANCE"
    assert prioritization[0]["remaining_blocker"] == "INSUFFICIENT_SIGNAL_PROVENANCE"
    assert prioritization[-1]["remaining_blocker"] in {"SOURCE_SEARCH_INCOMPLETE", "NO_TRADE_FILTER"}
    assert "broker" not in signal


def test_compact_files_have_sidecars(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    output = tmp_path / "closure"
    build_all_strategy_authority_closure(repo_root, output)

    for name in (
        "input_census_integrity.json",
        "dataset_family_authority_reviews.json",
        "dataset_version_authority_decisions.json",
        "aeron7_nifty_f1_authority_review.json",
        "unresolved_source_authority_review.json",
        "signal_ledger_authority_review.json",
        "all_strategy_authority_matrix.json",
        "authority_blocker_ledger.json",
        "strategy_authority_prioritization.json",
    ):
        payload = (output / name).read_text(encoding="utf-8")
        sidecar = (output / f"{name}.sha256").read_text(encoding="utf-8")
        assert payload.strip()
        assert sidecar.endswith(f"  {name}\n")
        digest = sidecar.split()[0]
        assert digest == digest.lower()
        assert all(ch in "0123456789abcdef" for ch in digest)


def test_snapshot_loader_reads_compact_census() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    snapshot = load_all_strategy_authority_closure(repo_root)

    assert snapshot.census_summary["raw_candidates"] == 6119
    assert snapshot.logical_dataset_family_registry[0]["dataset_family_id"] == "FAMILY:BANKNIFTY:spot:NSE:unknown"
    assert snapshot.dataset_family_summary["logical_dataset_family_count"] == 8
    assert snapshot.dataset_version_summary["dataset_version_count"] == 986
    assert snapshot.signal_ledger_summary["canonical_signal_ledger_count"] == 0
    assert snapshot.execution_readiness_summary["valid_precomputed_signals_lanes"] == 0
    assert snapshot.canonical_signal_ledger_registry[0]["status"] == "INSUFFICIENT_PROVENANCE"
