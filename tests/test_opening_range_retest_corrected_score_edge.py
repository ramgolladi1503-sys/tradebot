from __future__ import annotations

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


def test_join_corruption_fails_closed_for_missing_candidate() -> None:
    outcomes = evaluator.outcome_records()
    candidate_ids = {record["candidate_id"] for record in evaluator.candidate_records()}
    corrupted = dict(outcomes[0], candidate_id="corrupted-candidate-id")

    assert corrupted["candidate_id"] not in candidate_ids


def test_generate_and_independent_audit(tmp_path: Path) -> None:
    result = evaluator.generate(tmp_path)
    audit = artifact_audit.audit(tmp_path)
    final = json.loads((tmp_path / "final_verdict.json").read_text(encoding="utf-8"))
    external = json.loads((tmp_path / "external_artifact_manifest.json").read_text(encoding="utf-8"))

    assert result["final_verdict"]["final_verdict"] == "INSUFFICIENT_TRUSTED_OPTION_DATA"
    assert final["production_files_changed"] == "NO"
    assert final["broker_api_called"] == "NO"
    assert final["underlying_outcome_invariance"] == "NOT_EVALUATED"
    assert final["option_economic_outcome_invariance"] == "NOT_EVALUABLE_NO_TRUSTED_OPTION_DATA"
    assert final["underlying_signal"] == "UNDERLYING_SIGNAL_EVALUATION_INCOMPLETE"
    assert external["artifact_count"] == 2
    assert {item["git_storage_decision"] for item in external["artifacts"]} == {
        "EXTERNAL_HASH_PINNED_REPO_POLICY_IGNORED"
    }
    assert audit["verdict"] == "PASS"
