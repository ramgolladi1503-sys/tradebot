from __future__ import annotations

import json
from pathlib import Path

from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1 import (
    build_all_strategy_authority_closure,
    load_all_strategy_authority_closure,
)


def test_closure_uses_published_census_counts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    output = tmp_path / "closure"

    result = build_all_strategy_authority_closure(repo_root, output)

    integrity = json.loads((output / "input_census_integrity.json").read_text(encoding="utf-8"))
    families = json.loads((output / "dataset_family_authority_reviews.json").read_text(encoding="utf-8"))
    versions = json.loads((output / "dataset_version_authority_decisions.json").read_text(encoding="utf-8"))
    matrix = json.loads((output / "all_strategy_authority_matrix.json").read_text(encoding="utf-8"))
    blockers = json.loads((output / "authority_blocker_ledger.json").read_text(encoding="utf-8"))

    assert integrity["authority_status"] == "PASS"
    assert integrity["raw_candidates"] == 6119
    assert integrity["accepted_physical_files"] == 1055
    assert integrity["dataset_families"] == 8
    assert integrity["dataset_versions"] == 986
    assert integrity["canonical_signal_ledgers"] == 0
    assert integrity["material_truncated_roots"] == 27
    assert result["authority_status"] == "BLOCKED_WITH_DECLARED_GAPS"
    assert result["dataset_family_count"] == 8
    assert result["dataset_version_count"] == 986
    assert result["ready_for_causal_execution_lanes"] == 0
    assert result["valid_precomputed_signals_lanes"] == 0
    assert len(families) == 8
    assert families[0]["authority_status"] == "BLOCKED_WITH_LIMITATIONS"
    assert families[-1]["authority_status"] == "BLOCKED"
    assert len(versions) == 986
    assert sum(1 for row in versions if row["authority_status"] == "UNRESOLVED_DATASET_VERSION") == 961
    assert sum(1 for row in versions if row["authority_status"] == "USABLE_WITH_LIMITATIONS") == 25
    assert matrix[-1]["authority_target"] == "strategy_execution"
    assert blockers[0]["blocked_lane_count"] == 7
    assert blockers[1]["blocked_lane_count"] == 1
    assert blockers[2]["blocked_lane_count"] == 8
    assert "canonical" not in integrity["implementation_direction"].lower()
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
    assert unresolved["authority_status"] == "BLOCKED"
    assert unresolved["unresolved_candidate_count"] == 24
    assert unresolved["material_truncated_roots"] == 27
    assert signal["authority_status"] == "BLOCKED"
    assert signal["canonical_signal_ledger_count"] == 0
    assert signal["insufficient_provenance_ledgers"] == 1
    assert prioritization[0]["canonical_strategy_id"] == "VWAP_RECLAIM"
    assert prioritization[0]["remaining_blocker"] == "INSUFFICIENT_SIGNAL_PROVENANCE"
    assert prioritization[-1]["canonical_strategy_id"] == "NO_TRADE_CHOP"
    assert prioritization[-1]["remaining_blocker"] == "NO_TRADE_FILTER"
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
        assert len(sidecar.split()[0]) == 64


def test_snapshot_loader_reads_compact_census() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    snapshot = load_all_strategy_authority_closure(repo_root)

    assert snapshot.census_summary["raw_candidates"] == 6119
    assert snapshot.dataset_family_summary["logical_dataset_family_count"] == 8
    assert snapshot.dataset_version_summary["dataset_version_count"] == 986
    assert snapshot.signal_ledger_summary["canonical_signal_ledger_count"] == 0
    assert snapshot.execution_readiness_summary["valid_precomputed_signals_lanes"] == 0
