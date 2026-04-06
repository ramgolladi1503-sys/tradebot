from __future__ import annotations

from datetime import datetime

from config import config as cfg
from core.opportunity_engine import annotate_ranked_opportunities
from core.trade_schema import Trade


def _configure_density_test(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "OFFLINE_TRADE_DENSITY_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_AUDIT_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_TUNING_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_TRIAGE_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_AGGRESSIVENESS_GUARD_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "CAPITAL_ALLOCATOR_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "PORTFOLIO_OPTIMIZER_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "MIN_PRIORITY_SCORE_FOR_EXECUTABLE", 0.0, raising=False)
    monkeypatch.setattr(cfg, "MIN_EXECUTION_SCORE_FOR_EXECUTABLE", 0.0, raising=False)
    monkeypatch.setattr(cfg, "MIN_SELECTION_PROBABILITY", 0.0, raising=False)
    monkeypatch.setattr(cfg, "MIN_EXECUTABLE_GAP_OVER_NEXT_NON_EXECUTABLE", 0.0, raising=False)


def _trade(
    *,
    trade_id: str,
    confidence: float,
    symbol: str,
    strategy_family: str,
    direction_family: str = "bullish",
    session_mode: str = "MIDDAY",
    strategy_regime_mode: str = "TRENDING",
) -> Trade:
    normalized_symbol = str(symbol).strip().upper() or "NIFTY"
    entry = 121.5
    return Trade(
        trade_id=trade_id,
        timestamp=datetime(2026, 4, 6, 10, 0, 0),
        symbol=normalized_symbol,
        instrument="OPT",
        instrument_token=12345,
        strike=23850,
        expiry="2026-04-30",
        side="BUY",
        entry_price=entry,
        stop_loss=110.0,
        target=145.0,
        qty=1,
        capital_at_risk=11.5,
        expected_slippage=0.2,
        confidence=confidence,
        strategy="OPP_DIRECTIONAL",
        strategy_family=strategy_family,
        direction_family=direction_family,
        regime="TREND",
        session_mode=session_mode,
        strategy_regime_mode=strategy_regime_mode,
        market_mode="SIM",
        builder_confidence=confidence,
        permission_confidence=max(0.0, confidence - 0.02),
        gating_final_confidence=max(0.0, confidence - 0.04),
        confidence_raw_canonical=confidence,
        rank_score=confidence,
        timing_score=0.85,
        sizing_confluence_score=0.82,
        volume=9000,
        quote_age_sec=0.2,
        execution_allowed=True,
        tradable=True,
        execution_entry=entry,
        execution_entry_status="executable",
        execution_entry_source="ask",
        display_entry=entry,
        display_entry_status="displayable",
        display_entry_source="ask",
        entry_reason="unit_test",
        entry_price_source="ask",
        expected_entry=entry,
        expected_entry_source="ask",
        opt_bid=121.0,
        opt_ask=121.5,
        best_bid=121.0,
        best_ask=121.5,
        opt_ltp=121.2,
        current_ltp=121.2,
        option_type="CE",
        right="CE",
        instrument_type="OPT",
        tradingsymbol=f"{normalized_symbol}26APR23850CE",
        instrument_id=f"{normalized_symbol}|2026-04-30|23850|CE",
        setup_score=0.84,
        trigger_score=0.82,
        entry_quality_score=0.80,
        family_survival_score=0.81,
        signal_score=0.80,
        execution_score=0.79,
        priority_score=0.80,
        final_score=0.80,
        source_flags={
            "market_mode": "SIM",
            "session_mode": session_mode,
            "strategy_regime_mode": strategy_regime_mode,
            "strategy_family": strategy_family,
            "direction_family": direction_family,
        },
    )


def test_midday_density_policy_limits_executable_candidates(monkeypatch):
    _configure_density_test(monkeypatch)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_MIDDAY_MAX_RANKED_CANDIDATES", 3, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_MIDDAY_MAX_EXECUTABLE_CANDIDATES", 1, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_MIDDAY_MAX_PER_FAMILY", 3, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_TRENDING_EXECUTABLE_BONUS", 0, raising=False)

    ranked = annotate_ranked_opportunities(
        [
            _trade(trade_id="MIDDAY-1", confidence=0.82, symbol="NIFTY", strategy_family="continuation"),
            _trade(trade_id="MIDDAY-2", confidence=0.80, symbol="BANKNIFTY", strategy_family="breakout"),
            _trade(trade_id="MIDDAY-3", confidence=0.78, symbol="SENSEX", strategy_family="pullback"),
        ],
        scope="unit:density_midday",
        top_n=3,
    )

    assert sum(1 for trade in ranked if trade.selected_for_execution) == 1
    assert [trade.trade_id for trade in ranked if trade.selected_for_execution] == ["MIDDAY-1"]
    assert ranked[1].selection_reason == "trade_density_executable_cap"
    assert ranked[1].trade_density_limit_applied is True


