from __future__ import annotations

import inspect
import json
from pathlib import Path

from research.opening_range_retest_corrected_score_edge import artifact_audit, evaluator


def test_contract_freezes_chronological_holdout_before_outcomes() -> None:
    contract = evaluator.build_contract()
    split = contract["chronological_split"]

    assert contract["decision"] == "EDGE_VALIDATION_CONTRACT_FROZEN"
    assert split["random_split"] == "forbidden"
    assert split["development_end"] < split["holdout_start"]
    assert contract["primary_ranking_bucket"].startswith("top 20%")


def test_dataset_manifest_fails_closed_without_trusted_option_bid_ask() -> None:
    contract = evaluator.build_contract()
    manifest = evaluator.build_dataset_manifest(contract["contract_hash"])

    assert manifest["trusted_option_bid_ask_available"] is False
    assert all(asset["contains_real_option_bid_ask"] is False for asset in manifest["assets"])
    assert "No artifact" in manifest["option_data_search_result"]


def test_candidate_semantic_hash_is_deterministic() -> None:
    first = evaluator.build_candidate_conservation()["candidate_semantic_hash"]
    second = evaluator.build_candidate_conservation()["candidate_semantic_hash"]

    assert first == second
    assert len(first) == 64


def test_candidate_conservation_is_not_inferred_from_single_ledger() -> None:
    conservation = evaluator.build_candidate_conservation()

    assert conservation["decision"] == "NOT_EVALUATED_DUAL_REPLAY_UNAVAILABLE"
    assert conservation["base_candidate_count"] is None
    assert conservation["corrected_candidate_count"] == 2215
    assert conservation["current_certified_candidate_count"] == 2215
    assert conservation["non_score_candidate_differences"] is None


def test_candidate_conservation_pass_requires_two_ledgers() -> None:
    candidate = evaluator.build_candidate_conservation() | {
        "decision": "PASS",
        "distinct_generated_ledger_paths": ["one.parquet"],
        "source_shas_compared": [evaluator.CORRECTED_SHA],
        "ledger_sha256_values": ["a" * 64],
    }
    final = {"candidate_conservation": "PASS", "base_candidate_count": 2215}

    failures = artifact_audit.validate_candidate_conservation(candidate, final)

    assert "candidate_conservation:pass_without_two_source_ledgers" in failures


def test_join_corruption_fails_closed_for_missing_candidate() -> None:
    outcomes = evaluator.outcome_records()
    candidate_ids = {record["candidate_id"] for record in evaluator.candidate_records()}
    corrupted = dict(outcomes[0], candidate_id="corrupted-candidate-id")

    assert corrupted["candidate_id"] not in candidate_ids


def test_zero_byte_parquet_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.parquet"
    path.write_bytes(b"")
    artifact = {"logical_artifact_name": "bad", "path": str(path), "format": "parquet", "sha256": artifact_audit.sha256_file(path), "row_count": 0}

    failures = artifact_audit.validate_parquet_artifact(artifact)

    assert "bad:zero_byte_parquet" in failures
    assert "bad:invalid_parquet_magic" in failures


def test_arbitrary_parquet_bytes_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.parquet"
    path.write_bytes(b"not parquet")
    artifact = {"logical_artifact_name": "bad", "path": str(path), "format": "parquet", "sha256": artifact_audit.sha256_file(path), "row_count": 1}

    failures = artifact_audit.validate_parquet_artifact(artifact)

    assert "bad:invalid_parquet_magic" in failures


def test_unavailable_option_ledger_requires_no_placeholder_file(tmp_path: Path) -> None:
    manifest = evaluator.build_external_artifact_manifest()
    final = {"final_verdict": "INSUFFICIENT_TRUSTED_OPTION_DATA"}

    failures = artifact_audit.validate_external_artifacts(tmp_path, manifest, final)

    assert failures == []


