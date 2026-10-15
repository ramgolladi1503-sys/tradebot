import pytest
import os
import json
from core.shadow_circuit_breaker_evaluator import ShadowCircuitBreakerEvaluator

STRESS_STATE_PATH = "runtime/test_stress_operational_state.json"

@pytest.fixture(autouse=True)
def cleanup():
    if os.path.exists(STRESS_STATE_PATH):
        os.remove(STRESS_STATE_PATH)
    yield
    if os.path.exists(STRESS_STATE_PATH):
        os.remove(STRESS_STATE_PATH)

def test_full_backfill_repeated_polling_and_restart_lifecycle():
    """
    Stress test verifying:
    1. Full initial backfill.
    2. Repeated polling with 0 duplicate increments.
    3. Service restart and state file reloading.
    4. New prospective event arrival.
    5. Clean cross-asset isolation.
    """
    # 1. Start Evaluator
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=STRESS_STATE_PATH)
    date = "2026-10-15"
    
    # Ingest event stream across NIFTY and SENSEX concurrently in strict chronological sequence
    time_windows = [
        ("10:00:00", "10:05:00"),
        ("10:06:00", "10:10:00"),
        ("10:11:00", "10:15:00")
    ]
    for i, (t_prop, t_exit) in enumerate(time_windows, 1):
        # NIFTY
        evaluator.observe_trade_proposal(f"N_{i}", "NIFTY", date, "CE", "C", f"2026-10-15T{t_prop}+05:30")
        evaluator.observe_trade_exit(f"N_{i}", "NIFTY", date, 5.0, 2.0, "TARGET_HIT", f"2026-10-15T{t_exit}+05:30")
        
        # SENSEX
        evaluator.observe_trade_proposal(f"S_{i}", "SENSEX", date, "CE", "S", f"2026-10-15T{t_prop}+05:30")
        evaluator.observe_trade_exit(f"S_{i}", "SENSEX", date, 15.0, 8.0, "TARGET_HIT", f"2026-10-15T{t_exit}+05:30")
        
    assert len(evaluator.shadow_ledger) == 6
    
    # 2. Repeated polling: Replay all identical events
    for i in range(1, 4):
        p_n = evaluator.observe_trade_proposal(f"N_{i}", "NIFTY", date, "CE", "C", f"2026-10-15T10:0{i}:00+05:30")
        e_n = evaluator.observe_trade_exit(f"N_{i}", "NIFTY", date, 5.0, 2.0, "TARGET_HIT", f"2026-10-15T10:0{i+4}:00+05:30")
        assert p_n["status"] == "IDEMPOTENT_PROPOSAL_REPLAYED"
        assert e_n["status"] == "DUPLICATE_EXIT_IGNORED"
        
    # Count must remain strictly 6
    assert len(evaluator.shadow_ledger) == 6
    
    # 3. Simulate Daemon Restart & Crash Recovery
    restarted = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=STRESS_STATE_PATH)
    assert len(restarted.shadow_ledger) == 6
    
    # 4. New Prospective Live Event Arrives (Trade 4)
    new_prop = restarted.observe_trade_proposal(
        "N_4", "NIFTY", date, "CE", "C", "2026-10-15T10:16:00+05:30", is_live_event=True
    )
    assert new_prop["shadow_decision"] == "PERMITTED"
    assert new_prop["provenance_mode"] == "PROSPECTIVE_OBSERVED"
    
    new_exit = restarted.observe_trade_exit(
        "N_4", "NIFTY", date, 10.0, 6.0, "TARGET_HIT", "2026-10-15T10:20:00+05:30", is_live_event=True
    )
    assert new_exit["provenance_mode"] == "PROSPECTIVE_OBSERVED"
    assert len(restarted.shadow_ledger) == 7
    
    # 5. Verify Unmatched Exit is quarantined without corrupting count
    ghost_exit = restarted.observe_trade_exit(
        "GHOST", "NIFTY", date, 10.0, 5.0, "TARGET_HIT", "2026-10-15T10:25:00+05:30"
    )
    assert ghost_exit["status"] == "UNMATCHED_EXIT_QUARANTINED"
    assert len(restarted.unmatched_exit_queue) == 1
    assert len(restarted.shadow_ledger) == 7
