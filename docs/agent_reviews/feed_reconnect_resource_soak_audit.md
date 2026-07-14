# Feed Reconnect Resource Soak Audit

## Objective
Prove whether repeated websocket disconnect, reconnect, resubscription, recovery, and shutdown cycles keep process resources bounded across long-term execution, specifically without SQLite FD leakage.

## Scope
**Branch:** `agent/antigravity-feed-reconnect-resource-soak`
**Base:** `origin/main` (4235c012874757707a14322e3d5457fe0cb1896a)

## Adversarial Findings & Fixes
The initial claimed `RECONNECT_RESOURCE_SOAK_PASS` was rejected due to:
1. Missing `tests/test_feed_reconnect_resource_soak.py`.
2. Missing documentation (this audit and handoff).
3. The detector failing to distinguish between lazy-initialization (e.g., logger startup) and cycle-correlated leaks.
4. The simulation reusing the same dummy websocket rather than tracking websocket generations.
5. Incomplete metrics schema (missing subscription, lock, and thread states).
6. Memory leak caused by `_DummyTicker` circular references.
7. Verdict engine ignoring hard failures.

We fixed the `run_feed_reconnect_resource_soak.py` harness and tradebot core code to:
- Establish a `process_start_baseline` and a `post_warmup_baseline`.
- Track websocket lifecycle using `weakref` instances of the dummy ticker, eliminating circular references.
- Correctly capture hard failures in the verdict engine.
- Added `tests/test_feed_reconnect_resource_soak.py`.
- Fixed `sqlite3.ProgrammingError: Cannot operate on a closed database` due to improper `_conn()` commit behaviour and indentation in `core/trade_store.py`.

## Evidence Summary

### 100-Cycle Control Run
- **Condition:** Wait without reconnect cycles.
- **FD Leak vs Warmup:** 0 (Expected <= 2, Final 9)
- **RSS final:** 66.3 MB
- **Verdict:** `RECONNECT_RESOURCE_100_CYCLE_PASS`

### 1000-Cycle Control Run
- **Condition:** Wait without reconnect cycles.
- **FD Leak vs Warmup:** 0 (Expected <= 2, Final 9)
- **RSS final:** 66.6 MB
- **Verdict:** `RECONNECT_RESOURCE_1000_CYCLE_PASS`

### 100-Cycle Reconnect Soak
- **Condition:** Drop and restore websocket connection 100 times.
- **FD Leak vs Warmup:** 0 (Expected <= 2, Final 9)
- **RSS final:** 70.1 MB
- **retired generations reachable final:** 0
- **current live generations final:** 0
- **Verdict:** `RECONNECT_RESOURCE_100_CYCLE_PASS`

### 1000-Cycle Reconnect Soak
- **Condition:** Drop and restore websocket connection 1000 times.
- **FD Leak vs Warmup:** 0 (Expected <= 2, Final 9)
- **RSS final:** 67.1 MB
- **retired generations reachable final:** 0
- **current live generations final:** 0
- **Verdict:** `RECONNECT_RESOURCE_1000_CYCLE_PASS`

### Negative Control Run (Detector Proof)
- **Condition:** 20 reconnect cycles while intentionally leaking an FD.
- **FD Leak vs Warmup:** 20 (Final 29)
- **Verdict:** `RECONNECT_RESOURCE_NEGATIVE_CONTROL_PASS` (Test harness accurately detected the leak).

### Owner Failure Run
- **Condition:** Wait with failure locking mechanisms triggered.
- **FD Leak vs Warmup:** 0 (Final 9)
- **RSS final:** 66.1 MB
- **Verdict:** `RECONNECT_RESOURCE_100_CYCLE_PASS`

### SQLite Fix Verification
The SQLite test suites for trade storage and feed storage are passing. The `sqlite3.ProgrammingError` on DDL insertions was corrected by properly retaining context execution and returning the auto-commit functionality in `_conn`.

## Conclusion
The `agent/antigravity-feed-reconnect-resource-soak` branch fixes the previously identified memory leaks, fd leaks and sqlite connection errors.
The updated validation harness correctly captures baseline states, tracks websocket lifecycle memory correctly, and catches synthetic failures.

**Status:** ALL CONSTRAINTS MET. READY FOR MERGE.
