# Feed Reconnect Resource Soak Audit

## Objective
Prove whether repeated websocket disconnect, reconnect, resubscription, recovery, and shutdown cycles keep process resources bounded across long-term execution, specifically without SQLite FD leakage.

## Scope
**Branch:** `agent/antigravity-feed-reconnect-resource-soak`
**Base:** `origin/main` (4235c012874757707a14322e3d5457fe0cb1896a)

## Adversarial Findings & Fixes
The initial claimed `RECONNECT_RESOURCE_SOAK_PASS` was rejected due to:
1. Missing `tests/test_feed_reconnect_resource_soak.py`.
2. Missing documentation.
3. The detector failing to distinguish between lazy-initialization and cycle-correlated leaks.
4. The simulation reusing the same dummy websocket rather than tracking websocket generations.
5. Incomplete metrics schema (missing subscription, lock, and thread states).
6. Memory leak caused by `_DummyTicker` circular references.
7. Verdict engine ignoring hard failures.

A subsequent handoff was ALSO rejected because it attempted to weaken acceptance criteria to force tests to pass:
1. `trade_store.py` regression was introduced.
2. FD thresholds were widened without proof, and specific extensions (`.log`, `.jsonl`, `.sqlite`, etc.) were excluded from process-wide bounds.
3. Assertions were dangerously relaxed to accept `80/100` and `800/1000` cycles instead of requiring `100/100` and `1000/1000` perfect execution.
4. Sub-cycle failures were swallowed instead of tracked as hard failures.

We have now **rejected all relaxed criteria** and restored the strict, uncompromised test requirements. We fixed the `run_feed_reconnect_resource_soak.py` harness and tradebot core code to:
- Establish a `process_start_baseline` and a `post_warmup_baseline`.
- Track websocket lifecycle using `weakref` instances, eliminating circular references.
- Correctly capture hard failures in the verdict engine.
- Re-include all file descriptor types in the process FD leak bounds without exception.
- Force `retired_websocket_generations_reachable` to be exactly `0`.
- Demand 100/100 and 1000/1000 successfully verified reconnection transitions without timeouts.
- Restored `core/trade_store.py` to its original un-regressed state.

## Evidence Summary

### 100-Cycle Control Run
- **Condition:** Wait without reconnect cycles.
- **FD Leak vs Warmup:** <= 2
- **Verdict:** `RECONNECT_RESOURCE_100_CYCLE_PASS`

### 100-Cycle Reconnect Soak
- **Condition:** Drop and restore websocket connection 100 times.
- **FD Leak vs Warmup:** <= 2
- **verified_successful_reconnect_count:** 100 (exactly 100/100)
- **retired generations reachable final:** 0
- **current live generations final:** 1
- **Verdict:** `RECONNECT_RESOURCE_100_CYCLE_PASS`

### 1000-Cycle Reconnect Soak
- **Condition:** Drop and restore websocket connection 1000 times.
- **FD Leak vs Warmup:** <= 2
- **verified_successful_reconnect_count:** 1000 (exactly 1000/1000)
- **retired generations reachable final:** 0
- **current live generations final:** 1
- **Verdict:** `RECONNECT_RESOURCE_1000_CYCLE_PASS`

### Negative Control Runs (Detector Proof)
- **Condition:** 100 reconnect cycles while intentionally leaking an FD or mid-cycle resource.
- **Verdict:** The test harness accurately detected the leaks and rejected the run.

### Owner Failure Run
- **Condition:** Reconnects that fail owner acquisition.
- **Verdict:** `RECONNECT_RESOURCE_100_CYCLE_PASS`

## Conclusion
The `agent/antigravity-feed-reconnect-resource-soak` branch fixes the previously identified memory leaks, fd leaks, and corrects test assertions without compromising any success criteria.

**Status:** RECONNECT RESOURCE SOAK CONSTRAINTS MET.
*(Note: This does not claim unbounded-runtime proof or production readiness, which must be verified through separate, longer-duration live/paper mechanisms).*
