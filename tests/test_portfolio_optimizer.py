from __future__ import annotations

from datetime import datetime

from config import config as cfg
from core.opportunity_engine import select_top_opportunities
from core.portfolio_optimizer import optimize_portfolio_selection
from core.trade_schema import Trade


def _trade(
    *,
    trade_id: str,
    symbol: str,
    right: str,
    setup_family: str,
    opportunity_score: float,
    capital_assigned: float,
    selected_for_execution: bool = True,
    slot_id: str | None = None,
    allocation_reason: str = "allocated",
) -> Trade:
    normalized_symbol = str(symbol).strip().upper()
    normalized_right = str(right).strip().upper()
    source_flags = {
        "candidate_origin": {
            "setup_family": setup_family,
        },
        "setup_family": setup_family,
    }
    return Trade(
        trade_id=trade_id,
        timestamp=datetime(2026, 3, 19, 10, 0, 0),
        symbol=normalized_symbol,
        instrument="OPT",
        instrument_token=12345,
        strike=23850,
        expiry="2026-03-26",
        side="BUY",
        entry_price=120.0,
        stop_loss=110.0,
        target=145.0,
        qty=1,
        capital_at_risk=12.0,
        expected_slippage=0.2,
        confidence=opportunity_score,
        strategy="UNIT",
        regime="TREND",
        builder_confidence=opportunity_score,
        permission_confidence=opportunity_score,
        gating_final_confidence=opportunity_score,
        opportunity_score=opportunity_score,
        allocation_score=opportunity_score,
        execution_allowed=True,
        tradable=True,
        execution_entry=120.5,
        execution_entry_status="executable",
        execution_entry_source="ask",
        display_entry=120.5,
        display_entry_status="displayable",
        display_entry_source="ask",
        option_type=normalized_right,
        right=normalized_right,
        instrument_type="OPT",
        tradingsymbol=f"{normalized_symbol}26MAR23850{normalized_right}",
        instrument_id=f"{normalized_symbol}|2026-03-26|23850|{normalized_right}",
        selected_for_execution=selected_for_execution,
        slot_id=slot_id,
        allocation_reason=allocation_reason,
        capital_assigned=capital_assigned,
        source_flags=source_flags,
    )


def test_highly_correlated_long_candidates_are_not_all_selected_together(monkeypatch):
    monkeypatch.setattr(cfg, "PORTFOLIO_OPTIMIZER_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PORTFOLIO_OPTIMIZER_MAX_GROUP_EXPOSURE", 1, raising=False)
    monkeypatch.setattr(cfg, "CAPITAL_ALLOCATOR_ENABLE", False, raising=False)

    candidates = [
        _trade(
            trade_id="T-NIFTY-CE",
            symbol="NIFTY",
            right="CE",
            setup_family="breakout",
            opportunity_score=0.92,
            capital_assigned=12.0,
            slot_id="slot-1",
        ),
        _trade(
            trade_id="T-BANK-CE",
            symbol="BANKNIFTY",
            right="CE",
            setup_family="breakout",
            opportunity_score=0.90,
            capital_assigned=13.0,
            slot_id="slot-2",
        ),
        _trade(
            trade_id="T-NIFTY-PE",
            symbol="NIFTY",
            right="PE",
            setup_family="breakout",
            opportunity_score=0.81,
            capital_assigned=11.0,
            slot_id="slot-3",
        ),
    ]

    selected = select_top_opportunities(
        candidates,
        executable_top_n=3,
        advisory_top_n=0,
        current_portfolio_exposure=None,
    )

    assert [trade.trade_id for trade in selected["top_executable_opportunities"]] == [
        "T-NIFTY-CE",
        "T-NIFTY-PE",
    ]


def test_diversified_candidate_survives_better_than_concentrated_equivalent():
    candidates = [
        _trade(
            trade_id="T-STACK-SAME",
            symbol="BANKNIFTY",
            right="CE",
            setup_family="breakout",
            opportunity_score=0.88,
            capital_assigned=12.0,
            slot_id="slot-1",
        ),
        _trade(
            trade_id="T-DIVERSIFIED",
            symbol="NIFTY",
            right="PE",
            setup_family="breakout",
            opportunity_score=0.82,
            capital_assigned=10.0,
            slot_id="slot-2",
        ),
    ]
    current_exposure = {
        "trades": [
            {
                "symbol": "NIFTY",
                "right": "CE",
                "side": "BUY",
                "source_flags": {"candidate_origin": {"setup_family": "breakout"}},
            }
        ]
    }

    optimized = optimize_portfolio_selection(
        candidates,
        current_portfolio_exposure=current_exposure,
        max_group_exposure=1,
    )

    same_group = next(trade for trade in optimized if trade.trade_id == "T-STACK-SAME")
    diversified = next(trade for trade in optimized if trade.trade_id == "T-DIVERSIFIED")

    assert same_group.portfolio_optimization_selected is False
    assert same_group.portfolio_optimization_reason == "rejected_correlated_concentration"
    assert "same_theme_stacking" in str(same_group.portfolio_optimization_penalty_reason)
    assert diversified.portfolio_optimization_selected is True
    assert diversified.portfolio_optimization_reason == "selected_diversified"


def test_higher_score_still_matters_but_not_blindly():
    optimized = optimize_portfolio_selection(
        [
            _trade(
                trade_id="T-HIGH-CORRELATED",
                symbol="NIFTY",
                right="CE",
                setup_family="breakout",
                opportunity_score=0.91,
                capital_assigned=12.0,
                slot_id="slot-1",
            ),
            _trade(
                trade_id="T-LOWER-CORRELATED",
                symbol="BANKNIFTY",
                right="CE",
                setup_family="breakout",
                opportunity_score=0.87,
                capital_assigned=13.0,
                slot_id="slot-2",
            ),
            _trade(
                trade_id="T-DIVERSIFIED-MID",
                symbol="NIFTY",
                right="PE",
                setup_family="breakout",
                opportunity_score=0.79,
                capital_assigned=9.0,
                slot_id="slot-3",
            ),
        ],
        max_group_exposure=1,
    )

    highest = next(trade for trade in optimized if trade.trade_id == "T-HIGH-CORRELATED")
    lower_same_group = next(trade for trade in optimized if trade.trade_id == "T-LOWER-CORRELATED")
    diversified = next(trade for trade in optimized if trade.trade_id == "T-DIVERSIFIED-MID")

    assert highest.portfolio_optimization_selected is True
    assert highest.portfolio_optimization_reason in {"selected_diversified", "selected_best_effective_score"}
    assert lower_same_group.portfolio_optimization_selected is False
    assert lower_same_group.portfolio_optimization_reason == "rejected_correlated_concentration"
    assert diversified.portfolio_optimization_selected is True
