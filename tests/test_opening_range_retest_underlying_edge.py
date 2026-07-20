from __future__ import annotations

import json
from pathlib import Path

from research.opening_range_retest_underlying_edge import artifact_audit, evaluator


def test_exact_candidate_outcome_join() -> None:
    audit = evaluator.audit_inputs()

    assert audit["decision"] == "PASS"
    assert audit["candidate_count"] == 2215
    assert audit["intersection_count"] == 2215
    assert audit["candidate_ids_missing_outcomes"] == []
    assert audit["outcome_ids_missing_candidates"] == []


def test_duplicate_candidate_rejection_shape() -> None:
    candidate = evaluator.read_json(evaluator.CANDIDATE_LEDGER)
    ids = [row["candidate_id"] for row in candidate["records"]]

    assert len(ids) == len(set(ids))


def test_missing_outcome_rejection_shape() -> None:
    candidate = evaluator.read_json(evaluator.CANDIDATE_LEDGER)
    outcome = evaluator.read_json(evaluator.OUTCOME_LEDGER)

    assert {row["candidate_id"] for row in candidate["records"]} == {row["candidate_id"] for row in outcome["records"]}


def test_direction_normalized_return_uses_certified_horizon() -> None:
    groups = evaluator.read_joined()
    first = next(record for records in groups.values() for record in records)
    outcome = next(
        row for row in evaluator.read_json(evaluator.OUTCOME_LEDGER)["records"] if row["candidate_id"] == first["candidate_id"]
    )

    assert first["primary_return"] == outcome["horizons"]["15"]["directional_underlying_return"]


def test_chronological_80_20_split_and_folds() -> None:
    groups = evaluator.read_joined()
    dev, holdout, blocks = evaluator.fold_plan(groups)

    assert len(dev) == 381
    assert len(holdout) == 96
    assert dev[-1] < holdout[0]
    assert len(blocks) == 6
    assert sum(len(block) for block in blocks) == len(dev)


def test_training_only_score_thresholds_and_holdout_isolation() -> None:
    metrics = evaluator.evaluate()

    for fold in metrics["folds"]:
        assert fold["train_range"][1] < fold["validation_range"][0]
        assert "training_score_80th_percentile" in fold
    assert metrics["holdout_thresholds"]["threshold_source"] == "full_development_only"


def test_session_cluster_bootstrap() -> None:
    groups = evaluator.read_joined()
    dev, _, blocks = evaluator.fold_plan(groups)
    records = evaluator.flatten(groups, dev[: len(blocks[0])])
    ci = evaluator.bootstrap_ci(records, "mean", 123, n=100)

    assert ci["method"] == "session_cluster"
    assert ci["resamples"] == 100
    assert ci["lower"] is not None


def test_negative_controls() -> None:
    metrics = evaluator.evaluate()
    controls = evaluator.negative_controls(metrics["aggregate_oos_bucketed"])

    assert controls["permutations"] == 2000
    assert controls["join_corruption_control"] == "PASS_FAILS_CLOSED"
    assert controls["future_suffix_mutation"] == "NOT_EVALUATED_RAW_CAUSAL_SOURCE_UNAVAILABLE"


def test_inverted_score_control() -> None:
    metrics = evaluator.evaluate()
    controls = evaluator.negative_controls(metrics["aggregate_oos_bucketed"])

    assert controls["inverted_score_result"]["top_minus_bottom_spread"] is not None


def test_concentration_calculation() -> None:
    groups = evaluator.read_joined()
    dev, holdout, _ = evaluator.fold_plan(groups)
    result = evaluator.session_contribution(evaluator.flatten(groups, dev + holdout))

    assert result["single_session_concentration"] is not None
    assert result["top_five_session_concentration"] >= result["single_session_concentration"]


def test_verdict_gate_enforcement() -> None:
    metrics = evaluator.build_metrics()

    assert metrics["final_verdict"]["final_verdict"] in {
        "UNDERLYING_STRUCTURAL_EDGE_CONFIRMED",
        "CORRECTED_SCORE_DISCRIMINATION_CONFIRMED",
        "CANDIDATE_EDGE_PRESENT_SCORE_NOT_PREDICTIVE",
        "UNDERLYING_SIGNAL_WEAK_OR_UNSTABLE",
        "NO_UNDERLYING_STRUCTURAL_EDGE",
    }


def test_deterministic_reruns(tmp_path: Path) -> None:
    run_a = tmp_path / "a"
    run_b = tmp_path / "b"
    evaluator.generate(run_a)
    evaluator.generate(run_b)
    comparison = evaluator.compare_runs(run_a, run_b)

    assert comparison["decision"] == "PASS"
    assert comparison["run_a_semantic_hash"] == comparison["run_b_semantic_hash"]


def test_option_profitability_claim_prohibition(tmp_path: Path) -> None:
    evaluator.generate(tmp_path)
    final = json.loads((tmp_path / "final_verdict.json").read_text(encoding="utf-8"))

    assert final["option_economic_edge"] == "NOT_EVALUATED_NO_BID_ASK"
    assert final["option_profitability_claimed"] == "NO"


def test_production_source_identity_gate() -> None:
    identity = evaluator.source_identity()

    assert identity["decision"] == "PASS"
    assert identity["validated_production_source"] == evaluator.VALIDATED_SOURCE
    assert identity["production_paths_changed_since_validated_source"] == []


def test_independent_auditor(tmp_path: Path) -> None:
    evaluator.generate(tmp_path)
    audit = artifact_audit.audit(tmp_path)

    assert audit["verdict"] == "PASS"
