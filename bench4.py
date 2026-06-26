import time, os
from config import config as cfg
os.environ["EXECUTION_MODE"] = "LIVE"
from core.orchestrator import Orchestrator, _scan_visible_suggestions
from core.paths import canonical_suggestions_log_path, logs_dir
from core.events import write_json_atomic
from core.runtime_boot_identity import stamp_runtime_payload
from core.cycle_semantics import derive_cycle_semantics
from collections import Counter
from datetime import datetime

orch = Orchestrator()
t0 = time.time()
ts_epoch = time.time()
ts_local = datetime.now().astimezone().isoformat()
print("step 1", time.time() - t0); t0 = time.time()

feed_status = orch._feed_status_for_heartbeat()
print("step 2 (feed_status)", time.time() - t0); t0 = time.time()

visible_counts = _scan_visible_suggestions(canonical_suggestions_log_path())
print("step 3 (scan)", time.time() - t0); t0 = time.time()

cycle_status = derive_cycle_semantics(market_mode="LIVE", market_open=True, suggestion_count=0, blocker_counts=Counter(), last_error="")
print("step 4 (derive)", time.time() - t0); t0 = time.time()

top_blockers = list(cycle_status.get("top_blockers") or [])
normalized_market_mode = str(cycle_status.get("market_mode") or "").strip().upper()
normalized_market_open = bool(cycle_status.get("market_open"))
visible_suggestion_count = int(visible_counts.get("visible_suggestion_count") or 0)
visible_advisory_count = int(visible_counts.get("visible_advisory_count") or 0)
visible_queue_only_count = int(visible_counts.get("visible_queue_only_count") or 0)
visible_executable_count = int(visible_counts.get("visible_executable_count") or 0)
visible_primary_blocker = str(visible_counts.get("primary_blocker") or "").strip() or None
suggestions_status = str(cycle_status.get("semantic_state") or "no_candidates")
suggestions_reason = cycle_status.get("dominant_reason")
suggestions_subreason = cycle_status.get("subreason")
suggestions_primary_blocker = cycle_status.get("primary_blocker")
suggestions_payload = {"ts_epoch": ts_epoch}
engine_payload = {"ts_epoch": ts_epoch}
print("step 5 (assign)", time.time() - t0); t0 = time.time()

write_json_atomic(logs_dir() / "suggestions_status.json", stamp_runtime_payload(suggestions_payload, writer="orchestrator.suggestions_status"))
print("step 6 (write 1)", time.time() - t0); t0 = time.time()

write_json_atomic(logs_dir() / "engine_cycle_status.json", stamp_runtime_payload(engine_payload, writer="orchestrator.engine_cycle_status"))
print("step 7 (write 2)", time.time() - t0); t0 = time.time()
