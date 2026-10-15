"""
Sentinel Continuous Prospective Read-Only Shadow Observer Service (v5 Production Daemon).

Runs as an independently restartable daemon with signal-handling for graceful shutdown,
continuous polling against live APM WAL streams, strict provenance tagging,
and real-time operational health reporting.

Integrity Invariants:
- 100% Read-Only: Never writes to Sentinel WALs, never mutates APM memory, never calls broker APIs.
- Phase 1: Ingests completed historical WAL records labeled RETROSPECTIVE_BACKFILL.
- Phase 2: Continuously polls active WAL sources, tagging new events PROSPECTIVE_OBSERVED.
- Controlled stop mechanism: handles SIGINT / SIGTERM cleanly and flushes snapshot.
- Dedicated runtime persistence: isolated in runtime/shadow_evaluator_live_state.json (git-ignored).
"""

import sys
import os
import time
import json
import signal
import logging
from typing import Dict, Any

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.shadow_circuit_breaker_evaluator import ShadowCircuitBreakerEvaluator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sentinel.shadow_observer_daemon")

LIVE_STATE_PATH = os.environ.get("SHADOW_STATE_PATH", "runtime/shadow_evaluator_live_state.json")
NIFTY_WAL_PATH = os.environ.get("SHADOW_NIFTY_WAL_PATH", "/Users/madhuram/tradebot/runtime/sentinel_apm_wal.json")
SENSEX_WAL_PATH = os.environ.get("SHADOW_SENSEX_WAL_PATH", "/private/tmp/tradebot-sensex-engine/runtime/sentinel_apm_wal_sensex.json")

RUNNING = True

def handle_signal(sig, frame):
    global RUNNING
    logger.info(f"Received termination signal ({sig}). Initiating graceful shutdown...")
    RUNNING = False

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