def test_trending_density_policy_allows_more_aligned_candidates(monkeypatch):
    _configure_density_test(monkeypatch)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_MIDDAY_MAX_RANKED_CANDIDATES", 3, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_MIDDAY_MAX_EXECUTABLE_CANDIDATES", 1, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_MIDDAY_MAX_PER_FAMILY", 3, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_TRENDING_EXECUTABLE_BONUS", 1, raising=False)

    ranked = annotate_ranked_opportunities(
        [
            _trade(trade_id="TREND-1", confidence=0.82, symbol="NIFTY", strategy_family="continuation"),
            _trade(trade_id="TREND-2", confidence=0.80, symbol="BANKNIFTY", strategy_family="breakout"),
            _trade(trade_id="TREND-3", confidence=0.78, symbol="SENSEX", strategy_family="pullback"),
        ],
        scope="unit:density_trending",
        top_n=3,
    )

    assert sum(1 for trade in ranked if trade.selected_for_execution) == 2
    assert [trade.trade_id for trade in ranked if trade.selected_for_execution] == ["TREND-1", "TREND-2"]


def test_density_policy_caps_family_dominance(monkeypatch):
    _configure_density_test(monkeypatch)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_OPENING_MAX_RANKED_CANDIDATES", 3, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_OPENING_MAX_EXECUTABLE_CANDIDATES", 3, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_OPENING_MAX_PER_FAMILY", 1, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_TRENDING_EXECUTABLE_BONUS", 0, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_TRENDING_PER_FAMILY_BONUS", 0, raising=False)

    ranked = annotate_ranked_opportunities(
        [
            _trade(
                trade_id="FAMILY-1",
                confidence=0.83,
                symbol="NIFTY",
                strategy_family="breakout",
                session_mode="OPENING",
            ),
            _trade(
                trade_id="FAMILY-2",
                confidence=0.81,
                symbol="BANKNIFTY",
                strategy_family="breakout",
                session_mode="OPENING",
            ),
            _trade(
                trade_id="FAMILY-3",
                confidence=0.79,
                symbol="SENSEX",
                strategy_family="continuation",
                session_mode="OPENING",
            ),
        ],
        scope="unit:density_family_cap",
        top_n=3,
    )

    selected = [trade for trade in ranked if trade.selected_for_execution]
    assert [trade.trade_id for trade in selected] == ["FAMILY-1", "FAMILY-3"]
    assert ranked[1].selection_reason == "trade_density_family_cap"
    assert ranked[1].density_reject_reason == "trade_density_family_cap"


def test_density_policy_records_rejection_reason(monkeypatch):
    _configure_density_test(monkeypatch)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_MIDDAY_MAX_RANKED_CANDIDATES", 2, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_MIDDAY_MAX_EXECUTABLE_CANDIDATES", 3, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_MIDDAY_MAX_PER_FAMILY", 3, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_TRENDING_RANKED_BONUS", 0, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DENSITY_TRENDING_EXECUTABLE_BONUS", 0, raising=False)

    ranked = annotate_ranked_opportunities(
        [
            _trade(trade_id="REASON-1", confidence=0.83, symbol="NIFTY", strategy_family="continuation"),
            _trade(trade_id="REASON-2", confidence=0.81, symbol="BANKNIFTY", strategy_family="breakout"),
            _trade(trade_id="REASON-3", confidence=0.79, symbol="SENSEX", strategy_family="pullback"),
        ],
        scope="unit:density_reason",
        top_n=3,
    )

    assert ranked[2].trade_density_limit_applied is True
    assert ranked[2].density_policy_name == "MIDDAY:TRENDING"
    assert ranked[2].density_reject_reason == "trade_density_rank_cap"
    assert ranked[2].selection_reason == "trade_density_rank_cap"
    assert ranked[2].rejected_at_stage == "selector"
    assert ranked[2].rejection_reason_code == "trade_density_rank_cap"
