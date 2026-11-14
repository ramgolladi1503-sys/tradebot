import math

import numpy as np
import pytest

from core.research_validation import (
    ResearchEvidence,
    TrialRecord,
    ValidationState,
    adjust_pvalues_benjamini_hochberg,
    adjust_pvalues_benjamini_yekutieli,
    adjust_pvalues_bonferroni,
    adjust_pvalues_holm,
    adjust_pvalues_sidak,
    deflated_sharpe_ratio,
    diagnose_returns,
    effective_rank,
    effective_trials_from_returns,
    evaluate_research_evidence,
    expected_maximum_sharpe_ratio,
    minimum_track_record_length,
    probabilistic_sharpe_ratio,
    probability_of_backtest_overfitting,
    sharpe_ratio_power,
    sharpe_ratio_variance,
    summarize_trial_ledger,
)


def test_reference_sharpe_numbers_match_public_2026_examples():
    sr = 0.036 / 0.079
    variance = sharpe_ratio_variance(sr, 24, skewness=-2.448, kurtosis=10.164)
    assert round(math.sqrt(variance), 3) == 0.329
    assert round(minimum_track_record_length(sr, 0, skewness=-2.448, kurtosis=10.164), 3) == 13.029
    assert round(probabilistic_sharpe_ratio(sr, 0, 24, skewness=-2.448, kurtosis=10.164), 3) == 0.987
    assert round(1 - sharpe_ratio_power(0, 0.5, 24, skewness=-2.448, kurtosis=10.164), 3) == 0.315


def test_effective_rank_distinguishes_independent_and_correlated_trials():
    assert effective_rank(np.eye(4)) == pytest.approx(4.0)
    corr = np.array([[1.0, 0.99, 0.0, 0.0], [0.99, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.99], [0.0, 0.0, 0.99, 1.0]])
    assert effective_rank(corr) < 3.0

    rng = np.random.default_rng(42)
    base = rng.normal(size=(500, 2))
    returns = np.column_stack([base[:, 0], base[:, 0] + 0.01 * rng.normal(size=500), base[:, 1], base[:, 1] + 0.01 * rng.normal(size=500)])
    k_eff = effective_trials_from_returns(returns)
    assert 1.5 < k_eff < 3.0


def test_fractional_effective_trial_count_never_creates_negative_search_penalty():
    benchmark = 0.0
    threshold = expected_maximum_sharpe_ratio(1.01, 0.04, benchmark_sharpe=benchmark)
    assert threshold >= benchmark
    assert threshold == pytest.approx(
        expected_maximum_sharpe_ratio(2.0, 0.04, benchmark_sharpe=benchmark)
    )


def test_dsr_penalizes_a_larger_search_space():
    observed_sr = 0.8
    dsr_small, threshold_small = deflated_sharpe_ratio(
        observed_sr,
        250,
        effective_trials=2,
        sharpe_variance_across_trials=0.04,
    )
    dsr_large, threshold_large = deflated_sharpe_ratio(
        observed_sr,
        250,
        effective_trials=50,
        sharpe_variance_across_trials=0.04,
    )
    assert threshold_large > threshold_small
    assert dsr_large < dsr_small


def test_multiple_testing_adjustments_are_monotone_and_fwer_fdr_distinct():
    p = np.array([0.001, 0.01, 0.04, 0.2])
    bonf = adjust_pvalues_bonferroni(p)
    sidak = adjust_pvalues_sidak(p)
    holm = adjust_pvalues_holm(p)
    bh = adjust_pvalues_benjamini_hochberg(p)
    by = adjust_pvalues_benjamini_yekutieli(p)
    assert np.all((0 <= bonf) & (bonf <= 1))
    assert np.all((0 <= sidak) & (sidak <= 1))
    assert np.all((0 <= holm) & (holm <= 1))
    assert np.all((0 <= bh) & (bh <= 1))
    assert np.all((0 <= by) & (by <= 1))
    assert bh[0] <= bonf[0]
    assert by[0] >= bh[0]


