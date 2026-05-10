from __future__ import annotations

from core.risk_data_guard import evaluate_data_risk


def _candidate(**overrides):
    row = {
        "trade_id": "T-RISK-DATA",
        "symbol": "NIFTY",
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
        "execution_entry": 120.2,
        "execution_entry_status": "executable",
        "execution_entry_source": "ask",
    }
    row.update(overrides)
    return row


def test_data_risk_allows_clean_candidate():
    result = evaluate_data_risk(_candidate())

    assert result.allowed is True
    assert result.reason_code == "data_risk_ok"
    assert result.data_quality_grade == "A"


def test_data_risk_blocks_fallback_spread():
    result = evaluate_data_risk(
        _candidate(
            phase2_spread_fallback_used=True,
            spread_source="fallback_default",
        )
    )

    assert result.allowed is False
    assert result.data_quality_grade == "D"
    assert result.reason_code == "data_risk_block:fallback_spread"
    assert "fallback_spread" in result.blockers
    assert "spread_pct" in result.fallback_fields


def test_data_risk_context_is_dashboard_and_report_friendly():
    result = evaluate_data_risk(_candidate(quote_source="unknown"))
    context = result.to_context()

    assert context["data_risk_allowed"] is False
    assert context["data_risk_reason_code"] == "data_risk_block:unknown_quote_source"
    assert context["data_quality_grade"] == "D"
    assert "unknown_quote_source" in context["data_truth_blockers"]
