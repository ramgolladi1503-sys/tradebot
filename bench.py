import time, os
from config import config as cfg
os.environ["EXECUTION_MODE"] = "LIVE"
from core.orchestrator import TradebotOrchestrator
from collections import Counter

orch = TradebotOrchestrator()
t0 = time.time()
orch._write_cycle_status_files(
    cycle_ok=True,
    cycle_stage="dummy",
    cycle_reason="dummy",
    last_error="",
    market_mode="LIVE",
    market_open=True,
    symbols_scanned=50,
    trade_build_attempts=0,
    candidates_seen=0,
    candidates_blocked=0,
    candidates_enqueued=0,
    blocker_counts=Counter(),
    suggestion_count=0,
)
print("took", time.time() - t0)
