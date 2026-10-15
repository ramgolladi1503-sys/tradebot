import pytest
import os
import json
from core.shadow_circuit_breaker_evaluator import ShadowCircuitBreakerEvaluator

def test_shadow_evaluator_observes_proposals_without_side_effects():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2)
    
    # Observe proposal
    prop = evaluator.observe_trade_proposal("TRADE_01", "NIFTY", "2026-10-15", "CE", "NIFTY 22850 CE")
    assert prop["shadow_decision"] == "PERMITTED"
    assert prop["veto_reason"] is None
    assert prop["active_consecutive_losses"] == 0

def test_shadow_evaluator_unresolved_exit_treated_as_risk():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2)
    date = "2026-10-14"
    
    # Loss 1
    r1 = evaluator.observe_trade_exit("T1", "NIFTY", date, -5.0, -2.0, "STOP_LOSS_HIT")
    assert r1["consecutive_losses_after_exit"] == 1
    assert r1["is_shadow_halted_now"] is False
    
    # Unresolved exit (crashed/missing)
    exit_rec = evaluator.observe_trade_exit("T2_CRASH", "NIFTY", date, None, None, "CRASH_RECOVERY")
    assert exit_rec["eval_status"] == "UNRESOLVED_EXIT_PRESERVED_AS_RISK"
    assert exit_rec["consecutive_losses_after_exit"] == 2
    assert exit_rec["is_shadow_halted_now"] is True
    
    # Next trade must be shadow-vetoed
    prop = evaluator.observe_trade_proposal("T3", "NIFTY", date, "PE", "NIFTY 22650 PE")
    assert prop["shadow_decision"] == "VETOED"
    assert prop["veto_reason"] == "SHADOW_CHOP_CIRCUIT_BREAKER_L2"

def test_shadow_evaluator_quote_coverage_tracking():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2)
    date = "2026-10-15"
    
    # Entry depth only
    rec1 = evaluator.observe_trade_exit(
        "T1", "NIFTY", date, 10.0, 5.0, "TARGET_HIT",
        opt_entry_bid=150.0, opt_entry_ask=150.4, opt_exit_bid=None, opt_exit_ask=None
    )
    assert rec1["depth_coverage"] == "ENTRY_DEPTH_ONLY_EXIT_DEPTH_MISSING"
    
    # Full depth
    rec2 = evaluator.observe_trade_exit(
        "T2", "NIFTY", date, 10.0, 5.0, "TARGET_HIT",
        opt_entry_bid=150.0, opt_entry_ask=150.4, opt_exit_bid=155.0, opt_exit_ask=155.4
    )
    assert rec2["depth_coverage"] == "FULL_BID_ASK_VERIFIED"
