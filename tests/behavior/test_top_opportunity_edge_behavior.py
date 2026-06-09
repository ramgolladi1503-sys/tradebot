from __future__ import annotations

import pytest

from core.expectancy.top_opportunity_selector import select_top_opportunities


pytestmark = [pytest.mark.behavior, pytest.mark.edge, pytest.mark.safety, pytest.mark.regression]


def _executable_claim(**overrides):
    row = {
        "candidate_id": "cand-clean",
        "trade_id": "trade-clean",
        "symbol": "NIFTY",
        "index": "NIFTY",
        "strategy_family": "breakout",
        "setup_id": "breakout__LIVE__HIGH__HIGH__TIGHT__BUY__NIFTY__CE",
        "regime": "TREND",
        "direction": "BUY",
        "edge_rank_score": 0.86,
        "rank_score": 0.78,
        "confidence_final": 0.74,
        "expectancy_status": "KEEP",
        "expectancy_sample_count": 64,
        "expectancy_avg_cost_adjusted_r": 0.24,
        "execution_truth_state": "LIVE",
        "execution_status": "executable",
        "reportable_executable": True,
        "execution_allowed": True,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "fallback_used": False,
        "quote_source": "LIVE_WS_DEPTH",
        "blockers": [],
    }
    row.update(overrides)
    return row


def test_rest_fallback_quote_source_cannot_become_top_executable_even_when_row_claims_execute():
    """
    Edge purpose:
    Prevents fake executable opportunities from REST fallback quote data.
    A row may carry EXECUTE flags from an upstream bug or stale artifact, but the selector must
    use product truth: fallback-derived quotes are display/debug evidence, never executable edge.
    """
    report = select_top_opportunities(
        [
            _executable_claim(
                candidate_id="cand-rest-fallback-liar",
                trade_id="trade-rest-fallback-liar",
                quote_source="REST_FALLBACK",
                fallback_used=False,
                edge_rank_score=0.99,
                rank_score=0.98,
                confidence_final=0.97,
            )
        ]
    )

    assert report.executable_count == 0
    assert report.rejected_count == 1
    assert report.rejected_opportunities[0].candidate_id == "cand-rest-fallback-liar"
    assert "fallback_not_rankable" in report.rejected_opportunities[0].why_not_ranked


def test_clean_live_quote_can_still_become_top_executable_after_fallback_firewall():
    """
    Edge purpose:
    Protects real trading edge by proving the fallback firewall does not over-block a clean,
    live, expectancy-positive candidate with execution truth.
    """
    report = select_top_opportunities([_executable_claim(candidate_id="cand-clean-live", trade_id="trade-clean-live")])

    assert report.executable_count == 1
    assert report.executable_opportunities[0].candidate_id == "cand-clean-live"
    assert report.rejected_count == 0
