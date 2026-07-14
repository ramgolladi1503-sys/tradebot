# Feed Reconnect Resource Soak Audit

## Objective
Prove whether repeated websocket disconnect, reconnect, resubscription, recovery, and shutdown cycles keep process resources bounded across long-term execution, specifically without SQLite FD leakage.

## Scope
**Branch:** `agent/antigravity-feed-reconnect-resource-soak`
**Base:** `origin/main` (4235c012874757707a14322e3d5457fe0cb1896a)
**Target:** `agent/antigravity-feed-reconnect-resource-soak` tip.

## Adversarial Findings & Fixes
The initial claimed `RECONNECT_RESOURCE_SOAK_PASS` was rejected due to:
1. Missing `tests/test_feed_reconnect_resource_soak.py`.
2. Missing documentation (this audit and handoff).
3. The detector failing to distinguish between lazy-initialization (e.g., logger startup) and cycle-correlated leaks.
4. The simulation reusing the same dummy websocket rather than tracking websocket generations.
5. Incomplete metrics schema (missing subscription, lock, and thread states).

We fixed the `run_feed_reconnect_resource_soak.py` harness to:
- Establish a `process_start_baseline` and a `post_warmup_baseline`.
- Ensure strict identity-based FD tracking using `lsof`.
- Track websocket lifecycle using `weakref` instances of the dummy ticker.
- Properly expand the simulation's metric schema.

We also added a synthetic leak profile (`negative_fd_leak`) to prove the test harness correctly catches leaks, enforcing that a failure to crash on leaks is an overall failure.

## Evidence Summary

### 100-Cycle Control Run
- **Condition:** Wait without reconnect cycles.
- **FD Leak vs Warmup:** 0 (Expected <= 2)
- **Verdict:** `PASS`

### 100-Cycle Reconnect Soak
- **Condition:** Drop and restore websocket connection 100 times.
- **FD Leak vs Warmup:** 0 (Expected <= 2)
- **Verdict:** `PASS`

### Negative Control Run (Detector Proof)
- **Condition:** 20 reconnect cycles while intentionally leaking an FD.
- **FD Leak vs Warmup:** Detected
- **Verdict:** `RECONNECT_RESOURCE_NEGATIVE_CONTROL_PASS` (Test harness accurately detected the leak).

### SQLite Fix Verification
The SQLite leak in `core/storage/` and `core/feed/` was fixed by enforcing `@contextmanager` decorators across DB accesses and using `contextlib.closing` in `core/kite_depth_ws.py`. Direct testing confirmed standard block execution and exceptions successfully close the DB connection before returning to caller.

## Conclusion
The `agent/antigravity-feed-reconnect-resource-soak` branch fixes the previously identified SQLite file descriptor leakage during persistent websocket reconnections. 
The updated validation harness correctly captures baseline states, tracks websocket lifecycle memory correctly, and catches synthetic failures.

**Status:** ALL CONSTRAINTS MET. READY FOR MERGE.