def test_physical_placeholder_contradicting_unavailable_status_fails(tmp_path: Path) -> None:
    (tmp_path / "option_trade_ledger.parquet").write_bytes(b"")
    manifest = evaluator.build_external_artifact_manifest()
    final = {"final_verdict": "INSUFFICIENT_TRUSTED_OPTION_DATA"}

    failures = artifact_audit.validate_external_artifacts(tmp_path, manifest, final)

    assert "option_trade_ledger:unavailable_physical_placeholder_exists" in failures


def test_insufficient_data_allows_option_ledger_absent(tmp_path: Path) -> None:
    result = evaluator.generate(tmp_path)
    audit = artifact_audit.audit(tmp_path)
    final = json.loads((tmp_path / "final_verdict.json").read_text(encoding="utf-8"))
    external = json.loads((tmp_path / "external_artifact_manifest.json").read_text(encoding="utf-8"))

    assert result["final_verdict"]["final_verdict"] == "INSUFFICIENT_TRUSTED_OPTION_DATA"
    assert final["option_economic_outcome_invariance"] == "NOT_EVALUABLE_NO_TRUSTED_OPTION_DATA"
    assert not (tmp_path / "option_trade_ledger.parquet").exists()
    assert external["available_artifacts"] == []
    assert {item["logical_artifact_name"]: item["status"] for item in external["unavailable_artifacts"]} == {
        "old_vs_corrected_score_ledger": "NOT_GENERATED_DUAL_REPLAY_MISSING",
        "option_trade_ledger": "NOT_GENERATED_NO_TRUSTED_OPTION_BID_ASK",
    }
    assert audit["verdict"] == "PASS"


def test_actual_two_directory_deterministic_outputs_pass(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    evaluator.generate_compact(run_a, determinism_hash="PENDING")
    evaluator.generate_compact(run_b, determinism_hash="PENDING")

    report = evaluator.compare_outputs(run_a, run_b)

    assert report["decision"] == "PASS"
    assert report["run_a_hash"] == report["run_b_hash"]
    assert report["old_vs_corrected_score_ledger"] == "NOT_APPLICABLE_ARTIFACT_UNAVAILABLE"
    assert report["option_trade_ledger"] == "NOT_APPLICABLE_ARTIFACT_UNAVAILABLE"


def test_deliberately_changed_output_fails_determinism(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    evaluator.generate_compact(run_a, determinism_hash="PENDING")
    evaluator.generate_compact(run_b, determinism_hash="PENDING")
    final = json.loads((run_b / "final_verdict.json").read_text(encoding="utf-8"))
    final["current_certified_candidate_count"] = 0
    (run_b / "final_verdict.json").write_text(json.dumps(final, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    report = evaluator.compare_outputs(run_a, run_b)

    assert report["decision"] == "FAIL"
    assert "final_verdict.json" in report["differing_artifacts"]


def test_research_commit_descended_from_validated_source_can_run() -> None:
    identity = evaluator.verify_source_identity()

    assert identity["decision"] == "PASS"
    assert identity["validated_production_source_sha"] == evaluator.CORRECTED_SHA
    assert identity["research_execution_head"] != identity["validated_production_source_sha"]


def test_production_file_change_after_validated_source_fails_closed() -> None:
    simulated = {
        "decision": "FAIL",
        "validated_production_source_sha": evaluator.CORRECTED_SHA,
        "production_changed_paths_since_validated_source": ["core/example.py"],
        "working_tree_production_diffs_vs_validated_source": [],
    }

    failures = artifact_audit.validate_source_identity(simulated)

    assert "source_identity:not_pass" in failures
    assert "source_identity:production_changes_since_source" in failures


def test_independent_auditor_does_not_import_evaluator_result_helpers() -> None:
    source = inspect.getsource(artifact_audit)

    assert "from research.opening_range_retest_corrected_score_edge.evaluator" not in source
    assert "import evaluator" not in source
    assert "write_json(" not in source
