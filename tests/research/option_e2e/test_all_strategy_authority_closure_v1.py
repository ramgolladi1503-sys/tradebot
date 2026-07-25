from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1 import (
    AuthorityClosureSnapshot,
    AuthorityClosureReconciliationError,
    build_all_strategy_authority_closure,
    load_authority_closure_inputs,
    load_signal_ledger_provenance_evidence,
)


LEDGER_HASH = "b9736aa6af68a07c32a01dbc2bc60220acf8337181e3878940abfab540398bed"
LEDGER_ID = f"{LEDGER_HASH}:24"
EVIDENCE_DIR = Path("research/option_e2e_recertification_v4/signal_ledger_provenance_v1")


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
        canonical_signal_ledger_registry=[{
            "canonical_signal_ledger_id": LEDGER_ID,
            "sha256": LEDGER_HASH,
            "row_count": 24,
            "status": "INSUFFICIENT_PROVENANCE",
        }],
        canonical_signal_ledger_audit=[{
            "canonical_signal_ledger_id": LEDGER_ID,
            "physical_sha256": LEDGER_HASH,
            "row_count": 24,
            "signal_id_unique": True,
            "status": "INSUFFICIENT_PROVENANCE",
            "strategy_or_hypothesis_id": None,
        }],
        aeron7_nifty_f1_dataset_family=[{"dataset_family_id": "FAMILY:NIFTY_F1:futures:NSE:1m", "exact_copy_count": 68}],
        unresolved_candidate_resolution=[{"input_unresolved_count": 1, "items": [{"candidate_id": "u1"}]}],
        truncation_review=[{"root_id": "ROOT", "final_materiality_verdict": "MATERIAL_GAP_NOT_FULLY_EXHAUSTED"}],
        strategy_implementation_inventory=[
            {"canonical_strategy_id": "VWAP_RECLAIM"},
            {"canonical_strategy_id": "NO_TRADE_CHOP"},
        ],
        strategy_alias_registry=[
            {"canonical_strategy_id": "VWAP_RECLAIM", "aliases": ["VWAP_RECLAIM"]},
            {"canonical_strategy_id": "NO_TRADE_CHOP", "aliases": ["NO_TRADE_CHOP"]},
        ],
        all_strategy_execution_readiness=readiness,
        census_summary={"raw_candidates": 3, "physical_accepted_file_count": 2, "raw_unresolved": 1, "material_truncated_roots": 1, "dataset_version_count": 2, "logical_dataset_family_count": 2, "blocked_lanes": 2, "ready_for_causal_execution_lanes": 0, "valid_precomputed_signals_lanes": 0},
        dataset_family_summary={"logical_dataset_family_count": 2},
        dataset_version_summary={"dataset_version_count": 2, "usable_with_limitations_version_count": 1, "unresolved_dataset_version_count": 1},
        signal_ledger_summary={"canonical_signal_ledger_count": 0, "insufficient_provenance_ledgers": 1, "valid_signal_ledger_with_limitations_count": 0},
        execution_readiness_summary={"blocked_lanes_by_blocker_class": {"INSUFFICIENT_SIGNAL_PROVENANCE": 1, "NO_TRADE_FILTER": 1}},
        determinism={"ok": True},
        signal_ledger_provenance=load_signal_ledger_provenance_evidence(EVIDENCE_DIR),
    )


