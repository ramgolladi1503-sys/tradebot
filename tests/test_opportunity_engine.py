from __future__ import annotations

from datetime import datetime

from core.opportunity_engine import annotate_ranked_opportunities, select_best_opportunity
from core.trade_schema import Trade


def _trade(
    *,
        trade_id: str,
        confidence: float,
        builder_confidence: float,
        permission_confidence: float,
        gating_final_confidence: float,
        confluence: float,
        bid: float,
        ask: float,
        ltp: float,
        volume: float,
        quote_age_sec: float,
    execution_allowed: bool,
    tradable: bool,
    execution_entry: float | None,
    execution_entry_status: str,
    execution_entry_source: str,
    display_entry: float | None,
    size_mult: float = 1.0,
) -> Trade:
    return Trade(
        trade_id=trade_id,
        timestamp=datetime(2026, 3, 12, 10, 0, 0),
        symbol="NIFTY",
        instrument="OPT",
        instrument_token=12345,
        strike=23850,
        expiry="2026-03-17",
        side="BUY",
        entry_price=121.5,
        stop_loss=110.0,
        target=145.0,
        qty=1,
        capital_at_risk=11.5,
        expected_slippage=0.2,
        confidence=confidence,
        strategy="UNIT",
        regime="TREND",
        builder_confidence=builder_confidence,
        permission_confidence=permission_confidence,
        gating_final_confidence=gating_final_confidence,
        sizing_confluence_score=confluence,
        volume=volume,
        quote_age_sec=quote_age_sec,
        execution_allowed=execution_allowed,
        tradable=tradable,
        execution_entry=execution_entry,
        execution_entry_status=execution_entry_status,
        execution_entry_source=execution_entry_source,
        display_entry=display_entry,
        display_entry_status="displayable" if display_entry is not None else "missing",
        display_entry_source="ask" if display_entry is not None else "none",
        entry_reason="unit_test",
        entry_price_source="ask",
        expected_entry=display_entry,
        expected_entry_source="ask" if display_entry is not None else "none",
        opt_bid=bid,
        opt_ask=ask,
        best_bid=bid,
        best_ask=ask,
        opt_ltp=ltp,
        current_ltp=ltp,
        size_mult=size_mult,
        option_type="CE",
        right="CE",
        instrument_type="OPT",
        tradingsymbol="NIFTY2631723850CE",
        instrument_id="NIFTY|2026-03-17|23850|CE",
    )


def test_opportunity_engine_ranks_executable_candidate_first_and_scales_size():
    ranked = annotate_ranked_opportunities(
        [
            _trade(
                trade_id="T-EXEC-1",
                confidence=0.52,
                builder_confidence=0.52,
                permission_confidence=0.49,
                gating_final_confidence=0.46,
                confluence=0.72,
                bid=120.0,
                ask=121.44,
                ltp=121.0,
                volume=8000,
                quote_age_sec=0.5,
                execution_allowed=True,
                tradable=True,
                execution_entry=121.5,
                execution_entry_status="executable",
                execution_entry_source="ask",
                display_entry=121.5,
            ),
            _trade(
                trade_id="T-EXEC-2",
                confidence=0.64,
                builder_confidence=0.64,
                permission_confidence=0.60,
                gating_final_confidence=0.57,
                confluence=0.85,
                bid=119.0,
                ask=119.72,
                ltp=119.5,
                volume=12000,
                quote_age_sec=0.2,
                execution_allowed=True,
                tradable=True,
                execution_entry=119.5,
                execution_entry_status="executable",
                execution_entry_source="ask",
                display_entry=119.5,
            ),
        ],
        scope="unit:main",
        top_n=1,
    )

    assert [trade.trade_id for trade in ranked] == ["T-EXEC-2", "T-EXEC-1"]
    assert ranked[0].opportunity_rank == 1
    assert ranked[0].selected_for_execution is True
    assert ranked[0].selection_reason == "selected_top_rank"
    assert ranked[0].opportunity_score is not None
    assert ranked[0].opportunity_size_multiplier is not None
    assert ranked[0].size_mult < 1.0
    assert ranked[1].selected_for_execution is False
    assert ranked[1].selection_reason in {"rank_outside_top_n", "below_adaptive_threshold"}


def test_opportunity_engine_keeps_display_only_candidate_non_selected():
    ranked = annotate_ranked_opportunities(
        [
            _trade(
                trade_id="T-DISPLAY",
                confidence=0.61,
                builder_confidence=0.61,
                permission_confidence=0.57,
                gating_final_confidence=0.53,
                confluence=0.76,
                bid=120.4,
                ask=121.6,
                ltp=121.0,
                volume=7000,
                quote_age_sec=0.7,
                execution_allowed=True,
                tradable=True,
                execution_entry=None,
                execution_entry_status="non_executable",
                execution_entry_source="none",
                display_entry=121.0,
            ),
        ],
        scope="unit:display_only",
        top_n=1,
    )

    assert len(ranked) == 1
    assert ranked[0].selected_for_execution is False
    assert ranked[0].selection_reason == "not_execution_eligible"
    assert ranked[0].opportunity_rank == 1
    assert ranked[0].display_entry == 121.0
    assert ranked[0].execution_entry is None


def test_select_best_opportunity_downgrades_non_selected_execution_allowed_trade():
    best, ranked = select_best_opportunity(
        [
            _trade(
                trade_id="T-DISPLAY-BEST",
                confidence=0.61,
                builder_confidence=0.61,
                permission_confidence=0.57,
                gating_final_confidence=0.53,
                confluence=0.76,
                bid=120.4,
                ask=121.6,
                ltp=121.0,
                volume=7000,
                quote_age_sec=0.7,
                execution_allowed=True,
                tradable=True,
                execution_entry=None,
                execution_entry_status="non_executable",
                execution_entry_source="none",
                display_entry=121.0,
            ),
        ],
        scope="unit:select_best",
        top_n=1,
    )

    assert best is not None
    assert ranked[0].selected_for_execution is False
    assert best.execution_allowed is False
    assert "opportunity_not_execution_eligible" in str(best.reason)
