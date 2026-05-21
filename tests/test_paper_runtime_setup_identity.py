from __future__ import annotations

from types import SimpleNamespace

from core.paper_runtime_setup_identity import runtime_setup_identity_from_trade


def test_runtime_setup_identity_extracts_supplied_trade_fields():
    trade = SimpleNamespace(
        setup_id="orb_breakout_v1",
        regime_key="trend_morning",
        entry_rule_id="orb_high_break_with_volume",
        exit_rule_id="target_stop_or_time_exit",
        cost_model_version="cost_v1",
        score_bucket="0.75-1.00",
    )

    assert runtime_setup_identity_from_trade(trade) == {
        "setup_id": "orb_breakout_v1",
        "regime_key": "trend_morning",
        "entry_rule_id": "orb_high_break_with_volume",
        "exit_rule_id": "target_stop_or_time_exit",
        "cost_model_version": "cost_v1",
        "score_bucket": "0.75-1.00",
    }


def test_runtime_setup_identity_does_not_fabricate_missing_fields():
    trade = SimpleNamespace(strategy_family="orb", regime="trend", final_score=0.84)

    assert runtime_setup_identity_from_trade(trade) == {}


def test_runtime_setup_identity_skips_blank_fields():
    trade = SimpleNamespace(
        setup_id="orb_breakout_v1",
        regime_key="",
        entry_rule_id=None,
        exit_rule_id="target_stop_or_time_exit",
        cost_model_version="None",
    )

    assert runtime_setup_identity_from_trade(trade) == {
        "setup_id": "orb_breakout_v1",
        "exit_rule_id": "target_stop_or_time_exit",
    }
