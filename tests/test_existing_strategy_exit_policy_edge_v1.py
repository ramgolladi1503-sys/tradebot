from datetime import datetime, timedelta, timezone

import pytest

from research.existing_strategy_exit_policy_edge_v1.contract import ExitPolicy, frozen_contract
from research.existing_strategy_exit_policy_edge_v1.evaluator import CostModel, OptionBar, evaluate_long_option_trade, remove_top_winners, summarize


def _bar(minute: int, *, open_: float, high: float, low: float, close: float) -> OptionBar:
    return OptionBar(
        timestamp=datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc) + timedelta(minutes=minute),
        open=open_,
        high=high,
        low=low,
        close=close,
    )


def test_stop_first_when_target_and_stop_touch_same_bar() -> None:
    outcome = evaluate_long_option_trade(
        strategy_id="opening_range_retest_v1",
        signal_id="s1",
        bars=[_bar(0, open_=100, high=106, low=89, close=103)],
        entry_price=100,
        risk_points=10,
        policy=ExitPolicy(target_r=0.50, max_hold_minutes=5),
        costs=CostModel(),
    )
    assert outcome.exit_reason == "STOP"
    assert outcome.gross_r == pytest.approx(-1.0)


def test_target_hit_and_costs_reduce_net_expectancy() -> None:
    outcome = evaluate_long_option_trade(
        strategy_id="vwap_reclaim_v1",
        signal_id="s2",
        bars=[_bar(0, open_=100, high=106, low=99, close=105)],
        entry_price=100,
        risk_points=10,
        policy=ExitPolicy(target_r=0.50, max_hold_minutes=5),
        costs=CostModel(entry_slippage_points=1, exit_slippage_points=1, fixed_round_trip_rupees=65, quantity=65),
    )
    assert outcome.exit_reason == "TARGET"
    assert outcome.gross_r == pytest.approx(0.5)
    assert outcome.net_r == pytest.approx(0.3)


def test_time_exit_uses_last_bar_inside_deadline() -> None:
    bars = [
        _bar(0, open_=100, high=102, low=99, close=101),
        _bar(5, open_=101, high=103, low=100, close=102),
        _bar(6, open_=102, high=120, low=102, close=119),
    ]
    outcome = evaluate_long_option_trade(
        strategy_id="trend_pullback_v1",
        signal_id="s3",
        bars=bars,
        entry_price=100,
        risk_points=10,
        policy=ExitPolicy(target_r=1.0, max_hold_minutes=5),
        costs=CostModel(),
    )
    assert outcome.exit_reason == "TIME_EXIT"
    assert outcome.exit_time == bars[1].timestamp
    assert outcome.gross_r == pytest.approx(0.2)


def test_summary_and_top_winner_removal() -> None:
    policies = ExitPolicy(target_r=0.50, max_hold_minutes=5)
    outcomes = [
        evaluate_long_option_trade(
            strategy_id="opening_range_retest_v1",
            signal_id=f"s{i}",
            bars=[_bar(0, open_=100, high=high, low=low, close=close)],
            entry_price=100,
            risk_points=10,
            policy=policies,
            costs=CostModel(),
        )
        for i, (high, low, close) in enumerate([(106, 99, 105), (106, 99, 105), (102, 89, 90), (101, 99, 100)])
    ]
    summary = summarize(outcomes)
    assert summary["trade_count"] == 4
    assert summary["target_count"] == 2
    assert len(remove_top_winners(outcomes, 1)) == 3


def test_contract_is_research_only_and_hash_stable() -> None:
    first = frozen_contract(base_commit_sha="a" * 40, source_manifest="manifest.json")
    second = frozen_contract(base_commit_sha="a" * 40, source_manifest="manifest.json")
    assert first == second
    assert first["safety"]["allowed_for_live_execution"] is False
    assert "NOT_PRODUCTION_READY" in first["claim_boundary"]
