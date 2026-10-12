from __future__ import annotations

from core.analytics.execution_feasibility import _enrich_outcome, evaluate_feasibility
from core.analytics.schema import TradeOutcome


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


def test_quote_enrichment_keeps_path_only_outcome_unassessed_without_quotes():
    outcome = TradeOutcome(
        trade_key="NIFTY|2026-10-29|25000|CE|BUY",
        event_id="out_evt",
        outcome="hit_target",
        ts_epoch_ms=1791776700000,
        symbol="NIFTY",
        exec_feasible=False,
        exec_feasible_flags={
            "outcome_path_observed": True,
            "execution_feasibility_status": "UNASSESSED",
        },
        source="analytics_outcome_replay",
    )
    quote_evidence = evaluate_feasibility(
        side="BUY", intended_entry=100.0, target=104.0,
        bid=None, ask=None, ltp=None, mark_price=None,
        spread_pct=None, quote_age_sec=None,
        max_spread_pct=0.02, max_quote_age_sec=2.0, slippage_allowance=0.2,
    )

    enriched = _enrich_outcome(outcome, quote_evidence)

    assert enriched.exec_feasible is False
    assert enriched.exec_feasible_flags["execution_feasibility_status"] == "UNASSESSED"


def test_quote_enrichment_assesses_replay_only_when_independent_quote_gates_pass():
    outcome = TradeOutcome(
        trade_key="NIFTY|2026-10-29|25000|CE|BUY",
        event_id="out_evt",
        outcome="hit_target",
        ts_epoch_ms=1791776700000,
        symbol="NIFTY",
        exec_feasible=False,
        exec_feasible_flags={
            "outcome_path_observed": True,
            "execution_feasibility_status": "UNASSESSED",
        },
        source="analytics_outcome_replay",
    )
    quote_evidence = {
        "quote_present": True,
        "spread_ok": True,
        "quote_age_ok": True,
        "entry_feasible": True,
        "target_feasible": True,
    }

    enriched = _enrich_outcome(outcome, quote_evidence)

    assert enriched.exec_feasible is True
    assert enriched.exec_feasible_flags["execution_feasibility_status"] == "ASSESSED_FEASIBLE"


def test_quote_enrichment_marks_present_but_failing_quote_as_assessed_infeasible():
    outcome = TradeOutcome(
        trade_key="NIFTY|2026-10-29|25000|CE|BUY",
        event_id="out_evt",
        outcome="hit_target",
        ts_epoch_ms=1791776700000,
        symbol="NIFTY",
        exec_feasible=False,
        exec_feasible_flags={
            "outcome_path_observed": True,
            "execution_feasibility_status": "UNASSESSED",
        },
        source="analytics_outcome_replay",
    )
    quote_evidence = {
        "quote_present": True,
        "spread_ok": False,
        "quote_age_ok": True,
        "entry_feasible": True,
        "target_feasible": True,
    }

    enriched = _enrich_outcome(outcome, quote_evidence)

    assert enriched.exec_feasible is False
    assert enriched.exec_feasible_flags["execution_feasibility_status"] == "ASSESSED_INFEASIBLE"
