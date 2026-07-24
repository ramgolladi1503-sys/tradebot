from __future__ import annotations

import hashlib
import json
from pathlib import Path

from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1 import (
    AuthorityClosureSnapshot,
    build_all_strategy_authority_closure,
    load_authority_closure_inputs,
)


def _semantic_sha(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "input_bundle_integrity_independent.json", {"status": "INPUT_BUNDLE_INTEGRITY_PASSED", "candidate_count": 3, "accepted_candidate_count": 2, "unresolved_candidate_count": 1})
    for name in (
        "current_986_breakdown.json",
        "logical_dataset_family_registry.json",
        "dataset_version_registry.json",
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
    ):
        _write_json(run_dir / name, [])
    _write_jsonl(run_dir / "physical_candidate_registry.jsonl", [{"candidate_id": "c1"}])
    _write_jsonl(run_dir / "exact_content_blob_registry.jsonl", [{"blob_id": "b1"}])
    _write_jsonl(run_dir / "exact_duplicate_groups.jsonl", [])
    _write_jsonl(run_dir / "dataset_partition_registry.jsonl", [{"partition_id": "p1"}])
    _write_jsonl(run_dir / "semantic_duplicate_groups.jsonl", [])


def _snapshot() -> AuthorityClosureSnapshot:
    families = [
        {"dataset_family_id": "FAMILY:BANKNIFTY:spot:NSE:unknown", "partition_count": 1, "physical_file_count": 1, "exact_copy_count": 0, "identity_status": "IDENTITY_INCOMPLETE", "generation_method": "source"},
        {"dataset_family_id": "FAMILY:NIFTY_SPOT:spot:NSE:5m", "partition_count": 1, "physical_file_count": 1, "exact_copy_count": 0, "identity_status": "PROVISIONAL", "generation_method": "source"},
    ]
    versions = [
        {"dataset_version_id": "VERSION:1", "dataset_family_id": families[0]["dataset_family_id"], "status": "UNRESOLVED_DATASET_VERSION", "limitations": ["gap"], "partition_ids": ["p1"], "source_provenance": "ROOT"},
        {"dataset_version_id": "VERSION:2", "dataset_family_id": families[1]["dataset_family_id"], "status": "USABLE_WITH_LIMITATIONS", "limitations": ["timezone_incomplete"], "partition_ids": ["p2"], "source_provenance": "ROOT"},
    ]
    readiness = [
        {"canonical_strategy_id": "VWAP_RECLAIM", "remaining_blocker": "INSUFFICIENT_SIGNAL_PROVENANCE", "status": "READY_WITH_DATA_LIMITATIONS", "selected_canonical_dataset": "VERSION:1", "selected_canonical_signal_ledger": None},
        {"canonical_strategy_id": "NO_TRADE_CHOP", "remaining_blocker": "NO_TRADE_FILTER", "status": "NO_TRADE_FILTER", "selected_canonical_dataset": "VERSION:1", "selected_canonical_signal_ledger": None},
    ]
    return AuthorityClosureSnapshot(
        input_bundle={"status": "INPUT_BUNDLE_INTEGRITY_PASSED", "candidate_count": 3, "accepted_candidate_count": 2, "unresolved_candidate_count": 1},
        current_986_breakdown={},
        physical_candidate_registry=[{"candidate_id": "c1"}],
        exact_content_blob_registry=[{"blob_id": "b1"}],
        exact_duplicate_groups=[],
        dataset_partition_registry=[{"partition_id": "p1"}],
        logical_dataset_family_registry=families,
        dataset_version_registry=versions,
        semantic_duplicate_groups=[],
        canonical_signal_ledger_registry=[{"canonical_signal_ledger_id": "s1", "status": "INSUFFICIENT_PROVENANCE"}],
        canonical_signal_ledger_audit=[{"canonical_signal_ledger_id": "s1", "status": "INSUFFICIENT_PROVENANCE"}],
        aeron7_nifty_f1_dataset_family=[{"dataset_family_id": "FAMILY:NIFTY_F1:futures:NSE:1m", "exact_copy_count": 68}],
        unresolved_candidate_resolution=[{"input_unresolved_count": 1, "items": [{"candidate_id": "u1"}]}],
        truncation_review=[{"root_id": "ROOT", "final_materiality_verdict": "MATERIAL_GAP_NOT_FULLY_EXHAUSTED"}],
        strategy_implementation_inventory=[
            {"canonical_strategy_id": "VWAP_RECLAIM"},
            {"canonical_strategy_id": "NO_TRADE_CHOP"},
        ],
        strategy_alias_registry=[{"canonical_strategy_id": "VWAP_RECLAIM", "aliases": ["VWAP_RECLAIM"]}],
        all_strategy_execution_readiness=readiness,
        census_summary={"raw_candidates": 3, "physical_accepted_file_count": 2, "raw_unresolved": 1, "material_truncated_roots": 1, "dataset_version_count": 2, "logical_dataset_family_count": 2, "blocked_lanes": 2, "ready_for_causal_execution_lanes": 0, "valid_precomputed_signals_lanes": 0},
        dataset_family_summary={"logical_dataset_family_count": 2},
        dataset_version_summary={"dataset_version_count": 2, "usable_with_limitations_version_count": 1, "unresolved_dataset_version_count": 1},
        signal_ledger_summary={"canonical_signal_ledger_count": 0, "insufficient_provenance_ledgers": 1, "valid_signal_ledger_with_limitations_count": 0},
        execution_readiness_summary={"blocked_lanes_by_blocker_class": {"INSUFFICIENT_SIGNAL_PROVENANCE": 1, "NO_TRADE_FILTER": 1}},
        determinism={"ok": True},
    )


