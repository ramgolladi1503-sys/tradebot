from __future__ import annotations

import json
from pathlib import Path

from core.expectancy.strategy_regime_expectancy import (
    STRATEGY_REGIME_EXPECTANCY_SCHEMA_VERSION,
    aggregate_strategy_regime_expectancy,
    load_candidate_outcomes,
    write_strategy_regime_expectancy_report,
    write_strategy_regime_expectancy_reports,
)


def _outcome(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": "cand-1",
        "trade_id": "trade-1",
        "strategy_family": "breakout",
        "regime": "TREND",
        "index": "NIFTY",
        "expiry_type": "WEEKLY",
        "option_type": "CE",
        "direction": "BUY",
        "signal_epoch": 1.0,
        "outcome_status": "TARGET_HIT",
        "outcome_reason": "target_hit_before_stop",
        "entry_price": 100.0,
        "stop_loss_price": 95.0,
        "target_price": 110.0,
        "timeout_epoch": 301.0,
        "gross_r": 2.0,
        "estimated_cost_r": 0.25,
        "cost_adjusted_r": 1.75,
        "fallback_used": False,
    }
    payload.update(overrides)
    return payload


def test_positive_group_becomes_watch_or_keep_based_on_thresholds() -> None:
    rows = [
        _outcome(candidate_id=f"cand-{i}", trade_id=f"trade-{i}", signal_epoch=float(i), cost_adjusted_r=0.25)
        for i in range(1, 31)
    ]

    report = aggregate_strategy_regime_expectancy(rows)
    assert report.groups
    group = report.groups[0]
    assert group.keep_watch_kill_status == "WATCH"
    assert group.status_reason == "positive_expectancy_but_keep_threshold_not_met"
    assert group.sample_count == 30
    assert group.executable_count == 30
    assert group.avg_cost_adjusted_r > 0

    rows.extend(
        _outcome(candidate_id=f"cand-k-{i}", trade_id=f"trade-k-{i}", signal_epoch=float(31 + i), cost_adjusted_r=0.2)
        for i in range(1, 21)
    )
    report = aggregate_strategy_regime_expectancy(rows)
    group = report.groups[0]
    assert group.keep_watch_kill_status == "KEEP"
    assert group.sample_count == 50
    assert group.avg_cost_adjusted_r >= 0.15


def test_negative_group_becomes_kill() -> None:
    rows = [
        _outcome(candidate_id=f"cand-{i}", trade_id=f"trade-{i}", cost_adjusted_r=-0.2, gross_r=-0.1, outcome_status="STOP_HIT", signal_epoch=float(i))
        for i in range(1, 31)
    ]

    group = aggregate_strategy_regime_expectancy(rows).groups[0]
    assert group.keep_watch_kill_status == "KILL"
    assert group.status_reason == "avg_cost_adjusted_r_non_positive"
    assert group.avg_cost_adjusted_r <= 0


def test_small_sample_remains_insufficient_data() -> None:
    rows = [_outcome(candidate_id=f"cand-{i}", trade_id=f"trade-{i}", signal_epoch=float(i)) for i in range(1, 5)]

    group = aggregate_strategy_regime_expectancy(rows).groups[0]
    assert group.keep_watch_kill_status == "INSUFFICIENT_DATA"
    assert group.status_reason == "sample_count_below_threshold"
    assert group.sample_count == 4


def test_fallback_outcomes_excluded_from_executable_expectancy() -> None:
    rows = [
        _outcome(candidate_id="fallback-1", trade_id="fallback-1", fallback_used=True, outcome_status="NOT_EXECUTABLE", cost_adjusted_r=9.0),
        _outcome(candidate_id="exec-1", trade_id="exec-1", signal_epoch=2.0, cost_adjusted_r=1.0),
    ]

    group = aggregate_strategy_regime_expectancy(rows).groups[0]
    assert group.fallback_excluded_count == 1
    assert group.executable_count == 1
    assert group.not_executable_count == 0
    assert group.avg_cost_adjusted_r == 1.0


