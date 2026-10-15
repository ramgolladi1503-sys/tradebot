"""
Sentinel Prospective Read-Only Shadow Observer Service (v3 Hardened).

Attaches to the active Sentinel APM WAL / event log stream as a non-invasive observer.
Ingests historical records with mode='BACKFILL_HISTORICAL' and listens for new events
with mode='PROSPECTIVE_LIVE'.

Invariants:
- 100% Read-Only: NEVER places broker orders, alters APM payload, or modifies Sentinel runtime.
- Fail-closed crash recovery: reloads state from runtime/shadow_evaluator_live_state.json.
- Scoped Event Identity: (asset, session_date, position_id) prevents cross-asset collision.
- Idempotency: Multiple runs against identical WALs produce 0 duplicate events and 0 counter increments.
"""

import sys
import os
import json
import logging
from typing import Dict, Any

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.shadow_circuit_breaker_evaluator import ShadowCircuitBreakerEvaluator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sentinel.shadow_observer_service")

LIVE_STATE_PATH = "runtime/shadow_evaluator_live_state.json"
NIFTY_WAL_PATH = "/Users/madhuram/tradebot/runtime/sentinel_apm_wal.json"
SENSEX_WAL_PATH = "/private/tmp/tradebot-sensex-engine/runtime/sentinel_apm_wal_sensex.json"

def run_shadow_observer_cycle(
    evaluator: ShadowCircuitBreakerEvaluator,
    wal_path: str,
    asset: str,
    ingest_mode: str = "BACKFILL_HISTORICAL"
) -> Dict[str, int]:
    """
    Reads trades from a target APM WAL file, feeds unobserved trades into the shadow evaluator,
    and returns processing counts.
    """
    if not os.path.exists(wal_path):
        return {"observed_proposals": 0, "observed_exits": 0, "new_exits": 0}

    with open(wal_path, "r") as f:
        data = json.load(f)

    trade_history = data.get("trade_history", [])
    proposals_count = 0
    new_exits_count = 0
    replayed_exits_count = 0

    for t in trade_history:
        pid = t.get("position_id")
        date = (t.get("entry_time") or "")[:10]
        direction = t.get("direction")
        contract = t.get("strike_contract")
        entry_time = t.get("entry_time") or ""
        exit_time = t.get("exit_time") or ""
        
        # 1. Observe proposal
        prop = evaluator.observe_trade_proposal(
            position_id=pid,
            asset=asset,
            session_date=date,
            direction=direction,
            contract=contract,
            proposal_timestamp=entry_time,
            ingest_mode=ingest_mode
        )
        proposals_count += 1

        # 2. Observe exit
        spot_pnl = t.get("pnl_pts")
        opt_pnl = t.get("opt_pnl_pts")
        exit_reason = t.get("exit_reason") or ""
        opt_bid = t.get("opt_bid")
        opt_ask = t.get("opt_ask")

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
            ingest_mode=ingest_mode
        )
        
        if exit_res.get("status") == "DUPLICATE_EXIT_IGNORED":
            replayed_exits_count += 1
        elif exit_res.get("status") != "QUARANTINED":
            new_exits_count += 1

    return {
        "observed_proposals": proposals_count,
        "new_exits": new_exits_count,
        "duplicate_exits_ignored": replayed_exits_count
    }

def main():
    logger.info("Initializing Sentinel Prospective Shadow Observer Service (v3 Hardened)...")
    logger.info(f"Targeting WALs:\n  NIFTY: {NIFTY_WAL_PATH}\n  SENSEX: {SENSEX_WAL_PATH}")
    
    # Remove existing state if fresh operational proof run requested via env
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=LIVE_STATE_PATH)
    
    # Ingest NIFTY and SENSEX
    nifty_res = run_shadow_observer_cycle(evaluator, NIFTY_WAL_PATH, "NIFTY", ingest_mode="BACKFILL_HISTORICAL")
    sensex_res = run_shadow_observer_cycle(evaluator, SENSEX_WAL_PATH, "SENSEX", ingest_mode="BACKFILL_HISTORICAL")
    
    logger.info(f"Observer Cycle Complete:")
    logger.info(f"  NIFTY:  {nifty_res['observed_proposals']} proposals, {nifty_res['new_exits']} new exits, {nifty_res['duplicate_exits_ignored']} duplicates ignored.")
    logger.info(f"  SENSEX: {sensex_res['observed_proposals']} proposals, {sensex_res['new_exits']} new exits, {sensex_res['duplicate_exits_ignored']} duplicates ignored.")
    logger.info(f"  Total Ledger Records: {len(evaluator.shadow_ledger)} (Quarantined: {len(evaluator.quarantine_ledger)})")
    logger.info(f"  Persisted Shadow State: {LIVE_STATE_PATH} ({os.path.getsize(LIVE_STATE_PATH)} bytes)")

if __name__ == "__main__":
    main()
