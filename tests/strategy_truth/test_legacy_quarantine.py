import pytest
from core._engine_phase2_adapter_base import build_candidates_phase2

def test_phase2_hard_blocks_fallback():
    raw_candidates = [{
        "trade_id": "test_fallback_1",
        "symbol": "BANKNIFTY",
        "strategy_id": "HTF_RANGE_EXPANSION",
        "mode": "live",
        "confidence": 0.9,
        "fallback_used": True,
        "candidate_status": "near_executable",
        "execution_status": "executable",
        "execution_ok": True
    }, {
        "trade_id": "test_advisory_1",
        "symbol": "FINNIFTY",
        "strategy_id": "HTF_RANGE_EXPANSION",
        "mode": "live",
        "confidence": 0.9,
        "advisory_only": True,
        "candidate_status": "near_executable",
        "execution_status": "executable",
        "execution_ok": True
    }, {
        "trade_id": "test_valid_htf",
        "symbol": "NIFTY",
        "strategy_id": "HTF_RANGE_EXPANSION",
        "mode": "live",
        "confidence": 0.9,
        "candidate_status": "near_executable",
        "execution_status": "executable",
        "execution_ok": True,
        "execution_entry_source": "last",
        "display_entry_source": "last",
        "hard_execution": False,
        "hard_spread": False,
        "hard_liquidity": False
    }]
    
    ranked = build_candidates_phase2(raw_candidates)
    
    # Prove that fallback and advisory candidates are marked not executable by Phase 2
    # They might be completely dropped or returned with execution_ok=False depending on global config
    for c in ranked:
        if c["trade_id"] in ("test_fallback_1", "test_advisory_1"):
            assert c["execution_ok"] is False
            assert c["candidate_status"] == "advisory_only"
    
    # Prove HTF_RANGE_EXPANSION remains unaffected if valid
    valid_htf = next(c for c in ranked if c["trade_id"] == "test_valid_htf")
    assert valid_htf["candidate_status"] == "near_executable"


