import json

import pytest

from core.movement_contract import MovementContractError, StrategyContext
from core.movement_regime import (
    MovementRegimeClassifier,
    MovementRegimeResult,
    REGIME_LABELS,
    classify_movement_regime,
)


def test_classifies_trend_up_with_option_pressure():
    ctx = StrategyContext(
        symbol="NIFTY",
        spot_ltp=22600.0,
        vwap=22480.0,
        vwap_slope=0.07,
        day_high=22620.0,
        day_low=22390.0,
        ce_premium_change=12.0,
        pe_premium_change=-5.0,
        volume_z=1.1,
        range_width_pct=0.8,
        option_ltp_age_sec=0.4,
    )

    result = classify_movement_regime(ctx)

    assert result.primary_regime == "TREND_UP"
    assert result.scores["TREND_UP"] > result.scores["TREND_DOWN"]
    assert result.scores["TREND_UP"] >= 0.5
    assert set(REGIME_LABELS).issubset(result.scores.keys())
    assert json.loads(result.to_json())["primary_regime"] == "TREND_UP"


def test_classifies_trend_down_with_option_pressure():
    ctx = StrategyContext(
        symbol="BANKNIFTY",
        spot_ltp=48600.0,
        vwap=48950.0,
        vwap_slope=-0.08,
        day_high=49100.0,
        day_low=48580.0,
        ce_premium_change=-8.0,
        pe_premium_change=16.0,
        volume_z=1.3,
        range_width_pct=0.9,
        option_ltp_age_sec=0.5,
    )

    result = MovementRegimeClassifier().classify(ctx)

    assert result.primary_regime == "TREND_DOWN"
    assert result.scores["TREND_DOWN"] > result.scores["TREND_UP"]
    assert result.scores["TREND_DOWN"] >= 0.5


def test_scores_compression_near_vwap_with_low_range_and_low_atr_ratio():
    ctx = StrategyContext(
        symbol="SENSEX",
        spot_ltp=74010.0,
        vwap=74000.0,
        vwap_slope=0.0,
        day_high=74100.0,
        day_low=73920.0,
        atr_short=35.0,
        atr_long=100.0,
        range_width_pct=0.12,
        volume_z=0.45,
        option_ltp_age_sec=0.6,
    )

    result = classify_movement_regime(ctx)

    # Compression is a subtype of range, so primary may remain RANGE while the
    # COMPRESSION score activates compression-specific strategies.
    assert result.primary_regime in {"RANGE", "COMPRESSION"}
    assert result.scores["COMPRESSION"] >= 0.6
    assert result.scores["COMPRESSION"] > result.scores["TREND_UP"]
    assert result.scores["COMPRESSION"] > result.scores["TREND_DOWN"]
    assert result.evidence["atr_short_long_ratio"] == 0.35


def test_classifies_volatility_expansion_when_atr_ratio_and_volume_expand():
    ctx = StrategyContext(
        symbol="NIFTY",
        spot_ltp=22680.0,
        vwap=22500.0,
        vwap_slope=0.02,
        day_high=22690.0,
        day_low=22400.0,
        atr_short=140.0,
        atr_long=80.0,
        range_width_pct=0.95,
        volume_z=2.8,
        ce_premium_change=18.0,
        pe_premium_change=-4.0,
    )

    result = classify_movement_regime(ctx)

    assert result.primary_regime in {"VOLATILITY_EXPANSION", "TREND_UP"}
    assert result.scores["VOLATILITY_EXPANSION"] >= 0.4
    assert result.scores["VOLATILITY_EXPANSION"] > result.scores["COMPRESSION"]


def test_detects_trap_risk_when_breakout_lacks_option_confirmation():
    ctx = StrategyContext(
        symbol="NIFTY",
        spot_ltp=22650.0,
        vwap=22520.0,
        orb_high=22620.0,
        orb_low=22460.0,
        day_high=22655.0,
        day_low=22400.0,
        ce_premium_change=-1.0,
        pe_premium_change=1.0,
        volume_z=0.7,
        range_width_pct=0.6,
    )

    result = classify_movement_regime(ctx)

    assert result.scores["TRAP_RISK"] >= 0.5
    assert result.evidence["above_orb_high"] is True
    assert result.evidence["near_day_high"] is True


def test_detects_exhaustion_risk_when_far_from_vwap_and_premium_stalls():
    ctx = StrategyContext(
        symbol="BANKNIFTY",
        spot_ltp=49700.0,
        vwap=49000.0,
        day_high=49705.0,
        day_low=48800.0,
        ce_premium_change=0.0,
        pe_premium_change=0.5,
        volume_z=0.3,
        range_width_pct=1.0,
    )

    result = classify_movement_regime(ctx)

    assert result.scores["EXHAUSTION_RISK"] >= 0.3
    assert result.evidence["abs_vwap_distance_pct"] > 0.01


def test_expiry_context_score_is_visible_without_forcing_primary_when_other_signal_stronger():
    ctx = StrategyContext(
        symbol="NIFTY",
        spot_ltp=22600.0,
        vwap=22590.0,
        range_width_pct=0.2,
        atr_short=40.0,
        atr_long=100.0,
        volume_z=0.4,
        expiry_context=True,
    )

    result = classify_movement_regime(ctx)

    assert result.scores["EXPIRY_CONTEXT"] == 1.0
    assert result.primary_regime in {"EXPIRY_CONTEXT", "COMPRESSION"}


def test_missing_core_market_data_returns_safe_inconclusive():
    result = classify_movement_regime({"symbol": "NIFTY"})

    assert result.primary_regime == "INCONCLUSIVE"
    assert result.scores["INCONCLUSIVE"] >= 0.5
    assert "spot_ltp_missing" in result.warnings
    assert "vwap_missing" in result.warnings


def test_stale_and_fallback_context_adds_warnings_without_crash():
    ctx = StrategyContext(
        symbol="NIFTY",
        spot_ltp=22500.0,
        vwap=22500.0,
        fallback_used=True,
        quote_source="recovered_fallback",
        option_ltp_age_sec=9.5,
    )

    result = classify_movement_regime(ctx)

    assert "fallback_used_in_context" in result.warnings
    assert "option_ltp_stale_for_regime_context" in result.warnings
    assert result.evidence["fallback_used"] is True
    assert result.evidence["quote_source"] == "recovered_fallback"


def test_regime_result_rejects_invalid_primary_regime():
    with pytest.raises(MovementContractError, match="invalid_primary_regime"):
        MovementRegimeResult(schema_version=1, primary_regime="RANDOM", scores={})
