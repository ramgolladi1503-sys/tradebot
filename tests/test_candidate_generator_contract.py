import pytest
import os
import json
import time
from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from scripts.audit_candidate_generator_contract import run_audit

def mock_good_generator(ctx: StrategyContext, regime: MovementRegimeResult):
    return [
        StrategyCandidate(
            schema_version=1,
            strategy_id="GOOD_STRAT",
            movement_type="TREND_PULLBACK",
            symbol="NIFTY",
            direction="BUY_CALL",
            status="VALIDATED_CANDIDATE",
            generated_epoch=time.time()
        )
    ]

def mock_bad_generator(ctx: StrategyContext, regime: MovementRegimeResult):
    return [
        {"not_a_candidate": True}
    ]

def mock_fallback_executable(ctx: StrategyContext, regime: MovementRegimeResult):
    return [
        StrategyCandidate(
            schema_version=1,
            strategy_id="BAD_STRAT",
            movement_type="TREND_PULLBACK",
            symbol="NIFTY",
            direction="BUY_CALL",
            status="NO_TRADE",
            generated_epoch=time.time()
        )
    ]

def test_audit_good_generator(tmp_path):
    mod_path = tmp_path / "good.py"
    mod_path.write_text("""
import time
from core.movement_contract import StrategyCandidate

def good_gen(ctx, regime):
    return [StrategyCandidate(
        schema_version=1,
        strategy_id="GOOD",
        movement_type="TREND_PULLBACK",
        symbol="N",
        direction="BUY_CALL",
        status="VALIDATED_CANDIDATE",
        raw_score=0.5,
        confidence_score=0.5,
        price_structure_score=0.5,
        option_confirmation_score=0.5,
        liquidity_score=0.5,
        freshness_score=0.5,
        volatility_score=0.5,
        regime_alignment_score=0.5,
        timing_score=0.5,
        trap_risk_score=0.5,
        confluence_score=0.5,
        generated_epoch=time.time()
    )]
""")
    res = run_audit("GOOD", str(mod_path), "good_gen")
    assert res["contract_passed"] is True
    assert not res["errors"]

def test_audit_bad_generator_missing_fields(tmp_path):
    mod_path = tmp_path / "bad.py"
    mod_path.write_text("""
from core.movement_contract import StrategyCandidate
def bad_gen(ctx, regime):
    cand = StrategyCandidate(
        schema_version=1,
        strategy_id="",
        movement_type="TREND_PULLBACK",
        symbol="N",
        direction="BUY_CALL",
        status="VALIDATED_CANDIDATE",
        raw_score=0.5,
        confidence_score=0.5,
        price_structure_score=0.5,
        option_confirmation_score=0.5,
        liquidity_score=0.5,
        freshness_score=0.5,
        volatility_score=0.5,
        regime_alignment_score=0.5,
        timing_score=0.5,
        trap_risk_score=0.5,
        confluence_score=0.5,
        generated_epoch=None
    )
    object.__setattr__(cand, 'generated_epoch', None)
    return [cand]
""")
    res = run_audit("BAD", str(mod_path), "bad_gen")
    assert res["contract_passed"] is False
    assert any("missing_required_field" in e or "Missing strategy_id" in e for e in res["errors"])
    assert any("missing_required_field" in e or "Missing generated_epoch" in e for e in res["errors"])

def test_audit_fallback_not_executable(tmp_path):
    mod_path = tmp_path / "fallback.py"
    mod_path.write_text("""
import time
from core.movement_contract import StrategyCandidate
def fallback_gen(ctx, regime):
    return [StrategyCandidate(
        schema_version=1,
        strategy_id="FB",
        movement_type="TREND_PULLBACK",
        symbol="N",
        direction="NO_TRADE",
        status="NO_TRADE",
        blockers=(),
        generated_epoch=time.time()
    )]
""")
    res = run_audit("FB", str(mod_path), "fallback_gen")
    assert res["contract_passed"] is False

def test_audit_advisory_not_executable(tmp_path):
    mod_path = tmp_path / "advisory.py"
    mod_path.write_text("""
import time
from core.movement_contract import StrategyCandidate
def adv_gen(ctx, regime):
    cand = StrategyCandidate(
        schema_version=1,
        strategy_id="ADV",
        movement_type="TREND_PULLBACK",
        symbol="N",
        direction="BUY_CALL",
        status="ADVISORY",
        raw_score=0.5,
        confidence_score=0.5,
        price_structure_score=0.5,
        option_confirmation_score=0.5,
        liquidity_score=0.5,
        freshness_score=0.5,
        volatility_score=0.5,
        regime_alignment_score=0.5,
        timing_score=0.5,
        trap_risk_score=0.5,
        confluence_score=0.5,
        generated_epoch=time.time()
    )
    return [cand]
""")
    res = run_audit("ADV", str(mod_path), "adv_gen")
    assert res["contract_passed"] is False
