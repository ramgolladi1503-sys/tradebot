from __future__ import annotations

from config import config as cfg
from core.risk_engine import adjust_system_aggressiveness, evaluate_candidate_risk


def _candidate(**overrides):
    base = {
        "symbol": "NIFTY",
        "strategy_family": "continuation",
        "direction_family": "bullish",
        "regime": "TREND",
        "session_mode": "MIDDAY",
        "entry_price": 100.0,
        "execution_entry": 100.0,
        "stop_loss": 95.0,
        "target": 110.0,
        "qty": 1,
    }
    base.update(overrides)
    return base


def test_position_size_respects_stop_distance(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_RISK_PER_TRADE_PCT", 0.01, raising=False)
    portfolio = {"capital": 100000.0}

    tight = evaluate_candidate_risk(_candidate(stop_loss=98.0), portfolio_state=portfolio)
    wide = evaluate_candidate_risk(_candidate(stop_loss=85.0), portfolio_state=portfolio)

    assert tight.position_size_estimate > wide.position_size_estimate


def test_wide_stop_candidate_fails_risk_budget(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_RISK_MAX_STOP_DISTANCE_PCT", 0.10, raising=False)

    assessment = evaluate_candidate_risk(_candidate(stop_loss=70.0))

    assert assessment.risk_budget_ok is False
    assert assessment.risk_budget_reason == "stop_distance_too_wide_pct"


def test_portfolio_heat_blocks_extra_correlated_candidate(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_RISK_MAX_PORTFOLIO_HEAT", 0.02, raising=False)

    assessment = evaluate_candidate_risk(
        _candidate(),
        portfolio_state={"open_risk_pct": 0.03},
    )

    assert assessment.exposure_blocker == "portfolio_heat_limit"
    assert float(assessment.portfolio_heat_score) >= 0.03


def test_family_exposure_cap_prevents_same_idea_flooding(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_RISK_MAX_FAMILY_EXPOSURE", 1, raising=False)

    assessment = evaluate_candidate_risk(
        _candidate(strategy_family="continuation", direction_family="bullish"),
        portfolio_state={"family_exposure": {"continuation|bullish": 1}},
    )

    assert assessment.exposure_blocker == "family_exposure_limit"


def test_aggressiveness_mode_detects_starvation():
    mode = adjust_system_aggressiveness(
        {
            "survival_rate": 0.18,
            "no_trade_rate": 0.85,
        }
    )

    assert mode == "STARVING"


def test_risk_engine_reads_risk_policy_without_behavior_change(monkeypatch):
    original = cfg.get_risk_policy
    baseline = evaluate_candidate_risk(_candidate(stop_loss=98.0), portfolio_state={"capital": 100000.0})

    def _wrapped_policy():
        policy = dict(original())
        policy["policy_source"] = "test_risk_policy"
        return policy

    monkeypatch.setattr(cfg, "get_risk_policy", _wrapped_policy, raising=True)

    assessment = evaluate_candidate_risk(_candidate(stop_loss=98.0), portfolio_state={"capital": 100000.0})

    assert assessment.risk_budget_ok == baseline.risk_budget_ok
    assert assessment.position_size_estimate == baseline.position_size_estimate
    assert assessment.context["effective_risk_policy"]["policy_source"] == "test_risk_policy"
