import pytest
import os
import json
from core.shadow_circuit_breaker_evaluator import ShadowCircuitBreakerEvaluator

TEST_LOG_PATH = "runtime/test_shadow_evaluator_state.json"

@pytest.fixture(autouse=True)
def cleanup():
    if os.path.exists(TEST_LOG_PATH):
        os.remove(TEST_LOG_PATH)
    yield
    if os.path.exists(TEST_LOG_PATH):
        os.remove(TEST_LOG_PATH)

def test_shadow_evaluator_atomic_persistence_and_recovery():
    # 1. Initialize and run some events
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-14"
    
    # Trade 1 proposal & exit (Loss 1)
    evaluator.observe_trade_proposal("T1", "NIFTY", date, "PE", "NIFTY 22750 PE", "2026-10-14T10:11:00")
    evaluator.observe_trade_exit("T1", "NIFTY", date, -13.4, -0.85, "STOP_LOSS_HIT", "2026-10-14T10:20:00")
    
    # Trade 2 proposal & exit (Loss 2 -> Trips breaker)
    evaluator.observe_trade_proposal("T2", "NIFTY", date, "PE", "NIFTY 22700 PE", "2026-10-14T11:35:00")
    evaluator.observe_trade_exit("T2", "NIFTY", date, -56.7, -34.6, "OPTION_NATIVE_STOP_LOSS_HIT", "2026-10-14T11:57:49")
    
    assert os.path.exists(TEST_LOG_PATH), "Log file must exist on disk"
    
    # 2. Simulate process crash & restart: Create a brand new instance pointing to same file
    recovered = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    
    # Verify state recovered
    st = recovered._get_state("NIFTY", date)
    assert st["consecutive_losses"] == 2
    assert st["is_shadow_halted"] is True
    assert st["halt_reason"] == "CONSECUTIVE_LOSS_LIMIT_2_EXCEEDED"
    
    # Trade 3 proposal must be shadow-vetoed in recovered instance
    prop = recovered.observe_trade_proposal("T3", "NIFTY", date, "PE", "NIFTY 22650 PE", "2026-10-14T13:39:00")
    assert prop["shadow_decision"] == "VETOED"
    assert prop["veto_reason"] == "SHADOW_CHOP_CIRCUIT_BREAKER_L2"

def test_shadow_evaluator_duplicate_exit_prevention():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-14"
    
    # First exit
    r1 = evaluator.observe_trade_exit("T1", "NIFTY", date, -5.0, -2.0, "STOP_LOSS_HIT", "2026-10-14T10:00:00")
    assert r1["consecutive_losses_after_exit"] == 1
    
    # Duplicate exit with same position_id
    r2 = evaluator.observe_trade_exit("T1", "NIFTY", date, -5.0, -2.0, "STOP_LOSS_HIT", "2026-10-14T10:00:00")
    assert r2["status"] == "DUPLICATE_EXIT_IGNORED"
    
    # Counter must NOT have incremented again
    st = evaluator._get_state("NIFTY", date)
    assert st["consecutive_losses"] == 1

def test_shadow_evaluator_out_of_order_causality_detection():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    
    # T1 at 10:00
    p1 = evaluator.observe_trade_proposal("T1", "NIFTY", "2026-10-15", "CE", "C1", "2026-10-15T10:00:00")
    assert p1["shadow_decision"] == "PERMITTED"
    
    # T2 with earlier timestamp (Out of order) -> Quarantined
    p2 = evaluator.observe_trade_proposal("T2", "NIFTY", "2026-10-15", "CE", "C2", "2026-10-15T09:45:00")
    assert p2["shadow_decision"] == "QUARANTINED"
    assert p2["quarantine_reason"] == "OUT_OF_ORDER_TIMESTAMP"

def test_shadow_evaluator_asset_isolation_under_stress():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-15"
    
    # Trip NIFTY
    evaluator.observe_trade_exit("N1", "NIFTY", date, -10.0, -5.0, "STOP_LOSS_HIT", "2026-10-15T10:00:00")
    evaluator.observe_trade_exit("N2", "NIFTY", date, -10.0, -5.0, "STOP_LOSS_HIT", "2026-10-15T10:05:00")
    
    nifty_prop = evaluator.observe_trade_proposal("N3", "NIFTY", date, "CE", "C1", "2026-10-15T10:10:00")
    assert nifty_prop["shadow_decision"] == "VETOED"
    
    # SENSEX on same date must be PERMITTED (zero bleed)
    sensex_prop = evaluator.observe_trade_proposal("S1", "SENSEX", date, "CE", "S1", "2026-10-15T10:11:00")
    assert sensex_prop["shadow_decision"] == "PERMITTED"
    assert sensex_prop["active_consecutive_losses"] == 0
