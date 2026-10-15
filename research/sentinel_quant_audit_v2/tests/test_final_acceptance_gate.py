import pytest
import os
import json
from core.shadow_circuit_breaker_evaluator import ShadowCircuitBreakerEvaluator

TEST_LOG_PATH = "runtime/test_final_gate_state.json"

@pytest.fixture(autouse=True)
def cleanup():
    if os.path.exists(TEST_LOG_PATH):
        os.remove(TEST_LOG_PATH)
    yield
    if os.path.exists(TEST_LOG_PATH):
        os.remove(TEST_LOG_PATH)

def test_quarantined_exit_reconciles_cleanly_and_idempotently():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-15"
    
    # 1. Register valid proposal at 10:00
    evaluator.observe_trade_proposal("T_RECON", "NIFTY", date, "CE", "C1", "2026-10-15T10:00:00+05:30")
    
    # 2. Exit arrives with an invalid out-of-order timestamp (09:40) -> Quarantined
    exit_bad = evaluator.observe_trade_exit(
        "T_RECON", "NIFTY", date, 10.0, 5.0, "TARGET_HIT", "2026-10-15T09:40:00+05:30"
    )
    assert exit_bad["status"] == "QUARANTINED"
    assert len(evaluator.quarantine_ledger) == 1
    assert len(evaluator.shadow_ledger) == 0
    
    # 3. Reconcile with corrected timestamp (10:15)
    recon_res = evaluator.reconcile_quarantined_exit(
        "T_RECON", "NIFTY", date, "2026-10-15T10:15:00+05:30", audit_operator="QA_AUDITOR"
    )
    assert recon_res["status"] == "RECONCILED"
    assert len(evaluator.shadow_ledger) == 1
    assert len(evaluator.reconciliation_audit_trail) == 1
    assert recon_res["audit_entry"]["audit_operator"] == "QA_AUDITOR"
    
    # 4. Attempt duplicate reconciliation: must fail closed
    dup_recon = evaluator.reconcile_quarantined_exit(
        "T_RECON", "NIFTY", date, "2026-10-15T10:15:00+05:30"
    )
    assert dup_recon["status"] == "ERROR_NOT_IN_QUARANTINE"
    assert len(evaluator.shadow_ledger) == 1

def test_trade1513_historical_unresolved_risk_reconciled():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-14"
    
    # Proposal for TRADE_1513_PE at 15:13
    evaluator.observe_trade_proposal("TRADE_1513_PE", "NIFTY", date, "PE", "NIFTY 22650 PE", "2026-10-14T15:13:00+05:30")
    
    # Exit has missing timestamp / crash recovery
    exit_res = evaluator.observe_trade_exit(
        "TRADE_1513_PE", "NIFTY", date, None, None, "CRASH_RECOVERY_FAIL_CLOSED", ""
    )
    
    # Must be classified as HISTORICAL_UNRESOLVED_RISK and NOT remain in-flight!
    assert exit_res["lifecycle_state"] == "HISTORICAL_UNRESOLVED_RISK"
    assert exit_res["is_shadow_halted_now"] is True
    scoped_key = evaluator._make_scoped_key("NIFTY", date, "TRADE_1513_PE")
    assert scoped_key not in evaluator.in_flight_positions
    assert len(evaluator.shadow_ledger) == 1

def test_corrupt_persistence_fails_closed():
    # Write garbage to snapshot
    with open(TEST_LOG_PATH, "w") as f:
        f.write("{corrupt_json: true, invalid")
        
    with pytest.raises(RuntimeError) as exc_info:
        ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    assert "Corrupt or unreadable snapshot" in str(exc_info.value)

def test_provenance_distinguishes_prospective_vs_retrospective():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-15"
    
    # Historical backfill trade
    p_hist = evaluator.observe_trade_proposal("T_HIST", "NIFTY", date, "CE", "C", "2026-10-15T10:00:00+05:30", is_live_event=False)
    e_hist = evaluator.observe_trade_exit("T_HIST", "NIFTY", date, 5.0, 2.0, "TARGET_HIT", "2026-10-15T10:05:00+05:30", is_live_event=False)
    assert p_hist["provenance_mode"] == "RETROSPECTIVE_BACKFILL"
    assert e_hist["provenance_mode"] == "RETROSPECTIVE_BACKFILL"
    
    # Genuine prospective live trade
    p_live = evaluator.observe_trade_proposal("T_LIVE", "NIFTY", date, "CE", "C", "2026-10-15T10:10:00+05:30", is_live_event=True)
    e_live = evaluator.observe_trade_exit("T_LIVE", "NIFTY", date, 5.0, 2.0, "TARGET_HIT", "2026-10-15T10:15:00+05:30", is_live_event=True)
    assert p_live["provenance_mode"] == "PROSPECTIVE_OBSERVED"
    assert e_live["provenance_mode"] == "PROSPECTIVE_OBSERVED"

