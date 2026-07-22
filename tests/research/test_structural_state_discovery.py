from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.run_structural_state_discovery import (
    DEFAULT_KITE_ARCHIVE,
    DiscoveryError,
    build_matrices,
    dataframe_hash,
    load_kite,
    outer_folds,
    run,
)


def test_fake_kite_archive_fails_closed(tmp_path: Path) -> None:
    fake = tmp_path / "kite.zip"
    fake.write_bytes(b"bad")
    with pytest.raises(DiscoveryError, match="hash mismatch"):
        load_kite(fake)


def test_real_kite_matrices_are_causal_and_research_only() -> None:
    if not DEFAULT_KITE_ARCHIVE.is_file():
        pytest.fail("authoritative Kite archive missing")
    bars, _, sessions, _ = load_kite(DEFAULT_KITE_ARCHIVE)
    features, outcomes = build_matrices(bars, sessions[:12])
    assert not features.empty
    assert len(features) == len(outcomes)
    assert set(features["decision_time"]).issubset({"09:45", "10:30", "11:30", "13:00", "14:00"})
    assert (pd.to_datetime(features["entry_timestamp"]) >= pd.to_datetime(features["decision_timestamp"])).all()
    assert (features["execution_eligibility"] == False).all()  # noqa: E712
    assert (features["allowed_for_live_execution"] == False).all()  # noqa: E712
    for column in [
        "raw_15m_return_bps",
        "raw_30m_return_bps",
        "raw_60m_return_bps",
        "raw_close_return_bps",
        "30m_MFE_long_bps",
        "30m_MAE_short_bps",
        "target_10_stop_10_label",
        "target_20_stop_20_label",
    ]:
        assert column in outcomes.columns


def test_outer_folds_are_expanding_and_chronological() -> None:
    folds = outer_folds([f"2026-01-{i:02d}" for i in range(1, 41)])
    assert len(folds) >= 5
    previous_train = 0
    for fold in folds:
        assert fold["train_end"] < fold["test_start"]
        assert set(fold["train_sessions"]).isdisjoint(fold["test_sessions"])
        assert len(fold["train_sessions"]) > previous_train
        previous_train = len(fold["train_sessions"])


def test_campaign_writes_v2_artifacts_and_truthful_contracts(tmp_path: Path) -> None:
    if not DEFAULT_KITE_ARCHIVE.is_file():
        pytest.fail("authoritative Kite archive missing")
    output = tmp_path / "evidence"
    result = run(output, DEFAULT_KITE_ARCHIVE, max_sessions=35)
    assert result["final_verdict"] in {
        "NO_STABLE_STATE_EDGE_FOUND",
        "DISCOVERY_ONLY_NOT_VALIDATED",
        "RETROSPECTIVE_VALIDATED_STATE_CANDIDATE",
        "READY_FOR_PROSPECTIVE_SHADOW",
    }
    assert result["determinism"] == "PASS"
    required = [
        "source/source_authority.json",
        "source/accepted_file_manifest.json",
        "source/accepted_session_manifest.json",
        "source/session_conservation.json",
        "source/evidence_exposure_registry.json",
        "source/holdout_contamination.json",
        "contracts/feature_contract.json",
        "contracts/timestamp_contract.json",
        "contracts/outcome_contract.json",
        "contracts/discovery_contract.json",
        "contracts/multiple_testing_contract.json",
        "contracts/matched_control_contract.json",
        "contracts/validation_contract.json",
        "features/feature_matrix.parquet",
        "features/outcome_matrix.parquet",
        "features/feature_dictionary.json",
        "features/matrix_hashes.json",
        "features/timestamp_boundary_samples.json",
        "discovery/complete_hypothesis_ledger.parquet",
        "discovery/quantile_single_feature.json",
        "discovery/quantile_interactions.json",
        "discovery/shallow_tree_rules.json",
        "discovery/sparse_model_results.json",
        "discovery/cluster_states.json",
        "discovery/fdr_results.json",
        "candidates/frozen_candidate_rules.json",
        "candidates/candidate_manifest.parquet",
        "candidates/candidate_bundle_hash.json",
        "evaluation/chronological_outer_folds.json",
        "evaluation/chronological_inner_folds.json",
        "evaluation/development_results.json",
        "evaluation/matched_controls.parquet",
        "evaluation/matched_controls.json",
        "evaluation/negative_controls.json",
        "evaluation/delay_sensitivity.json",
        "evaluation/boundary_sensitivity.json",
        "evaluation/concentration.json",
        "evaluation/retrospective_validation_results.json",
        "audit/independent_oracle.json",
        "audit/mutation_tests.json",
        "audit/determinism.json",
        "audit/artifact_index.json",
        "audit/final_verdict.json",
        "report/EXECUTIVE_SUMMARY.md",
        "report/FINAL_REPORT.md",
        "run-a/features/feature_matrix.parquet",
        "run-b/features/feature_matrix.parquet",
    ]
    for rel in required:
        assert (output / rel).is_file(), rel
        assert (output / f"{rel}.sha256").is_file(), rel
    exposure = json.loads((output / "source/evidence_exposure_registry.json").read_text())
    assert exposure["latest_100_internal_holdout_status"] == "CONTAMINATED_BY_V1_OUTCOME_MATERIALIZATION"
    feature_contract = json.loads((output / "contracts/feature_contract.json").read_text())
    assert feature_contract["predictor_feature_count"] > 20
    assert feature_contract["feature_row_count"] != feature_contract["predictor_feature_count"]
    matrix_hashes = json.loads((output / "features/matrix_hashes.json").read_text())
    features = pd.read_parquet(output / "features/feature_matrix.parquet")
    assert matrix_hashes["feature_matrix_hash"] == dataframe_hash(features)
    ledger = pd.read_parquet(output / "discovery/complete_hypothesis_ledger.parquet")
    assert ledger["q_value"].notna().all()
    assert {
        "quantile_single",
        "quantile_interaction_2",
        "quantile_interaction_3",
        "shallow_tree_leaf",
        "sparse_model_nomination",
        "cluster_state",
    }.issubset(set(ledger["lane"]))
    negatives = json.loads((output / "evaluation/negative_controls.json").read_text())
    for name in [
        "session_level_label_permutation",
        "matched_random_timestamps",
        "matched_random_sessions",
        "direction_inversion",
        "feature_column_permutation",
        "false_previous_session_ownership",
        "one_bar_delayed_entry",
        "two_bar_delayed_entry",
        "top_five_session_removal",
        "best_month_removal",
        "leave_one_quarter_out",
        "post_outcome_mutation_invariance",
    ]:
        assert name in negatives
    mutations = json.loads((output / "audit/mutation_tests.json").read_text())["mutations"]
    assert len(mutations) == 10
    assert all(m["exit_code"] != 0 for m in mutations)