def poll_wal_source(
    evaluator: ShadowCircuitBreakerEvaluator,
    wal_path: str,
    asset: str,
    is_live_stream: bool = False
) -> Dict[str, int]:
    """
    Polls a single Sentinel WAL file, ingests newly arrived proposals and exits,
    and updates in-flight positions safely.
    """
    if not os.path.exists(wal_path):
        return {"proposals": 0, "new_exits": 0, "in_flight": 0, "duplicates": 0}

    try:
        with open(wal_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read {wal_path}: {e}")
        return {"proposals": 0, "new_exits": 0, "in_flight": 0, "duplicates": 0}

    trade_history = data.get("trade_history", [])
    current_payload = data.get("payload")
    
    proposals_count = 0
    new_exits_count = 0
    duplicates_count = 0
    in_flight_count = 0

    # 1. Ingest completed trades from history.
    # CRITICAL PROVENANCE RULE: Any trade discovered already complete in trade_history
    # must be classified as RETROSPECTIVE_BACKFILL, UNLESS its proposal was previously
    # captured in the in-flight registry during a prior poll cycle when it was open!
    for t in trade_history:
        pid = t.get("position_id")
        date = (t.get("entry_time") or "")[:10]
        direction = t.get("direction")
        contract = t.get("strike_contract")
        entry_time = t.get("entry_time") or ""
        exit_time = t.get("exit_time") or ""
        
        scoped_key = evaluator._make_scoped_key(asset, date, pid)
        was_observed_in_flight_prior = (scoped_key in evaluator.proposal_registry and 
                                        evaluator.proposal_registry[scoped_key].get("provenance_mode") == "PROSPECTIVE_OBSERVED")
        
        # Step A: Observe proposal if not already captured
        # If discovered completed in trade_history without prior prospective proposal capture, is_live_event MUST BE False!
        is_prop_live = was_observed_in_flight_prior
        prop = evaluator.observe_trade_proposal(
            position_id=pid,
            asset=asset,
            session_date=date,
            direction=direction,
            contract=contract,
            proposal_timestamp=entry_time,
            is_live_event=is_prop_live
        )
        if prop.get("status") != "IDEMPOTENT_PROPOSAL_REPLAYED":
            proposals_count += 1

        # Step B: Observe exit
        spot_pnl = t.get("pnl_pts")
        opt_pnl = t.get("opt_pnl_pts")
        exit_reason = t.get("exit_reason") or ""
        opt_bid = t.get("opt_bid")
        opt_ask = t.get("opt_ask")

        # Exit is PROSPECTIVE_OBSERVED only if proposal was captured before exit occurred
        is_exit_live = was_observed_in_flight_prior and is_live_stream

        exit_res = evaluator.observe_trade_exit(
            position_id=pid,
            asset=asset,
            session_date=date,
            spot_pnl=spot_pnl,
            opt_pnl=opt_pnl,
            exit_reason=exit_reason,
            exit_timestamp=exit_time,
            opt_entry_bid=opt_bid,
            opt_entry_ask=opt_ask,
            is_live_event=is_exit_live
        )
        
        if exit_res.get("status") == "DUPLICATE_EXIT_IGNORED":
            duplicates_count += 1
        elif exit_res.get("status") not in ("QUARANTINED", "UNMATCHED_EXIT_QUARANTINED"):
            new_exits_count += 1

    # 2. Ingest active in-flight position if currently open in WAL payload
    # This is the genuine source of prospective proposal observation!
    # Compatible with ActivePositionManager states: IN_FLIGHT, TRAIL_LOCK, EXIT_PENDING (and ARMED/OPEN)
    wal_state = data.get("state")
    if current_payload and wal_state in ("IN_FLIGHT", "TRAIL_LOCK", "EXIT_PENDING", "ARMED", "OPEN"):
        open_pid = current_payload.get("position_id")
        open_date = (current_payload.get("entry_time") or "")[:10]
        open_dir = current_payload.get("direction")
        open_contract = current_payload.get("strike_contract")
        open_time = current_payload.get("entry_time") or ""
        
        prop_open = evaluator.observe_trade_proposal(
            position_id=open_pid,
            asset=asset,
            session_date=open_date,
            direction=open_dir,
            contract=open_contract,
            proposal_timestamp=open_time,
            is_live_event=True
        )
        if prop_open.get("status") != "IDEMPOTENT_PROPOSAL_REPLAYED":
            proposals_count += 1
        in_flight_count += 1

    return {
        "proposals": proposals_count,
        "new_exits": new_exits_count,
        "in_flight": in_flight_count,
        "duplicates": duplicates_count
    }

def run_single_poll_cycle(evaluator: ShadowCircuitBreakerEvaluator, is_live: bool = False) -> Dict[str, Any]:
    nifty_stats = poll_wal_source(evaluator, NIFTY_WAL_PATH, "NIFTY", is_live_stream=is_live)
    sensex_stats = poll_wal_source(evaluator, SENSEX_WAL_PATH, "SENSEX", is_live_stream=is_live)
    return {
        "NIFTY": nifty_stats,
        "SENSEX": sensex_stats,
        "total_ledger": len(evaluator.shadow_ledger),
        "quarantined": len(evaluator.quarantine_ledger),
        "unmatched": len(evaluator.unmatched_exit_queue),
        "in_flight": len(evaluator.in_flight_positions)
    }

def main():
    logger.info("Starting Sentinel Continuous Prospective Read-Only Shadow Observer Daemon (v5)...")
    logger.info(f"Targeting WALs:\n  NIFTY:  {NIFTY_WAL_PATH}\n  SENSEX: {SENSEX_WAL_PATH}")
    logger.info(f"Runtime State Storage: {LIVE_STATE_PATH}")
    
    # Fail-closed state initialization: require explicit SHADOW_ALLOW_FRESH_INIT if state file is missing
    allow_fresh = os.environ.get("SHADOW_ALLOW_FRESH_INIT", "false").lower() in ("true", "1", "yes")
    skew_limit = float(os.environ.get("SHADOW_MAX_CLOCK_SKEW_SEC", "300.0"))
    evaluator = ShadowCircuitBreakerEvaluator(
        max_consecutive_losses=2,
        log_path=LIVE_STATE_PATH,
        allow_fresh_init=allow_fresh,
        max_clock_skew_sec=skew_limit
    )
    
    # 1. Backfill phase (initial synchronous pass)
    logger.info("Executing Phase 1: Pure Historical Backfill (RETROSPECTIVE_BACKFILL)...")
    backfill_res = run_single_poll_cycle(evaluator, is_live=False)
    logger.info(f"Phase 1 Complete:")
    logger.info(f"  NIFTY:  {backfill_res['NIFTY']['proposals']} proposals, {backfill_res['NIFTY']['new_exits']} new exits.")
    logger.info(f"  SENSEX: {backfill_res['SENSEX']['proposals']} proposals, {backfill_res['SENSEX']['new_exits']} new exits.")
    logger.info(f"  Ledger Count: {backfill_res['total_ledger']} (Quarantined: {backfill_res['quarantined']}, Unmatched: {backfill_res['unmatched']})")
    
    # 2. Continuous prospective polling loop
    logger.info("Executing Phase 2: Continuous Prospective Polling Service Active (PROSPECTIVE_OBSERVED)...")
    
    # Check both SHADOW_MAX_POLL_ITERATIONS and SHADOW_POLL_ITERATIONS for test mode;
    # Default to None (continuous infinite operation until SIGINT/SIGTERM)
    max_iter_env = os.environ.get("SHADOW_MAX_POLL_ITERATIONS") or os.environ.get("SHADOW_POLL_ITERATIONS")
    max_iterations = int(max_iter_env) if max_iter_env else None
    poll_interval = float(os.environ.get("SHADOW_POLL_INTERVAL_SEC", "1.0"))
    
    if max_iterations is not None:
        logger.info(f"Operating in TEST FINITE MODE: max {max_iterations} cycles")
    else:
        logger.info("Operating in CONTINUOUS SERVICE DAEMON MODE (infinite loop)")
        
    iteration = 0
    while RUNNING:
        if max_iterations is not None and iteration >= max_iterations:
            break
        iteration += 1
        live_res = run_single_poll_cycle(evaluator, is_live=True)
        if live_res['NIFTY']['new_exits'] > 0 or live_res['SENSEX']['new_exits'] > 0 or live_res['NIFTY']['proposals'] > 0:
            logger.info(f"Poll #{iteration}: Detected and ingested new events: {live_res}")
        time.sleep(poll_interval)
        
    logger.info(f"Observer Daemon Cycle Finished. Total In-Flight: {len(evaluator.in_flight_positions)}; Total Ledger: {len(evaluator.shadow_ledger)}")

if __name__ == "__main__":
    main()
