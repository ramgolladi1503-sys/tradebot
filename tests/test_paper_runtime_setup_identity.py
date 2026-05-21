from __future__ import annotations

from types import SimpleNamespace

from core.paper_runtime_setup_identity import (
    attach_runtime_setup_identity,
    runtime_setup_identity_from_trade,
)


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


def test_attach_runtime_setup_identity_preserves_existing_payload():
    trade = SimpleNamespace(
        setup_id="orb_breakout_v1",
        regime_key="trend_morning",
        entry_rule_id="orb_high_break_with_volume",
        exit_rule_id="target_stop_or_time_exit",
        cost_model_version="cost_v1",
    )

    enriched = attach_runtime_setup_identity(
        {"candidate_id": "trade-1", "terminal_status": "executed"},
        trade,
    )

    assert enriched["candidate_id"] == "trade-1"
    assert enriched["terminal_status"] == "executed"
    assert enriched["setup_id"] == "orb_breakout_v1"
    assert enriched["regime_key"] == "trend_morning"
    assert enriched["entry_rule_id"] == "orb_high_break_with_volume"
    assert enriched["exit_rule_id"] == "target_stop_or_time_exit"
    assert enriched["cost_model_version"] == "cost_v1"
