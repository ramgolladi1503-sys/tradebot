from __future__ import annotations

from core.analytics.execution_feasibility import evaluate_feasibility


def test_evaluate_feasibility_buy_entry_and_target():
    result = evaluate_feasibility(
        side="BUY",
        intended_entry=100.0,
        target=104.0,
        bid=99.8,
        ask=100.0,
        ltp=99.9,
        mark_price=99.9,
        spread_pct=0.002,
        quote_age_sec=0.5,
        max_spread_pct=0.02,
        max_quote_age_sec=2.0,
        slippage_allowance=0.2,
    )

    assert result["entry_feasible"] is True
    assert result["target_feasible"] is False
    assert result["quality_label"] == "TARGET_NOT_FEASIBLE"
