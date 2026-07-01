import pytest
from dataclasses import replace
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.opening_drive import generate_opening_drive_candidates
from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates


def dummy_context(symbol="TEST", fallback=False, spot_ltp=100.5, vwap=100.0) -> StrategyContext:
    return StrategyContext(
        symbol=symbol,
        minutes_since_open=15,
        minutes_to_close=360,
        spot_ltp=spot_ltp,
        vwap=vwap,
        open_price=99.0,
        day_high=101.0,
        day_low=98.5,
        option_ce_ltp=10.0,
        ce_premium_change=2.0,
        ce_spread_pct=0.01,
        ce_depth=1500.0,
        option_pe_ltp=9.0,
        pe_premium_change=1.0,
        pe_spread_pct=0.01,
        pe_depth=1200.0,
        option_ltp_age_sec=1.0,
        volume_z=1.5,
        quote_source="realtime",
        fallback_used=fallback,
        metadata={"vwap_reclaim_up_confirmed": True}
    )


def dummy_regime() -> MovementRegimeResult:
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP",
        scores={
            "TREND_UP": 0.8,
            "TREND_DOWN": 0.1,
            "VOLATILITY_EXPANSION": 0.5,
            "COMPRESSION": 0.2,
            "TRAP_RISK": 0.1,
            "CHOP": 0.1,
        },
    )


def test_opening_drive_generator_lineage():
    ctx = dummy_context()
    regime = dummy_regime()
    candidates = generate_opening_drive_candidates(ctx, regime)
    
    assert len(candidates) > 0
    c = candidates[0]
    
    assert "strategy_version" in c.lineage
    assert c.lineage["strategy_version"] == "v1"
    if c.strategy_id.startswith("vwap"): assert c.strategy_id == "vwap_reclaim_rejection_v1"
    
    assert "params_used" in c.lineage
    assert isinstance(c.lineage["params_used"], dict)
    assert "params_hash" in c.lineage
    # It seems params_hash might be None if the hash is not generated?
    assert c.lineage["params_hash"] is not None, f"Hash was None. Profile config issue? lineage: {c.lineage}"
    assert "promotion_state" in c.lineage
    assert c.lineage["promotion_state"] == "ADVISORY_ONLY"


def test_vwap_reclaim_generator_lineage():
    ctx = dummy_context(spot_ltp=100.1, vwap=100.0)
    regime = dummy_regime()
    candidates = generate_vwap_reclaim_rejection_candidates(ctx, regime)
    
    assert len(candidates) > 0
    c = candidates[0]
    
    assert "strategy_version" in c.lineage
    assert c.lineage["strategy_version"] == "v1"
    if c.strategy_id.startswith("vwap"): assert c.strategy_id == "vwap_reclaim_rejection_v1"
    
    assert "params_used" in c.lineage
    assert isinstance(c.lineage["params_used"], dict)
    assert "params_hash" in c.lineage
    assert c.lineage["params_hash"] is not None
    assert "promotion_state" in c.lineage
    assert c.lineage["promotion_state"] == "ADVISORY_ONLY"