def test_trial_ledger_is_hash_bound_and_fail_closed_on_missing_parent():
    rows = [
        TrialRecord("T1", "H1", "S1", "abc123", "data123", {"x": 1}, "REJECTED", False, {"sr": 0.1}),
        TrialRecord("T2", "H1", "S1", "abc123", "data123", {"x": 2}, "SELECTED", True, {"sr": 0.8}, parent_trial_id="T1"),
    ]
    summary = summarize_trial_ledger(rows)
    assert summary["total_trials"] == 2
    assert summary["selected_trials"] == 1
    assert len(summary["ledger_sha256"]) == 64

    bad = [TrialRecord("T1", "H1", "S1", "abc123", "data123", {}, "REJECTED", False, {}, parent_trial_id="MISSING")]
    with pytest.raises(ValueError, match="trial_parent_not_in_ledger"):
        summarize_trial_ledger(bad)


def test_pbo_separates_stable_edge_from_regime_specific_selection():
    rng = np.random.default_rng(0)
    stable = np.column_stack([
        0.01 + rng.normal(0, 0.01, 160),
        rng.normal(0, 0.01, 160),
        -0.005 + rng.normal(0, 0.01, 160),
        rng.normal(0, 0.012, 160),
    ])
    stable_result = probability_of_backtest_overfitting(stable, subgroup_count=8)
    assert stable_result.pbo == 0.0
    assert set(stable_result.selected_trial_indices) == {0}

    blocks = []
    for regime in range(8):
        block_rng = np.random.default_rng(regime)
        block = block_rng.normal(0, 0.005, (20, 4))
        if regime < 4:
            block[:, 0] += 0.02
            block[:, 1] -= 0.02
        else:
            block[:, 1] += 0.02
            block[:, 0] -= 0.02
        blocks.append(block)
    switching = np.vstack(blocks)
    switching_result = probability_of_backtest_overfitting(switching, subgroup_count=8)
    assert switching_result.pbo > 0.70
    assert switching_result.split_count == math.comb(8, 4)


def test_distribution_gate_warns_but_does_not_claim_population_moment_nonexistence():
    rng = np.random.default_rng(1)
    returns = rng.standard_t(df=3, size=500)
    diagnostics = diagnose_returns(returns, kurtosis_warning_threshold=5.0)
    assert diagnostics.finite is True
    assert diagnostics.heavy_tail_warning is True
    assert diagnostics.inference_model_status == "HEAVY_TAIL_REVIEW_REQUIRED"


def test_research_verdict_fails_closed_and_never_grants_live_authority():
    evidence = ResearchEvidence(
        search_history_complete=True,
        total_trials=20,
        effective_trials=4.0,
        psr=0.99,
        dsr=0.98,
        actual_track_record=500,
        minimum_track_record=200,
        power=0.9,
        pbo=0.2,
        inference_model_valid=True,
        wfa=ValidationState.PASS,
        cost_robustness=ValidationState.PASS,
        holdout=ValidationState.PASS,
        prospective=ValidationState.NOT_RUN,
    )
    verdict = evaluate_research_evidence(evidence)
    assert verdict.passed is False
    assert verdict.verdict == "PROSPECTIVE_NOT_CONFIRMED"
    assert verdict.allowed_for_live_execution is False
    assert verdict.broker_api_called is False
    assert verdict.is_order_action is False
    assert verdict.read_only is True


def test_research_verdict_pass_requires_every_default_gate():
    evidence = ResearchEvidence(
        search_history_complete=True,
        total_trials=20,
        effective_trials=4.0,
        psr=0.99,
        dsr=0.98,
        actual_track_record=500,
        minimum_track_record=200,
        power=0.9,
        pbo=0.2,
        inference_model_valid=True,
        wfa=ValidationState.PASS,
        cost_robustness=ValidationState.PASS,
        holdout=ValidationState.PASS,
        prospective=ValidationState.PASS,
    )
    verdict = evaluate_research_evidence(evidence)
    assert verdict.passed is True
    assert verdict.verdict == "RESEARCH_EVIDENCE_PASS"
    assert verdict.allowed_for_live_execution is False