def test_loader_reconciles_semantically_identical_runs(tmp_path: Path) -> None:
    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    _write_run(run_a)
    _write_run(run_b)
    compact = tmp_path / "compact"
    compact.mkdir()
    _write_json(compact / "census_summary.json", {"raw_candidates": 3})
    _write_json(compact / "dataset_family_summary.json", {"logical_dataset_family_count": 2})
    _write_json(compact / "dataset_version_summary.json", {"dataset_version_count": 2})
    _write_json(compact / "signal_ledger_summary.json", {"canonical_signal_ledger_count": 0})
    _write_json(compact / "execution_readiness_summary.json", {"valid_precomputed_signals_lanes": 0})

    snapshot = load_authority_closure_inputs(full_run_a=run_a, full_run_b=run_b, compact_census_dir=compact)

    assert snapshot.census_summary["raw_candidates"] == 3
    assert snapshot.dataset_family_summary["logical_dataset_family_count"] == 2
    assert snapshot.dataset_version_summary["dataset_version_count"] == 2


def test_closure_builds_real_records_from_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "closure"
    result = build_all_strategy_authority_closure(snapshot=_snapshot(), output_dir=output)

    families = json.loads((output / "dataset_family_authority_reviews.json").read_text(encoding="utf-8"))
    versions = json.loads((output / "dataset_version_authority_decisions.json").read_text(encoding="utf-8"))
    matrix = json.loads((output / "all_strategy_authority_matrix.json").read_text(encoding="utf-8"))
    signal = json.loads((output / "signal_ledger_authority_review.json").read_text(encoding="utf-8"))

    assert result.authority_status == "BLOCKED_WITH_DECLARED_GAPS"
    assert result.dataset_family_count == 2
    assert result.dataset_version_count == 2
    assert families[0]["dataset_family_id"] == "FAMILY:BANKNIFTY:spot:NSE:unknown"
    assert families[1]["authority_status"] == "BLOCKED_WITH_LIMITATIONS"
    assert versions[0]["dataset_version_id"] == "VERSION:1"
    assert matrix[-1]["authority_target"] == "strategy_execution"
    assert signal["canonical_signal_ledger_count"] == 0


def test_sidecars_are_written(tmp_path: Path) -> None:
    output = tmp_path / "closure"
    build_all_strategy_authority_closure(snapshot=_snapshot(), output_dir=output)

    payload = output / "dataset_family_authority_reviews.json"
    sidecar = output / "dataset_family_authority_reviews.json.sha256"
    assert payload.exists()
    assert sidecar.exists()
    assert sidecar.read_text(encoding="utf-8").split()[0] == hashlib.sha256(payload.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
