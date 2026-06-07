from __future__ import annotations

from core.expectancy.strategy_baseline_comparison import (
    BASELINE_VERDICT_INSUFFICIENT_SAMPLE,
    BASELINE_VERDICT_MATCHES,
    BASELINE_VERDICT_OUTPERFORMS,
    BASELINE_VERDICT_UNDERPERFORMS,
    compare_strategy_to_baselines,
)


def _row(**overrides):
    row = {
        "candidate_id": "cand-1",
        "trade_id": "trade-1",
        "strategy_id": "breakout_v1",
        "setup_id": "breakout__LIVE__HIGH__HIGH__WIDE__T08_11_UTC__WEEKLY__BUY__NIFTY__CE",
        "strategy_family": "breakout",
        "regime": "LIVE",
        "index": "NIFTY",
        "expiry_type": "WEEKLY",
        "option_type": "CE",
        "direction": "BUY",
        "sample_count": 50,
        "executable_count": 50,
        "not_executable_count": 0,
        "avg_cost_adjusted_r": 0.20,
        "median_cost_adjusted_r": 0.20,
        "keep_watch_kill_status": "KEEP",
        "status_reason": "strong_positive_expectancy_and_sample_threshold_met",
    }
    row.update(overrides)
    return row


def test_outperforms_same_regime_baseline():
    report = compare_strategy_to_baselines(
        [
            _row(setup_id="breakout__LIVE__A", avg_cost_adjusted_r=0.22, sample_count=60),
            _row(setup_id="breakout__LIVE__B", avg_cost_adjusted_r=0.08, sample_count=55),
            _row(strategy_id="range_v1", strategy_family="range", regime="LIVE", direction="BUY", setup_id="range__LIVE__A", avg_cost_adjusted_r=0.10, sample_count=58),
        ]
    )

    comparison = report.comparisons[0]
    assert comparison.baseline_verdict == BASELINE_VERDICT_OUTPERFORMS
    assert comparison.expectancy_delta_vs_baseline > 0
    assert comparison.penalty_or_boost > 0
    assert "same_regime" in comparison.reason


def test_underperforms_same_regime_baseline():
    report = compare_strategy_to_baselines(
        [
            _row(setup_id="breakout__LIVE__A", avg_cost_adjusted_r=0.05, sample_count=60),
            _row(setup_id="breakout__LIVE__B", avg_cost_adjusted_r=0.22, sample_count=60),
        ]
    )

    comparison = report.comparisons[0]
    assert comparison.baseline_verdict == BASELINE_VERDICT_UNDERPERFORMS
    assert comparison.expectancy_delta_vs_baseline < 0
    assert comparison.penalty_or_boost < 0


def test_matches_same_ish_baseline():
    report = compare_strategy_to_baselines(
        [
            _row(setup_id="breakout__LIVE__A", avg_cost_adjusted_r=0.15, sample_count=60),
            _row(setup_id="breakout__LIVE__B", avg_cost_adjusted_r=0.16, sample_count=60),
        ]
    )

    comparison = report.comparisons[0]
    assert comparison.baseline_verdict == BASELINE_VERDICT_MATCHES
    assert comparison.penalty_or_boost == 0.0


def test_insufficient_sample_is_neutral():
    report = compare_strategy_to_baselines([_row(sample_count=8, avg_cost_adjusted_r=0.24)])

    comparison = report.comparisons[0]
    assert comparison.baseline_verdict == BASELINE_VERDICT_INSUFFICIENT_SAMPLE
    assert comparison.penalty_or_boost == 0.0
    assert comparison.confidence_tier == "INSUFFICIENT"


def test_gross_positive_but_after_cost_negative_is_penalized():
    report = compare_strategy_to_baselines(
        [
            _row(setup_id="breakout__LIVE__A", avg_cost_adjusted_r=-0.06, sample_count=60, gross_avg_cost_adjusted_r=0.20),
            _row(setup_id="breakout__LIVE__B", avg_cost_adjusted_r=0.10, sample_count=60),
        ]
    )

    comparison = report.comparisons[0]
    assert comparison.strategy_after_cost_expectancy < 0
    assert comparison.baseline_verdict in {BASELINE_VERDICT_UNDERPERFORMS, BASELINE_VERDICT_MATCHES}
    assert comparison.penalty_or_boost <= 0


def test_missing_same_regime_baseline_falls_back_conservatively():
    report = compare_strategy_to_baselines(
        [
            _row(setup_id="breakout__LIVE__A", regime="LIVE", avg_cost_adjusted_r=0.18, sample_count=60),
            _row(setup_id="range__PAPER__A", regime="PAPER", strategy_family="range", avg_cost_adjusted_r=0.19, sample_count=60),
        ]
    )

    comparison = report.comparisons[0]
    assert comparison.baseline_source in {"same_direction", "eligible_candidates"}
    assert comparison.baseline_verdict in {
        BASELINE_VERDICT_OUTPERFORMS,
        BASELINE_VERDICT_MATCHES,
        BASELINE_VERDICT_UNDERPERFORMS,
        BASELINE_VERDICT_INSUFFICIENT_SAMPLE,
    }


def test_deterministic_output():
    rows = [
        _row(setup_id="breakout__LIVE__A", avg_cost_adjusted_r=0.18, sample_count=60),
        _row(setup_id="breakout__LIVE__B", avg_cost_adjusted_r=0.12, sample_count=60),
    ]

    first = compare_strategy_to_baselines(rows)
    second = compare_strategy_to_baselines(rows)

    assert first.to_dict() == second.to_dict()

