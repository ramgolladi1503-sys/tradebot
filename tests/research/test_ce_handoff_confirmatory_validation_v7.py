from __future__ import annotations

from scripts import run_ce_handoff_confirmatory_validation_v7 as mod


def _metrics(**overrides):
    values = {
        "trades": 25,
        "sessions": 20,
        "profit_factor": 1.5,
        "mean_return_pct": 2.0,
        "median_return_pct": 0.5,
        "win_rate": 0.6,
        "net_return_pct_sum": 50.0,
        "remove_top_five_profit_factor": 1.2,
        "stress_profit_factor": 1.2,
        "bootstrap_mean_ci_low": 0.1,
        "bootstrap_mean_ci_high": 3.0,
        "positive_folds": 1,
        "total_folds": 1,
        "largest_winner_share": 0.15,
        "top_five_session_profit_share": 0.35,
        "session_cluster_ci_low": 0.1,
        "session_cluster_ci_high": 3.0,
    }
    values.update(overrides)
    return values


def test_exactly_one_candidate_is_frozen():
    assert mod.CANDIDATE_ID == "ce_leadership_handoff_10m_v7"
    assert mod.MIN_VALIDATION_TRADES == 20
    assert mod.MIN_VALIDATION_SESSIONS == 15


def test_confirmatory_gate_requires_independent_positive_cluster_ci():
    primary = _metrics()
    delayed = _metrics(trades=20, mean_return_pct=1.0)
    pe = _metrics(trades=20, mean_return_pct=0.5)
    passed, gates = mod.validation_gate(primary, delayed, pe)
    assert passed
    failed, failed_gates = mod.validation_gate(
        _metrics(session_cluster_ci_low=-0.01), delayed, pe
    )
    assert not failed
    assert not failed_gates["cluster_ci"]


def test_controls_must_be_materially_weaker():
    primary = _metrics(mean_return_pct=2.0)
    passed, _ = mod.validation_gate(
        primary,
        _metrics(trades=20, mean_return_pct=1.9),
        _metrics(trades=20, mean_return_pct=0.5),
    )
    assert not passed
    passed, _ = mod.validation_gate(
        primary,
        _metrics(trades=20, mean_return_pct=1.0),
        _metrics(trades=20, mean_return_pct=1.7),
    )
    assert not passed


def test_master_holdout_is_never_materialized_by_validation_runner():
    import inspect

    source = inspect.getsource(mod.main)
    assert 'partitions["master_holdout"]' not in source
    assert '"master_holdout_outcomes_materialized": False' in source
    assert '"master_holdout_status": "SEALED_FOR_SINGLE_CANDIDATE_FINAL_CERTIFICATION"' in source


def test_live_authorization_is_impossible_in_result_contract():
    import inspect

    source = inspect.getsource(mod.main)
    assert '"paper_or_live_authorized": False' in source
    assert '"allowed_for_live_execution": False' in source
