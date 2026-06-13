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


@pytest.mark.parametrize(
    "overrides",
    [
        {"quote_source": "REST_FALLBACK", "fallback_used": False},
        {"quote_source": "SYNTHETIC_OFFHOURS", "fallback_used": False},
        {"quote_source": "SUBSCRIPTION_FAILED", "fallback_used": False},
        {"row_kind": "recovered_fallback", "fallback_used": False},
        {"candidate_class": "fallback", "fallback_used": False},
        {"candidate_type": "execution_fallback", "fallback_used": False},
        {"candidate_origin": "fallback_recovery", "fallback_used": False},
        {"trade_id": "softrej_trade-1", "fallback_used": False},
    ],
)
def test_fallback_truth_cannot_become_top_executable_even_when_row_claims_execute(overrides):
    """
    Edge purpose:
    Prevents fake executable opportunities from fallback, recovered, synthetic,
    soft-rejected, or subscription-failed quote paths.
    """
    row_overrides = dict(overrides)
    row_overrides.setdefault("trade_id", "trade-fallback-liar")

    report = select_top_opportunities(
        [
            _executable_claim(
                candidate_id="cand-fallback-liar",
                edge_rank_score=0.99,
                rank_score=0.98,
                confidence_final=0.97,
                **row_overrides,
            )
        ]
    )

    assert report.executable_count == 0
    assert report.rejected_count == 1
    assert report.rejected_opportunities[0].candidate_id == "cand-fallback-liar"
    assert "fallback_not_rankable" in report.rejected_opportunities[0].why_not_ranked


def test_clean_live_quote_can_still_become_top_executable_after_fallback_firewall():
    """
    Edge purpose:
    Protects real trading edge by proving the fallback firewall does not over-block a clean,
    live, expectancy-positive candidate with execution truth.
    """
    report = select_top_opportunities(
        [_executable_claim(candidate_id="cand-clean-live", trade_id="trade-clean-live")]
    )

    assert report.executable_count == 1
    assert report.executable_opportunities[0].candidate_id == "cand-clean-live"
    assert report.rejected_count == 0
