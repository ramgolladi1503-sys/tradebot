import pytest
import os
import json
from core.shadow_circuit_breaker_evaluator import ShadowCircuitBreakerEvaluator

TEST_LOG_PATH = "runtime/test_shadow_evaluator_v3_state.json"

@pytest.fixture(autouse=True)
def cleanup():
    if os.path.exists(TEST_LOG_PATH):
        os.remove(TEST_LOG_PATH)
    yield
    if os.path.exists(TEST_LOG_PATH):
        os.remove(TEST_LOG_PATH)

def test_scoped_event_identity_prevents_trade1014_collision():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-15"
    
    # NIFTY TRADE_1014_CE
    nifty_prop = evaluator.observe_trade_proposal(
        "TRADE_1014_CE", "NIFTY", date, "CE", "NIFTY 22850 CE", "2026-10-15T10:14:00"
    )
    nifty_exit = evaluator.observe_trade_exit(
        "TRADE_1014_CE", "NIFTY", date, 4.0, 0.3, "TRAILING_STOP_HIT", "2026-10-15T10:16:00"
    )
    
    # SENSEX TRADE_1014_CE (Same position_id, same date, different asset!)
    sensex_prop = evaluator.observe_trade_proposal(
        "TRADE_1014_CE", "SENSEX", date, "CE", "SENSEX 73600 CE", "2026-10-15T10:14:00"
    )
    sensex_exit = evaluator.observe_trade_exit(
        "TRADE_1014_CE", "SENSEX", date, 21.55, 13.1, "TRAILING_STOP_HIT", "2026-10-15T10:16:00"
    )
    
    # BOTH must be processed without duplicate collision!
    assert nifty_exit.get("status") != "DUPLICATE_EXIT_IGNORED"
    assert sensex_exit.get("status") != "DUPLICATE_EXIT_IGNORED"
    assert len(evaluator.shadow_ledger) == 2
    assert evaluator.shadow_ledger[0]["asset"] == "NIFTY"
    assert evaluator.shadow_ledger[1]["asset"] == "SENSEX"

def test_idempotent_proposal_and_exit_replays():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-14"
    
    # Initial proposal & exit
    evaluator.observe_trade_proposal("T1", "NIFTY", date, "PE", "P1", "2026-10-14T10:00:00")
    evaluator.observe_trade_exit("T1", "NIFTY", date, -10.0, -5.0, "STOP_LOSS_HIT", "2026-10-14T10:05:00")
    
    st1 = evaluator._get_state("NIFTY", date)
    assert st1["total_proposals"] == 1
    assert st1["total_completed_exits"] == 1
    assert st1["consecutive_losses"] == 1
    
    # Replay identical proposal & exit
    rep_prop = evaluator.observe_trade_proposal("T1", "NIFTY", date, "PE", "P1", "2026-10-14T10:00:00")
    rep_exit = evaluator.observe_trade_exit("T1", "NIFTY", date, -10.0, -5.0, "STOP_LOSS_HIT", "2026-10-14T10:05:00")
    
    # Verify idempotency: No counter increment
    assert rep_prop["status"] == "IDEMPOTENT_PROPOSAL_REPLAYED"
    assert rep_exit["status"] == "DUPLICATE_EXIT_IGNORED"
    assert st1["total_proposals"] == 1
    assert st1["total_completed_exits"] == 1
    assert st1["consecutive_losses"] == 1

def test_out_of_order_event_quarantine():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    
    # Valid event at 10:00
    p1 = evaluator.observe_trade_proposal("T1", "NIFTY", "2026-10-15", "CE", "C1", "2026-10-15T10:00:00")
    assert p1["shadow_decision"] == "PERMITTED"
    
    # Out of order proposal at 09:45
    p2 = evaluator.observe_trade_proposal("T2", "NIFTY", "2026-10-15", "CE", "C2", "2026-10-15T09:45:00+05:30")
    assert p2["shadow_decision"] == "QUARANTINED"
    assert "OUT_OF_ORDER" in p2["quarantine_reason"]
    assert len(evaluator.quarantine_ledger) == 1
    
    # Proposal for T1 was registered at 10:00. Out-of-order exit at 09:50 for T1
    e1 = evaluator.observe_trade_exit("T1", "NIFTY", "2026-10-15", 5.0, 2.0, "TARGET_HIT", "2026-10-15T09:50:00+05:30")
    assert e1["status"] == "QUARANTINED"
    assert "OUT_OF_ORDER" in e1["quarantine_reason"]
    assert len(evaluator.quarantine_ledger) == 2

def test_tri_state_lifecycle_and_unresolved_risk_pause():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-14"
    
    # Evaluable trade
    evaluator.observe_trade_proposal("T1", "NIFTY", date, "PE", "P1", "2026-10-14T10:00:00")
    e1 = evaluator.observe_trade_exit("T1", "NIFTY", date, 10.0, 5.0, "TARGET_HIT", "2026-10-14T10:05:00")
    assert e1["lifecycle_state"] == "COMPLETED_EVALUABLE"
    
    # Unresolved trade (Crash/missing exit)
    evaluator.observe_trade_proposal("T2_UNRES", "NIFTY", date, "PE", "P2", "2026-10-14T15:13:00")
    e2 = evaluator.observe_trade_exit("T2_UNRES", "NIFTY", date, None, None, "CRASH_FAIL_CLOSED", "2026-10-14T15:20:00")
    
    assert e2["lifecycle_state"] == "COMPLETED_UNRESOLVED_RISK"
    st = evaluator._get_state("NIFTY", date)
    assert st["unresolved_risk_positions"] == 1
    # Triggers conservative pause
    assert st["is_shadow_halted"] is True
    assert st["halt_reason"] == "CONSERVATIVE_PAUSE_ON_UNRESOLVED_RISK"

def test_challenger_processes_only_permitted_trades():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-14"
    
    # Loss 1
    evaluator.observe_trade_proposal("T1", "NIFTY", date, "PE", "P1", "2026-10-14T10:00:00")
    evaluator.observe_trade_exit("T1", "NIFTY", date, -5.0, -2.0, "STOP_LOSS_HIT", "2026-10-14T10:05:00")
    
    # Loss 2 -> Breaker trips
    evaluator.observe_trade_proposal("T2", "NIFTY", date, "PE", "P2", "2026-10-14T10:10:00")
    evaluator.observe_trade_exit("T2", "NIFTY", date, -10.0, -5.0, "STOP_LOSS_HIT", "2026-10-14T10:15:00")
    
    # T3 is proposed -> SHADOW VETOED
    p3 = evaluator.observe_trade_proposal("T3", "NIFTY", date, "PE", "P3", "2026-10-14T10:20:00")
    assert p3["shadow_decision"] == "VETOED"
    
    # When T3 exits in baseline as a loss, it should NOT increment the challenger's active streak because it was vetoed!
    e3 = evaluator.observe_trade_exit("T3", "NIFTY", date, -20.0, -10.0, "STOP_LOSS_HIT", "2026-10-14T10:25:00")
    assert e3["was_challenger_executed"] is False
    assert e3["consecutive_losses_after_exit"] == 2  # Remains 2, didn't increment to 3!
