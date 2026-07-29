from __future__ import annotations

import pandas as pd

from scripts import run_cross_strike_diffusion_campaign_v2 as mod


def _frame(session_count: int = 100) -> pd.DataFrame:
    return pd.DataFrame({"session_id": [f"s{index:03d}" for index in range(session_count)]})


def test_partition_reserves_latest_fifteen_percent():
    parts = mod.partition_sessions(_frame())
    assert len(parts["research"]) == 70
    assert len(parts["validation"]) == 15
    assert len(parts["master_holdout"]) == 15
    assert max(parts["research"]) < min(parts["validation"])
    assert max(parts["validation"]) < min(parts["master_holdout"])


def test_expanding_folds_never_include_validation_or_master_holdout():
    parts = mod.partition_sessions(_frame())
    folds = mod.expanding_folds(parts["research"])
    assert len(folds) == 5
    forbidden = set(parts["validation"]) | set(parts["master_holdout"])
    for training, testing, _ in folds:
        assert set(training).isdisjoint(forbidden)
        assert set(testing).isdisjoint(forbidden)
        assert max(training) < min(testing)


def test_validation_gate_requires_more_than_twenty_sessions():
    metric = __import__(
        "scripts.run_cross_strike_diffusion_discovery_v1", fromlist=["Metrics"]
    ).Metrics(
        trades=30,
        sessions=25,
        profit_factor=1.4,
        mean_return_pct=1.0,
        median_return_pct=0.5,
        win_rate=0.6,
        net_return_pct_sum=30.0,
        remove_top_five_profit_factor=1.1,
        stress_profit_factor=1.05,
        bootstrap_mean_ci_low=0.1,
        bootstrap_mean_ci_high=1.9,
        positive_folds=1,
        total_folds=1,
        largest_winner_share=0.15,
        top_five_session_profit_share=0.3,
    )
    assert mod.validation_gate(metric)
    assert not mod.validation_gate(metric.__class__(**{**metric.__dict__, "sessions": 19}))


def test_master_holdout_contract_language_is_fail_closed():
    source = __import__("inspect").getsource(mod.main)
    assert "master_holdout_outcomes_materialized\": False" in source
    assert "SEALED_FOR_CROSS_FAMILY_FINAL_CERTIFICATION" in source