def test_persistence_failure_blocks_evaluator_into_degraded_state(monkeypatch):
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-15"
    
    # Force os.replace to fail, simulating disk full or permission error
    def mock_replace(src, dst):
        raise IOError("Disk quota exceeded on volume")
    monkeypatch.setattr(os, "replace", mock_replace)
    
    with pytest.raises(IOError):
        evaluator.observe_trade_proposal("T_FAIL", "NIFTY", date, "CE", "C", "2026-10-15T10:00:00+05:30")
        
    assert evaluator.operational_health == "DEGRADED_PERSISTENCE_FAILED"
    assert "Disk quota exceeded" in str(evaluator.persistence_error)
    
    # Subsequent calls must be blocked
    blocked = evaluator.observe_trade_proposal("T_NEXT", "NIFTY", date, "CE", "C", "2026-10-15T10:05:00+05:30")
    assert blocked["shadow_decision"] == "DEGRADED_BLOCKED"

def test_late_quarantine_reconciliation_after_subsequent_events():
    """
    Tests that an exit quarantined early can be reconciled much later after subsequent valid
    trades have been processed, without retroactively invalidating causal ordering.
    """
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-15"
    
    # Trade 1 registered at 10:00
    evaluator.observe_trade_proposal("T1", "NIFTY", date, "CE", "C", "2026-10-15T10:00:00+05:30")
    # Exit 1 arrives out of order (09:50) -> Quarantined
    evaluator.observe_trade_exit("T1", "NIFTY", date, 5.0, 2.0, "TARGET_HIT", "2026-10-15T09:50:00+05:30")
    assert "NIFTY::2026-10-15::T1" in evaluator.quarantined_exit_keys
    
    # Trade 2 executes normally at 10:10 -> 10:20
    evaluator.observe_trade_proposal("T2", "NIFTY", date, "CE", "C", "2026-10-15T10:10:00+05:30")
    evaluator.observe_trade_exit("T2", "NIFTY", date, -5.0, -2.0, "SL_HIT", "2026-10-15T10:20:00+05:30")
    
    # Now reconcile T1 with late corrected timestamp (10:05 - before T2)
    # The evaluator accepts the corrected timestamp and creates audit entry
    recon = evaluator.reconcile_quarantined_exit("T1", "NIFTY", date, "2026-10-15T10:05:00+05:30")
    assert recon["status"] == "RECONCILED"
    assert "NIFTY::2026-10-15::T1" not in evaluator.quarantined_exit_keys
    assert len(evaluator.reconciliation_audit_trail) == 1
    
    # Verify crash recovery of reconciled state
    evaluator_reloaded = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    assert len(evaluator_reloaded.shadow_ledger) == 2
    assert len(evaluator_reloaded.reconciliation_audit_trail) == 1

def test_missing_state_file_fails_closed_when_required():
    """Accidental state loss must not silently reset circuit-breaker decisions."""
    missing_path = "runtime/non_existent_state_file.json"
    if os.path.exists(missing_path):
        os.remove(missing_path)
        
    with pytest.raises(RuntimeError) as exc_info:
        ShadowCircuitBreakerEvaluator(
            max_consecutive_losses=2,
            log_path=missing_path,
            require_existing_state=True
        )
    assert "CRITICAL_STATE_LOSS_PREVENTION" in str(exc_info.value)

def test_stale_open_payload_clock_skew_quarantined():
    """A stale open WAL payload must not be promoted to genuine prospective evidence."""
    evaluator = ShadowCircuitBreakerEvaluator(
        max_consecutive_losses=2,
        log_path=TEST_LOG_PATH,
        max_clock_skew_sec=60.0
    )
    date = "2026-10-15"
    # Old timestamp (e.g., 2 hours in the past) marked as live event
    stale_ts = "2026-10-15T08:00:00+05:30"
    prop = evaluator.observe_trade_proposal(
        "T_STALE", "NIFTY", date, "CE", "C", stale_ts, is_live_event=True
    )
    assert prop["shadow_decision"] == "QUARANTINED"
    assert "PROSPECTIVE_CLOCK_SKEW_EXCEEDED" in prop["quarantine_reason"]
    assert len(evaluator.quarantine_ledger) == 1
    assert len(evaluator.in_flight_positions) == 0