def _cross_record_snapshot() -> AuthorityClosureSnapshot:
    snapshot = _snapshot()
    family_a = "FAMILY:BANKNIFTY:spot:NSE:unknown"
    family_b = "FAMILY:NIFTY_SPOT:spot:NSE:5m"
    version_a = "VERSION:FAMILY:BANKNIFTY:spot:NSE:unknown:aaaaaaaaaaaaaaaa"
    version_b = "VERSION:FAMILY:NIFTY_SPOT:spot:NSE:5m:bbbbbbbbbbbbbbbb"
    candidate_a = {
        "candidate_id": "candidate-a",
        "relative_path": "family-a.parquet",
        "sha256": "a" * 64,
        "physical_sha256": "a" * 64,
        "classification": "UNDERLYING_CANDLE_DATASET",
        "accepted": True,
        "quality_limitations": ["timezone_incomplete"],
    }
    candidate_b = {
        "candidate_id": "candidate-b",
        "relative_path": "family-b.parquet",
        "sha256": "b" * 64,
        "physical_sha256": "b" * 64,
        "classification": "UNDERLYING_CANDLE_DATASET",
        "accepted": True,
        "quality_limitations": ["session_gaps"],
    }
    partitions = [
        {
            "partition_id": "PART:aaaaaaaaaaaaaaaa",
            "blob_id": "a" * 64,
            "dataset_family_id": family_a,
            "dataset_version_id": version_a,
            "first_timestamp": "2026-01-05T09:15:00+05:30",
            "last_timestamp": "2026-01-05T15:30:00+05:30",
            "session_set_hash": "1" * 64,
            "quality_limitations": ["timezone_incomplete"],
        },
        {
            "partition_id": "PART:bbbbbbbbbbbbbbbb",
            "blob_id": "b" * 64,
            "dataset_family_id": family_b,
            "dataset_version_id": version_b,
            "first_timestamp": "2026-01-06T09:15:00+05:30",
            "last_timestamp": "2026-01-06T15:30:00+05:30",
            "session_set_hash": "2" * 64,
            "quality_limitations": ["session_gaps"],
        },
    ]
    families = [
        dict(snapshot.logical_dataset_family_registry[0], dataset_family_id=family_a, partition_ids=["PART:aaaaaaaaaaaaaaaa"], versions=[version_a]),
        dict(snapshot.logical_dataset_family_registry[1], dataset_family_id=family_b, partition_ids=["PART:bbbbbbbbbbbbbbbb"], versions=[version_b]),
    ]
    versions = [
        {
            "dataset_version_id": version_a,
            "dataset_family_id": family_a,
            "status": "USABLE_WITH_LIMITATIONS",
            "partition_ids": ["PART:aaaaaaaaaaaaaaaa"],
            "partition_manifest_hash": "3" * 64,
            "schema_hash": "4" * 64,
            "session_set_hash": "1" * 64,
            "source_provenance": "ROOT_A",
            "creation_method": "source",
            "quality_metrics": {"invalid_rows": 0},
            "limitations": ["timezone_incomplete"],
        },
        {
            "dataset_version_id": version_b,
            "dataset_family_id": family_b,
            "status": "USABLE_WITH_LIMITATIONS",
            "partition_ids": ["PART:bbbbbbbbbbbbbbbb"],
            "partition_manifest_hash": "5" * 64,
            "schema_hash": "6" * 64,
            "session_set_hash": "2" * 64,
            "source_provenance": "ROOT_B",
            "creation_method": "source",
            "quality_metrics": {"invalid_rows": 0},
            "limitations": ["session_gaps"],
        },
    ]
    return replace(
        snapshot,
        physical_candidate_registry=[candidate_a, candidate_b],
        exact_content_blob_registry=[
            {"blob_id": "a" * 64, "physical_sha256": "a" * 64, "candidate_ids": ["candidate-a"]},
            {"blob_id": "b" * 64, "physical_sha256": "b" * 64, "candidate_ids": ["candidate-b"]},
        ],
        exact_duplicate_groups=[
            {"physical_sha256": "a" * 64, "candidate_ids": ["candidate-a"]},
            {"physical_sha256": "b" * 64, "candidate_ids": ["candidate-b"]},
        ],
        dataset_partition_registry=partitions,
        logical_dataset_family_registry=families,
        dataset_version_registry=versions,
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

    snapshot = load_authority_closure_inputs(
        full_run_a=run_a,
        full_run_b=run_b,
        signal_ledger_provenance_dir=EVIDENCE_DIR,
        compact_census_dir=compact,
    )

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
    assert families[1]["authority_status"] == "FAMILY_USABLE_WITH_LIMITATIONS"
    assert versions[0]["dataset_version_id"] == "VERSION:1"
    assert tuple(row["canonical_strategy_id"] for row in matrix) == ("NO_TRADE_CHOP", "VWAP_RECLAIM")
    assert signal["canonical_signal_ledger_count"] == 0
    assert signal["authority_conclusion"] == "INVALIDATED_HISTORICAL_EVIDENCE"
    assert signal["invalidated_signal_ledger_count"] == 1
    assert signal["replacement_signal_ledger_required"] is True


def test_sidecars_are_written(tmp_path: Path) -> None:
    output = tmp_path / "closure"
    build_all_strategy_authority_closure(snapshot=_snapshot(), output_dir=output)

    payload = output / "dataset_family_authority_reviews.json"
    sidecar = output / "dataset_family_authority_reviews.json.sha256"
    assert payload.exists()
    assert sidecar.exists()
    assert sidecar.read_text(encoding="utf-8").split()[0] == hashlib.sha256(payload.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def test_family_and_version_authority_preserves_ids_and_accounts_once(tmp_path: Path) -> None:
    output = tmp_path / "closure"
    build_all_strategy_authority_closure(snapshot=_snapshot(), output_dir=output)

    families = json.loads((output / "dataset_family_authority_reviews.json").read_text(encoding="utf-8"))
    versions = json.loads((output / "dataset_version_authority_decisions.json").read_text(encoding="utf-8"))
    family_ids = tuple(row["dataset_family_id"] for row in families)
    version_ids = tuple(row["dataset_version_id"] for row in versions)
    statuses = {row["dataset_family_id"]: row["authority_status"] for row in families}

    assert family_ids == ("FAMILY:BANKNIFTY:spot:NSE:unknown", "FAMILY:NIFTY_SPOT:spot:NSE:5m")
    assert version_ids == ("VERSION:1", "VERSION:2")
    assert statuses["FAMILY:BANKNIFTY:spot:NSE:unknown"] == "FAMILY_IDENTITY_INCOMPLETE"
    assert statuses["FAMILY:NIFTY_SPOT:spot:NSE:5m"] == "FAMILY_USABLE_WITH_LIMITATIONS"


def test_duplicate_family_and_version_ids_fail_closed(tmp_path: Path) -> None:
    snapshot = _snapshot()
    conflicting_family = dict(snapshot.logical_dataset_family_registry[0], identity_status="PROVISIONAL")
    with pytest.raises(AuthorityClosureReconciliationError, match="duplicate_key_conflict key=dataset_family_id"):
        build_all_strategy_authority_closure(
            snapshot=replace(snapshot, logical_dataset_family_registry=[*snapshot.logical_dataset_family_registry, conflicting_family]),
            output_dir=tmp_path / "family",
        )

    conflicting_version = dict(snapshot.dataset_version_registry[0], status="USABLE_WITH_LIMITATIONS")
    with pytest.raises(AuthorityClosureReconciliationError, match="duplicate_key_conflict key=dataset_version_id"):
        build_all_strategy_authority_closure(
            snapshot=replace(snapshot, dataset_version_registry=[*snapshot.dataset_version_registry, conflicting_version]),
            output_dir=tmp_path / "version",
        )


def test_version_status_mutation_cannot_promote_missing_evidence(tmp_path: Path) -> None:
    snapshot = _snapshot()
    baseline_dir = tmp_path / "baseline"
    mutated_dir = tmp_path / "mutated"
    build_all_strategy_authority_closure(snapshot=snapshot, output_dir=baseline_dir)
    mutated_versions = [dict(row) for row in snapshot.dataset_version_registry]
    mutated_versions[1]["status"] = "EXPLORATORY_ONLY"
    build_all_strategy_authority_closure(
        snapshot=replace(snapshot, dataset_version_registry=mutated_versions),
        output_dir=mutated_dir,
    )

    baseline = json.loads((baseline_dir / "dataset_version_authority_decisions.json").read_text(encoding="utf-8"))
    mutated = json.loads((mutated_dir / "dataset_version_authority_decisions.json").read_text(encoding="utf-8"))
    baseline_decisions = {row["dataset_version_id"]: row["authority_decision"] for row in baseline}
    mutated_decisions = {row["dataset_version_id"]: row["authority_decision"] for row in mutated}

    assert baseline_decisions["VERSION:2"] == "DOWNGRADE_TO_UNRESOLVED"
    assert mutated_decisions["VERSION:2"] == "DOWNGRADE_TO_UNRESOLVED"


def test_family_reviews_join_only_their_own_cross_record_evidence(tmp_path: Path) -> None:
    output = tmp_path / "closure"
    build_all_strategy_authority_closure(snapshot=_cross_record_snapshot(), output_dir=output)

    reviews = json.loads((output / "dataset_family_authority_reviews.json").read_text(encoding="utf-8"))
    by_family = {row["dataset_family_id"]: row for row in reviews}
    banknifty = by_family["FAMILY:BANKNIFTY:spot:NSE:unknown"]

    assert banknifty["partition_ids"] == ["PART:aaaaaaaaaaaaaaaa"]
    assert banknifty["version_ids"] == ["VERSION:FAMILY:BANKNIFTY:spot:NSE:unknown:aaaaaaaaaaaaaaaa"]
    assert banknifty["physical_candidate_ids"] == ["candidate-a"]
    assert banknifty["exact_blob_ids"] == ["a" * 64]
    assert banknifty["quality_limitations"] == ["family_identity_not_canonical", "timezone_incomplete"]
    assert banknifty["first_timestamp"] == "2026-01-05T09:15:00+05:30"
    assert banknifty["last_timestamp"] == "2026-01-05T15:30:00+05:30"
    assert "candidate-b" not in banknifty["physical_candidate_ids"]
    assert "b" * 64 not in banknifty["exact_blob_ids"]


def test_version_decision_uses_evidence_when_declared_status_is_unchanged(tmp_path: Path) -> None:
    snapshot = _cross_record_snapshot()
    baseline_dir = tmp_path / "baseline"
    mutated_dir = tmp_path / "mutated"
    build_all_strategy_authority_closure(snapshot=snapshot, output_dir=baseline_dir)
    mutated_versions = [dict(row) for row in snapshot.dataset_version_registry]
    mutated_versions[0]["source_provenance"] = None
    build_all_strategy_authority_closure(
        snapshot=replace(snapshot, dataset_version_registry=mutated_versions),
        output_dir=mutated_dir,
    )

    baseline = json.loads((baseline_dir / "dataset_version_authority_decisions.json").read_text(encoding="utf-8"))
    mutated = json.loads((mutated_dir / "dataset_version_authority_decisions.json").read_text(encoding="utf-8"))
    baseline_a = {row["dataset_version_id"]: row for row in baseline}["VERSION:FAMILY:BANKNIFTY:spot:NSE:unknown:aaaaaaaaaaaaaaaa"]
    mutated_a = {row["dataset_version_id"]: row for row in mutated}["VERSION:FAMILY:BANKNIFTY:spot:NSE:unknown:aaaaaaaaaaaaaaaa"]

    assert baseline_a["original_census_status"] == "USABLE_WITH_LIMITATIONS"
    assert mutated_a["original_census_status"] == "USABLE_WITH_LIMITATIONS"
    assert baseline_a["authority_decision"] != mutated_a["authority_decision"]
    assert baseline_a["authority_reason_codes"] != mutated_a["authority_reason_codes"]


def test_signal_review_integrates_exact_derived_invalidation_without_lane_assignment(tmp_path: Path) -> None:
    output = tmp_path / "closure"
    build_all_strategy_authority_closure(snapshot=_cross_record_snapshot(), output_dir=output)

    review = json.loads((output / "signal_ledger_authority_review.json").read_text(encoding="utf-8"))
    matrix = json.loads((output / "all_strategy_authority_matrix.json").read_text(encoding="utf-8"))

    assert review["physical_hash"] == LEDGER_HASH
    assert review["artifact_kind"] == "MULTI_OWNER_BLOCKED_PLACEHOLDER_INVENTORY"
    assert review["authority_conclusion"] == "INVALIDATED_HISTORICAL_EVIDENCE"
    assert review["direct_ledger_invalidation_authority"] == "UNRESOLVED"
    assert review["implementation_invalidation_authority"] == "CONFIRMED"
    assert review["derived_ledger_invalidation_authority"] == "CONFIRMED"
    assert review["canonical_strategy_id"] is None
    assert review["lane_impact_analysis"]["affected_lane_assignments"] == []
    assert all(row["selected_canonical_signal_ledger"] != LEDGER_ID for row in matrix)
    assert all(row["execution_eligible"] is False for row in matrix)


def test_alias_resolution_cannot_assign_multi_owner_placeholder(tmp_path: Path) -> None:
    snapshot = _cross_record_snapshot()
    audit = dict(snapshot.canonical_signal_ledger_audit[0], strategy_or_hypothesis_id="VWAP_RECLAIM")

    with pytest.raises(AuthorityClosureReconciliationError, match="multi_owner_placeholder"):
        build_all_strategy_authority_closure(
            snapshot=replace(snapshot, canonical_signal_ledger_audit=[audit]),
            output_dir=tmp_path / "closure",
        )


def test_closure_rejects_ledger_hash_mismatch_against_provenance(tmp_path: Path) -> None:
    snapshot = _cross_record_snapshot()
    audit = dict(snapshot.canonical_signal_ledger_audit[0], physical_sha256="f" * 64)

    with pytest.raises(AuthorityClosureReconciliationError, match="signal_ledger_hash_provenance_mismatch"):
        build_all_strategy_authority_closure(
            snapshot=replace(snapshot, canonical_signal_ledger_audit=[audit]),
            output_dir=tmp_path / "closure",
        )


def test_matrix_and_priority_cross_link_every_component_blocker(tmp_path: Path) -> None:
    output = tmp_path / "closure"
    build_all_strategy_authority_closure(snapshot=_snapshot(), output_dir=output)
    matrix = json.loads((output / "all_strategy_authority_matrix.json").read_text(encoding="utf-8"))
    blockers = json.loads((output / "authority_blocker_ledger.json").read_text(encoding="utf-8"))
    priorities = json.loads((output / "strategy_authority_prioritization.json").read_text(encoding="utf-8"))
    blocker_by_id = {row["blocker_id"]: row for row in blockers}
    matrix_by_id = {row["canonical_strategy_id"]: row for row in matrix}

    for lane_id, lane in matrix_by_id.items():
        expected_ids = sorted(row["blocker_id"] for row in blockers if lane_id in row["affected_strategy_ids"])
        assert lane["current_blocker_ids"] == expected_ids
        assert lane["component_blocker_count"] == len(expected_ids)
        assert lane["current_blocker_classes"] == sorted({blocker_by_id[item]["blocker_class"] for item in expected_ids})
    assert all(
        blocker["blocker_id"] in matrix_by_id[lane_id]["current_blocker_ids"]
        for blocker in blockers
        for lane_id in blocker["affected_strategy_ids"]
    )
    assert {row["upstream_readiness_blocker"] for row in priorities} == {
        "INSUFFICIENT_SIGNAL_PROVENANCE",
        "NO_TRADE_FILTER",
    }
    assert all("remaining_blocker" not in row for row in priorities)
