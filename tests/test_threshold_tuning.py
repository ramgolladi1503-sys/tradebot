from __future__ import annotations

from config import config as cfg
from core.opportunity_engine import _get_contextual_threshold_adjustment
from core.threshold_tuning import (
    build_threshold_tuning_recommendations,
    should_protect_gate,
)


def _base_inputs():
    return {
        "rejection_impact_summary": {
            "by_stage_strategy_family": {},
        },
        "starvation_by_group_summary": {
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


def test_recommendations_loosen_missed_win_heavy_gate(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_TUNING_MIN_IMPACT_SCORE", 0.20, raising=False)
    payload = _base_inputs()
    payload["rejection_impact_summary"]["by_stage_strategy_family"] = {
        "trigger|continuation": {
            "rejected_at_stage": "trigger",
            "strategy_family": "continuation",
            "reject_count": 12,
            "saved_loss_rate": 0.10,
            "missed_win_rate": 0.70,
            "impact_score": 0.60,
        }
    }

    recs = build_threshold_tuning_recommendations(**payload)

    assert recs["gates_to_loosen"][0]["gate_key"] == "trigger|continuation"
    assert recs["gates_to_loosen"][0]["gate_protected_flag"] is False


def test_recommendations_protect_saved_loss_heavy_gate(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_TUNING_PROTECT_SAVED_LOSS_RATE", 0.40, raising=False)
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

    recs = build_threshold_tuning_recommendations(**payload)

    assert recs["gates_to_protect"][0]["gate_key"] == "selector|mean_reversion"
    assert recs["gates_to_protect"][0]["protection_reason"] == "saved_loss_rate_high"


def test_recommendations_do_not_relax_hard_risk_gates():
    gate = {
        "rejected_at_stage": "risk_budget",
        "saved_loss_rate": 0.10,
    }

    assert should_protect_gate(gate) is True

    payload = _base_inputs()
    payload["rejection_impact_summary"]["by_stage_strategy_family"] = {
        "risk_budget|continuation": {
            "rejected_at_stage": "risk_budget",
            "strategy_family": "continuation",
            "reject_count": 20,
            "saved_loss_rate": 0.10,
            "missed_win_rate": 0.80,
            "impact_score": 0.70,
        }
    }
    payload["top_damaging_gates"]["gates"] = [
        {
            "gate_key": "risk_budget|continuation",
            "rejected_at_stage": "risk_budget",
            "strategy_family": "continuation",
            "impact_score": 0.70,
        }
    ]
    recs = build_threshold_tuning_recommendations(**payload)

    assert not recs["gates_to_loosen"]
    assert recs["gates_to_protect"][0]["gate_key"] == "risk_budget|continuation"
    assert recs["recommended_contextual_adjustments"] == {}


def test_starvation_group_with_no_edge_improvement_gets_relief_recommendation(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_TUNING_STARVATION_RELIEF_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_TUNING_MAX_DELTA", 0.03, raising=False)
    payload = _base_inputs()
    payload["rejection_impact_summary"]["by_stage_strategy_family"] = {
        "trigger|continuation": {
            "rejected_at_stage": "trigger",
            "strategy_family": "continuation",
            "reject_count": 14,
            "saved_loss_rate": 0.10,
            "missed_win_rate": 0.72,
            "impact_score": 0.62,
        }
    }
    payload["top_damaging_gates"]["gates"] = [
        {
            "gate_key": "trigger|continuation",
            "rejected_at_stage": "trigger",
            "strategy_family": "continuation",
            "impact_score": 0.62,
        }
    ]
    payload["starvation_by_group_summary"]["strategy_family__session_mode"] = {
        "continuation|MIDDAY": {
            "strategy_family": "continuation",
            "session_mode": "MIDDAY",
            "raw_candidate_count": 20,
            "survived_candidate_count": 2,
            "survival_rate": 0.10,
            "starvation_flag": True,
            "starvation_reason": "survival_rate_below_floor",
        }
    }
    payload["starvation_by_group_summary"]["strategy_family__strategy_regime_mode"] = {
        "continuation|TRENDING": {
            "strategy_family": "continuation",
            "strategy_regime_mode": "TRENDING",
            "raw_candidate_count": 20,
            "survived_candidate_count": 2,
            "survival_rate": 0.10,
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
            "survival_rate": 0.10,
            "edge_improved_flag": False,
            "filtering_without_edge_flag": True,
            "median_realized_r_multiple": 0.0,
        }
    }

    recs = build_threshold_tuning_recommendations(**payload)
    key = "trigger|continuation|MIDDAY|TRENDING"

    assert key in recs["recommended_contextual_adjustments"]
    assert float(recs["recommended_contextual_adjustments"][key]["recommended_delta"]) < 0.0


def test_starvation_group_with_edge_improvement_gets_no_relief_recommendation(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_TUNING_STARVATION_RELIEF_ENABLE", True, raising=False)
    payload = _base_inputs()
    payload["rejection_impact_summary"]["by_stage_strategy_family"] = {
        "trigger|continuation": {
            "rejected_at_stage": "trigger",
            "strategy_family": "continuation",
            "reject_count": 14,
            "saved_loss_rate": 0.10,
            "missed_win_rate": 0.72,
            "impact_score": 0.62,
        }
    }
    payload["top_damaging_gates"]["gates"] = [
        {
            "gate_key": "trigger|continuation",
            "rejected_at_stage": "trigger",
            "strategy_family": "continuation",
            "impact_score": 0.62,
        }
    ]
    payload["starvation_by_group_summary"]["strategy_family__session_mode"] = {
        "continuation|MIDDAY": {
            "strategy_family": "continuation",
            "session_mode": "MIDDAY",
            "raw_candidate_count": 20,
            "survived_candidate_count": 2,
            "survival_rate": 0.10,
            "starvation_flag": True,
            "starvation_reason": "survival_rate_below_floor",
        }
    }
    payload["starvation_by_group_summary"]["strategy_family__strategy_regime_mode"] = {
        "continuation|TRENDING": {
            "strategy_family": "continuation",
            "strategy_regime_mode": "TRENDING",
            "raw_candidate_count": 20,
            "survived_candidate_count": 2,
            "survival_rate": 0.10,
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
            "survival_rate": 0.10,
            "edge_improved_flag": True,
            "filtering_without_edge_flag": False,
            "median_realized_r_multiple": 0.35,
        }
    }

    recs = build_threshold_tuning_recommendations(**payload)

    assert recs["recommended_contextual_adjustments"] == {}


def test_contextual_threshold_adjustment_reads_recommendation_map():
    recommendations = {
        "recommended_contextual_adjustments": {
            "trigger|continuation|MIDDAY|TRENDING": {
                "recommended_delta": -0.02,
            }
        }
    }

    delta = _get_contextual_threshold_adjustment(
        "trigger",
        "continuation",
        "MIDDAY",
        "TRENDING",
        recommendations,
    )

    assert delta == -0.02
