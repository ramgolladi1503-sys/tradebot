from __future__ import annotations

from config import config as cfg
from core.threshold_triage import build_tuning_shortlist


def _base_inputs():
    return {
        "rejection_impact_summary": {
            "by_stage_strategy_family": {},
        },
        "starvation_by_group_summary": {
            "strategy_family": {},
            "direction_family": {},
            "session_mode": {},
            "strategy_regime_mode": {},
            "strategy_family__session_mode": {},
            "strategy_family__strategy_regime_mode": {},
        },
        "survival_expectancy_summary": {
            "groups": {},
        },
        "top_damaging_gates": {
            "gates": [],
        },
    }


def test_tuning_shortlist_identifies_damaging_missed_win_gate(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_TRIAGE_MIN_MISSED_WIN_RATE", 0.30, raising=False)
    payload = _base_inputs()
    payload["rejection_impact_summary"]["by_stage_strategy_family"] = {
        "trigger|continuation": {
            "rejected_at_stage": "trigger",
            "strategy_family": "continuation",
            "reject_count": 12,
            "saved_loss_rate": 0.10,
            "missed_win_rate": 0.72,
            "impact_score": 0.62,
        }
    }
    payload["top_damaging_gates"]["gates"] = [
        {
            "rank": 1,
            "gate_key": "trigger|continuation",
            "rejected_at_stage": "trigger",
            "strategy_family": "continuation",
            "impact_score": 0.62,
        }
    ]

    shortlist = build_tuning_shortlist(**payload, top_n=3)

    assert shortlist["gates_to_loosen"][0]["gate_key"] == "trigger|continuation"
    assert shortlist["gates_to_loosen"][0]["triage_recommendation"] == "review_loosen_gate"


def test_threshold_triage_identifies_damaging_gate(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_TRIAGE_MIN_MISSED_WIN_RATE", 0.30, raising=False)
    payload = _base_inputs()
    payload["rejection_impact_summary"]["by_stage_strategy_family"] = {
        "trigger|continuation": {
            "rejected_at_stage": "trigger",
            "strategy_family": "continuation",
            "reject_count": 12,
            "saved_loss_rate": 0.10,
            "missed_win_rate": 0.72,
            "impact_score": 0.62,
        }
    }
    payload["top_damaging_gates"]["gates"] = [
        {
            "rank": 1,
            "gate_key": "trigger|continuation",
            "rejected_at_stage": "trigger",
            "strategy_family": "continuation",
            "impact_score": 0.62,
        }
    ]

    shortlist = build_tuning_shortlist(**payload, top_n=3)

    assert shortlist["gates_to_loosen"][0]["gate_key"] == "trigger|continuation"
    assert shortlist["gates_to_loosen"][0]["gate_protected_flag"] is False


def test_tuning_shortlist_protects_saved_loss_gate(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_TRIAGE_PROTECT_SAVED_LOSS_RATE", 0.40, raising=False)
    payload = _base_inputs()
    payload["rejection_impact_summary"]["by_stage_strategy_family"] = {
        "selector|mean_reversion": {
            "rejected_at_stage": "selector",
            "strategy_family": "mean_reversion",
            "reject_count": 15,
            "saved_loss_rate": 0.65,
            "missed_win_rate": 0.05,
            "impact_score": -0.60,
        }
    }

    shortlist = build_tuning_shortlist(**payload, top_n=3)

    assert shortlist["gates_to_protect"][0]["gate_key"] == "selector|mean_reversion"
    assert shortlist["gates_to_protect"][0]["gate_protected_flag"] is True
    assert not shortlist["gates_to_loosen"]


def test_threshold_triage_protects_saved_loss_gate(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_TRIAGE_PROTECT_SAVED_LOSS_RATE", 0.40, raising=False)
    payload = _base_inputs()
    payload["rejection_impact_summary"]["by_stage_strategy_family"] = {
        "selector|mean_reversion": {
            "rejected_at_stage": "selector",
            "strategy_family": "mean_reversion",
            "reject_count": 15,
            "saved_loss_rate": 0.65,
            "missed_win_rate": 0.05,
            "impact_score": -0.60,
        }
    }

    shortlist = build_tuning_shortlist(**payload, top_n=3)

    assert shortlist["gates_to_protect"][0]["gate_key"] == "selector|mean_reversion"
    assert shortlist["gates_to_protect"][0]["gate_protected_flag"] is True
    assert not shortlist["gates_to_loosen"]


def test_tuning_shortlist_flags_starvation_without_edge_improvement(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR", 0.25, raising=False)
    payload = _base_inputs()
    payload["starvation_by_group_summary"]["strategy_family__session_mode"] = {
        "continuation|MIDDAY": {
            "strategy_family": "continuation",
            "session_mode": "MIDDAY",
            "raw_candidate_count": 20,
            "survived_candidate_count": 2,
            "survival_rate": 0.10,
            "no_trade_rate": 0.75,
            "starvation_flag": True,
            "starvation_reason": "survival_rate_below_floor",
        }
    }
    payload["survival_expectancy_summary"]["groups"] = {
        "continuation|bullish|TRENDING|MIDDAY": {
            "strategy_family": "continuation",
            "direction_family": "bullish",
            "strategy_regime_mode": "TRENDING",
            "session_mode": "MIDDAY",
            "raw_candidates": 20,
            "survived_candidates": 2,
            "survival_rate": 0.10,
            "median_realized_r_multiple": 0.0,
            "edge_improved_flag": False,
            "filtering_without_edge_flag": True,
        }
    }

    shortlist = build_tuning_shortlist(**payload, top_n=3)

    assert shortlist["starvation_groups_to_review"][0]["group_key"] == "continuation|MIDDAY"
    assert shortlist["starvation_groups_to_review"][0]["triage_recommendation"] == "review_starvation_group"


def test_threshold_triage_flags_starvation_without_edge_improvement(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR", 0.25, raising=False)
    payload = _base_inputs()
    payload["rejection_impact_summary"]["by_stage_strategy_family"] = {
        "trigger|continuation": {
            "rejected_at_stage": "trigger",
            "strategy_family": "continuation",
            "reject_count": 12,
            "saved_loss_rate": 0.10,
            "missed_win_rate": 0.72,
            "impact_score": 0.62,
        }
    }
    payload["starvation_by_group_summary"]["strategy_family__session_mode"] = {
        "continuation|MIDDAY": {
            "strategy_family": "continuation",
            "session_mode": "MIDDAY",
            "raw_candidate_count": 20,
            "survived_candidate_count": 2,
            "survival_rate": 0.10,
            "no_trade_rate": 0.75,
            "starvation_flag": True,
            "starvation_reason": "survival_rate_below_floor",
        }
    }
    payload["survival_expectancy_summary"]["groups"] = {
        "continuation|bullish|TRENDING|MIDDAY": {
            "strategy_family": "continuation",
            "direction_family": "bullish",
            "strategy_regime_mode": "TRENDING",
            "session_mode": "MIDDAY",
            "raw_candidates": 20,
            "survived_candidates": 2,
            "survival_rate": 0.10,
            "median_realized_r_multiple": 0.0,
            "edge_improved_flag": False,
            "filtering_without_edge_flag": True,
        }
    }

    shortlist = build_tuning_shortlist(**payload, top_n=3)
    key = "trigger|continuation|MIDDAY|TRENDING"

    assert shortlist["starvation_groups_to_review"][0]["group_key"] == "continuation|MIDDAY"
    assert shortlist["recommended_contextual_adjustments"][key]["recommended_delta"] < 0.0


def test_tuning_shortlist_leaves_edge_improved_group_alone(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_TRIAGE_MIN_EDGE_R_DELTA", 0.05, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR", 0.25, raising=False)
    payload = _base_inputs()
    payload["survival_expectancy_summary"]["groups"] = {
        "continuation|bullish|TRENDING|MIDDAY": {
            "strategy_family": "continuation",
            "direction_family": "bullish",
            "strategy_regime_mode": "TRENDING",
            "session_mode": "MIDDAY",
            "raw_candidates": 20,
            "survived_candidates": 2,
            "survival_rate": 0.10,
            "median_realized_r_multiple": 0.30,
            "edge_improved_flag": True,
            "filtering_without_edge_flag": False,
        }
    }

    shortlist = build_tuning_shortlist(**payload, top_n=3)

    assert shortlist["edge_improved_groups_to_leave_alone"][0]["group_key"] == "continuation|bullish|TRENDING|MIDDAY"
    assert shortlist["edge_improved_groups_to_leave_alone"][0]["edge_preserve_flag"] is True
    assert not shortlist["starvation_groups_to_review"]


def test_threshold_triage_leaves_edge_improved_group_alone(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_TRIAGE_MIN_EDGE_R_DELTA", 0.05, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR", 0.25, raising=False)
    payload = _base_inputs()
    payload["survival_expectancy_summary"]["groups"] = {
        "continuation|bullish|TRENDING|MIDDAY": {
            "strategy_family": "continuation",
            "direction_family": "bullish",
            "strategy_regime_mode": "TRENDING",
            "session_mode": "MIDDAY",
            "raw_candidates": 20,
            "survived_candidates": 2,
            "survival_rate": 0.10,
            "median_realized_r_multiple": 0.30,
            "edge_improved_flag": True,
            "filtering_without_edge_flag": False,
        }
    }

    shortlist = build_tuning_shortlist(**payload, top_n=3)

    assert shortlist["edge_improved_groups_to_leave_alone"][0]["group_key"] == "continuation|bullish|TRENDING|MIDDAY"
    assert shortlist["edge_improved_groups_to_leave_alone"][0]["edge_preserve_flag"] is True
    assert shortlist["recommended_contextual_adjustments"] == {}
