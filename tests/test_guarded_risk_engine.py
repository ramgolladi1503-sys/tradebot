from __future__ import annotations

from core.guarded_risk_engine import evaluate_candidate_risk_guarded


def _candidate(**overrides):
    row = {
        "trade_id": "T-GUARDED-RISK",
        "symbol": "NIFTY",
        "strategy_family": "unit",
        "direction_family": "bullish",
        "execution_entry": 120.0,
        "entry_price": 120.0,
        "stop_loss": 110.0,
        "target": 140.0,
        "opt_ltp": 120.0,
        "current_ltp": 120.0,
        "best_bid": 119.8,
        "best_ask": 120.2,
        "spread_pct": 0.003,
        "liquidity_score": 0.82,
        "quote_age_sec": 0.3,
        "max_quote_age_sec": 2.0,
        "quote_source": "live_broker",
        "spread_source": "live_book",
        "liquidity_source": "live_book",
        "contract_exact_match": True,
        "execution_entry_status": "executable",
        "execution_entry_source": "ask",
    }
    row.update(overrides)
    return row


def _portfolio():
    return {
        "capital": 100000.0,
        "risk_per_trade_pct": 0.004,
        "open_risk_pct": 0.0,
        "directional_heat": {},
        "family_exposure": {},
        "daily_kill_switch_active": False,
    }


def test_guarded_risk_allows_clean_candidate_to_use_normal_risk_flow():
    result = evaluate_candidate_risk_guarded(_candidate(), portfolio_state=_portfolio())

    assert result.context["data_risk_allowed"] is True
    assert result.context["data_risk_reason_code"] == "data_risk_ok"
    assert result.context["data_quality_grade"] == "A"


def test_guarded_risk_blocks_dirty_data_even_if_trade_math_is_good():
    result = evaluate_candidate_risk_guarded(
        _candidate(
            phase2_spread_fallback_used=True,
            spread_source="fallback_default",
        ),
        portfolio_state=_portfolio(),
    )

    assert result.risk_budget_ok is False
    assert result.risk_budget_reason == "data_risk_block:fallback_spread"
    assert result.rejected_at_stage == "risk_data_truth"
    assert result.rejection_bucket == "DATA_RISK"
    assert result.rejection_severity == "hard"
    assert "fallback_spread" in result.context["data_truth_blockers"]


def test_guarded_risk_blocks_unknown_quote_source():
    result = evaluate_candidate_risk_guarded(
        _candidate(quote_source="unknown"),
        portfolio_state=_portfolio(),
    )

    assert result.risk_budget_ok is False
    assert result.risk_budget_reason == "data_risk_block:unknown_quote_source"
    assert result.context["data_risk_allowed"] is False
