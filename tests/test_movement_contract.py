import json

import pytest

from core.movement_contract import (
    HARD_EXECUTION_BLOCKERS,
    MovementContractError,
    StrategyCandidate,
    StrategyContext,
    candidate_from_dict,
    context_from_dict,
    has_hard_blocker,
)


def _candidate(**overrides):
    payload = {
        "schema_version": 1,
        "strategy_id": "compression_breakout_v1",
        "movement_type": "COMPRESSION_BREAKOUT",
        "symbol": "nifty",
        "direction": "BUY_CALL",
        "status": "VALIDATED_CANDIDATE",
        "raw_score": 0.72,
        "confidence_score": 0.70,
        "price_structure_score": 0.74,
        "option_confirmation_score": 0.68,
        "liquidity_score": 0.81,
        "freshness_score": 1.0,
        "volatility_score": 0.66,
        "regime_alignment_score": 0.77,
        "timing_score": 0.62,
        "trap_risk_score": 0.14,
        "confluence_score": 0.71,
        "entry_trigger": "range_high_break_with_ce_premium_expansion",
        "invalid_if": "price_returns_inside_range_or_option_ltp_stale",
        "rank_reason": "compression breakout with fresh option confirmation",
        "blockers": (),
        "warnings": ("watch_near_resistance",),
        "confluence_tags": ("range_compression", "ce_premium_expansion"),
        "suppression_tags": (),
        "source_signals": ("compression_breakout", "option_pressure"),
        "regime_scores": {"COMPRESSION": 0.82, "VOLATILITY_EXPANSION": 0.61},
        "evidence": {"range_width_pct": 0.18, "ce_spread_pct": 0.9},
        "lineage": {"run_id": "unit-test"},
        "generated_epoch": 1772202300.0,
    }
    payload.update(overrides)
    return StrategyCandidate(**payload)


def test_strategy_candidate_normalizes_and_serializes_elite_fields():
    candidate = _candidate()

    assert candidate.symbol == "NIFTY"
    assert candidate.strategy_id == "compression_breakout_v1"
    assert candidate.movement_type == "COMPRESSION_BREAKOUT"
    assert candidate.executable_eligible is True
    assert candidate.has_hard_blocker is False
    assert candidate.regime_scores["COMPRESSION"] == 0.82
    assert "ce_premium_expansion" in candidate.confluence_tags

    payload = candidate.to_dict()
    assert payload["blockers"] == []
    assert payload["warnings"] == ["watch_near_resistance"]
    assert json.loads(candidate.to_json())["symbol"] == "NIFTY"

    restored = candidate_from_dict(payload)
    assert restored == candidate


def test_ranked_opportunity_cannot_have_hard_blocker():
    with pytest.raises(MovementContractError, match="ranked_opportunity_has_hard_blocker"):
        _candidate(status="RANKED_OPPORTUNITY", blockers=("STALE_OPTION_LTP",))


def test_validated_candidate_with_hard_blocker_is_not_executable_eligible():
    candidate = _candidate(blockers=("FALLBACK_QUOTE_ONLY",), freshness_score=0.1)

    assert candidate.has_hard_blocker is True
    assert candidate.executable_eligible is False
    assert has_hard_blocker(candidate.blockers) is True
    assert "FALLBACK_QUOTE_ONLY" in HARD_EXECUTION_BLOCKERS


def test_no_trade_status_requires_no_trade_direction():
    with pytest.raises(MovementContractError, match="no_trade_status_requires_no_trade_direction"):
        _candidate(status="NO_TRADE", direction="BUY_CALL")

    no_trade = _candidate(
        movement_type="NO_TRADE_CHOP",
        status="NO_TRADE",
        direction="NO_TRADE",
        raw_score=0.0,
        confidence_score=0.0,
        price_structure_score=0.0,
        option_confirmation_score=0.0,
        liquidity_score=0.0,
        freshness_score=0.0,
        volatility_score=0.0,
        regime_alignment_score=0.0,
        timing_score=0.0,
        trap_risk_score=1.0,
        confluence_score=0.0,
        blockers=("NO_TRADE_CHOP",),
        rank_reason="chop detector suppressed weak candidates",
    )
    assert no_trade.status == "NO_TRADE"
    assert no_trade.direction == "NO_TRADE"
    assert no_trade.executable_eligible is False


def test_invalid_scores_and_enum_values_are_rejected():
    with pytest.raises(MovementContractError, match="score_out_of_range:raw_score"):
        _candidate(raw_score=1.2)

    with pytest.raises(MovementContractError, match="invalid_direction"):
        _candidate(direction="BUY_STOCK")

    with pytest.raises(MovementContractError, match="invalid_movement_type"):
        _candidate(movement_type="RANDOM_INDICATOR_WRAPPER")


def test_strategy_context_supports_elite_market_and_option_evidence():
    context = StrategyContext(
        symbol="banknifty",
        ts_epoch=1772202300,
        spot_ltp=49000.0,
        vwap=48920.0,
        day_high=49100.0,
        day_low=48800.0,
        orb_high=49080.0,
        orb_low=48850.0,
        atr=125.0,
        range_width_pct=0.18,
        volume_z=1.4,
        regime_hint="COMPRESSION",
        regime_scores={"COMPRESSION": 0.8, "VOLATILITY_EXPANSION": 0.55},
        option_ce_ltp=220.0,
        option_pe_ltp=180.0,
        ce_premium_change=12.0,
        pe_premium_change=-4.0,
        ce_spread_pct=0.7,
        pe_spread_pct=1.1,
        ce_depth=1200.0,
        pe_depth=900.0,
        option_ltp_age_sec=0.4,
        quote_source="live_option_tick",
        fallback_used=False,
        minutes_since_open=42,
        minutes_to_close=260,
        metadata={"source": "unit-test"},
    )

    assert context.symbol == "BANKNIFTY"
    assert context.regime_scores["COMPRESSION"] == 0.8
    assert context.metadata["source"] == "unit-test"
    assert json.loads(context.to_json())["symbol"] == "BANKNIFTY"

    restored = context_from_dict(context.to_dict())
    assert restored == context


def test_strategy_context_rejects_invalid_regime_scores():
    with pytest.raises(MovementContractError, match="score_out_of_range:regime_scores.COMPRESSION"):
        StrategyContext(symbol="NIFTY", regime_scores={"COMPRESSION": 1.5})