def test_blocked_not_executable_counted_separately() -> None:
    rows = [
        _outcome(candidate_id="blocked-1", trade_id="blocked-1", outcome_status="INVALID_INPUT", cost_adjusted_r=0.0),
        _outcome(candidate_id="notexec-1", trade_id="notexec-1", outcome_status="NOT_EXECUTABLE", cost_adjusted_r=0.0),
        _outcome(candidate_id="exec-1", trade_id="exec-1", signal_epoch=1.0, cost_adjusted_r=0.5),
    ]

    group = aggregate_strategy_regime_expectancy(rows).groups[0]
    assert group.blocked_excluded_count == 1
    assert group.not_executable_count == 1
    assert group.executable_count == 1
    assert group.sample_count == 3


def test_median_cost_adjusted_r_correct() -> None:
    rows = [
        _outcome(candidate_id="cand-1", trade_id="trade-1", signal_epoch=1.0, cost_adjusted_r=1.0),
        _outcome(candidate_id="cand-2", trade_id="trade-2", signal_epoch=2.0, cost_adjusted_r=4.0),
        _outcome(candidate_id="cand-3", trade_id="trade-3", signal_epoch=3.0, cost_adjusted_r=7.0),
    ]

    group = aggregate_strategy_regime_expectancy(rows).groups[0]
    assert group.median_cost_adjusted_r == 4.0
    assert group.total_cost_adjusted_r == 12.0
    assert group.avg_cost_adjusted_r == 4.0


def test_max_drawdown_deterministic() -> None:
    rows = [
        _outcome(candidate_id="cand-1", trade_id="trade-1", signal_epoch=1.0, cost_adjusted_r=2.0),
        _outcome(candidate_id="cand-2", trade_id="trade-2", signal_epoch=2.0, cost_adjusted_r=-3.0),
        _outcome(candidate_id="cand-3", trade_id="trade-3", signal_epoch=3.0, cost_adjusted_r=4.0),
        _outcome(candidate_id="cand-4", trade_id="trade-4", signal_epoch=4.0, cost_adjusted_r=-1.0),
    ]

    group = aggregate_strategy_regime_expectancy(rows).groups[0]
    assert group.max_drawdown_r == 3.0


def test_markdown_and_json_report_generated(tmp_path: Path) -> None:
    rows = [_outcome(candidate_id=f"cand-{i}", trade_id=f"trade-{i}", signal_epoch=float(i), cost_adjusted_r=1.0) for i in range(1, 31)]

    json_path, md_path, report = write_strategy_regime_expectancy_report(rows, output_dir=tmp_path)
    json_again, md_again = write_strategy_regime_expectancy_reports(rows, output_dir=tmp_path / "nested")

    assert report.schema_version == STRATEGY_REGIME_EXPECTANCY_SCHEMA_VERSION
    assert json_path.exists()
    assert md_path.exists()
    assert json_again.exists()
    assert md_again.exists()
    payload = json.loads(json_path.read_text())
    assert payload["schema_version"] == STRATEGY_REGIME_EXPECTANCY_SCHEMA_VERSION
    assert payload["group_count"] == 1
    assert payload["groups"][0]["keep_watch_kill_status"] == "WATCH"
    markdown = md_path.read_text()
    assert "Strategy-Regime Expectancy Report" in markdown
    assert "Group Metrics" in markdown
    assert "This report does not prove strategy edge or runtime readiness." in markdown


def test_load_candidate_outcomes_from_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "candidate_outcomes.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(row, sort_keys=True)
            for row in [
                _outcome(candidate_id="cand-1", trade_id="trade-1", signal_epoch=1.0, cost_adjusted_r=1.0),
                _outcome(candidate_id="cand-2", trade_id="trade-2", signal_epoch=2.0, cost_adjusted_r=1.0),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_candidate_outcomes(path)
    assert len(loaded) == 2
    assert loaded[0]["candidate_id"] == "cand-1"
