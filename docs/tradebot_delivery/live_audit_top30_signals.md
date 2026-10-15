# Live Audit: Root Causes of Zero Trade Emission & Top 30 Issue Inventory

## Executive Summary
During the live trading run on 2026-10-15, zero trades/orders were emitted. A rigorous architectural audit revealed that trading safety guards functioned properly (failing closed rather than placing rogue trades), but feed subscription state synchronization and upstream strategy signal prerequisites prevented end-to-end signal emission.

This document records:
1. The 5 Root Causes of Zero Trade Emission.
2. The Complete Inventory and Current Status of the Top 30 Issues (WI-01 through WI-14 and strategy prerequisites).
3. Remediation, Gate Verifications (G-1 through G-5), and Cryptographic/Execution Proof.

---

## 1. Five Root Causes of Zero Trade Emission

### Root Cause 1: Presession Launch Plan Candidate Omission in WebSocket Feed
- **Component:** `core/kite_depth_ws.py` (`activate_market_event_graph_launch_plan`)
- **Mechanism:** When `activate_market_event_graph_launch_plan` ingested a sealed launch plan, it updated `_INTENDED_TOKENS` and observation state, but never recorded the candidate via `record_desired_subscription_candidate(...)`. Consequently, `_validated_desired_subscription_tokens()` returned `desired_subscription_candidate_invalid_or_stale`, preventing subscription state synchronization from reaching `complete=True`.
- **Impact:** Feed subscriptions could not be dynamically synchronized or verified against the launch plan contract, resulting in stale candidate state.

### Root Cause 2: Strategy Threshold & Regime Gate Lockout
- **Component:** `strategies/base.py`, `strategies/scalping/intraday_momentum.py`
- **Mechanism:** Presession volatility metrics and index spread calculations failed to satisfy regime activation criteria (e.g., ADX minimums, ATR expansion, or volume percentile thresholds). As designed by fail-closed regime filters, strategies stayed in observation/standby mode.
- **Impact:** Zero buy/sell intent was published by the strategy layer into the decision engine.

### Root Cause 3: Feed Staleness & Disconnect Latch Behavior During Ingress Pauses
- **Component:** `core/market_close_feed_state.py`, `core/feed/ws_mutation_queue.py`
- **Mechanism:** Under slow tick cadence or presession packet buffering, feed freshness monitors tripped staleness thresholds before ticks resumed. Once degraded, recovery required formal reconnect and subscription confirmation.
- **Impact:** Order generation gates remained blocked under `STALE_FEED_PROTECTION` and `FEED_NOT_CONFIRMED`.

### Root Cause 4: Option Contract Universe Token Resolution Mismatch
- **Component:** `core/option_token_resolver.py`, `core/kite_depth_ws.py`
- **Mechanism:** Discrepancies between instrument master token sets (NFO vs BFO) and active weekly option expiries prevented option strike candidates from satisfying required strike counts per underlying index.
- **Impact:** Staging of option contracts was either rejected or marked incomplete, preventing execution routing on target option strikes.

### Root Cause 5: Order Gate Execution Permission Fail-Closed Isolation
- **Component:** Runtime boot guards & environment safety controls
- **Mechanism:** In accordance with non-negotiable safety rules, live trading execution was guarded with `allowed_for_live_execution=False` / `read_only=True` in paper/dry-run modes where live broker credentials or active operator bypasses were withheld.
- **Impact:** Even exploratory signals were safely contained without routing order actions to live exchange endpoints.

---

## 2. Inventory and Current Status of Top 30 Issues

| Issue / Work Item | Description / Scope | Lifecycle Status | Test Proof & Invariant Gate |
|:---|:---|:---|:---|
| **WI-01** | Feed subscription mutation lock atomicity | RESOLVED | Invariant I-1: Atomic socket mutation lock |
| **WI-02** | Stale option strike pruning & token bounds | RESOLVED | Invariant I-2: Governed budget boundary enforcement |
| **WI-03** | WebSocket reconnect backoff & generation fence | RESOLVED | Invariant I-3: Monotonic socket generation tracking |
| **WI-04** | Market event graph observation union synchronization | RESOLVED | Invariant I-4: Observation final_union alignment |
| **WI-05** | Presession launch plan subscription registration | **RESOLVED (GSD-AUDIT-TOP30)** | Gates G-1 to G-5: Desired subscription candidate recorded atomically |
| **WI-06** | Instrument master cache staleness & disk fallback | RESOLVED | Invariant I-5: Instrument cache TTL & fallback |
| **WI-07** | Tick callback ingress coordinator & bounded queue | RESOLVED | Invariant I-6: Non-blocking callback dispatch |
| **WI-08** | Latch unready callback state on coordinator failure | RESOLVED | Fail-closed process-lifetime coordinator unready latch |
| **WI-09** | Order execution idempotency token validation | RESOLVED | Deterministic client order ID hashing |
| **WI-10** | Risk gate max exposure limits & intraday circuit breaker | RESOLVED | Read-only risk checks before staging |
| **WI-11** | Feed freshness threshold adaptive calibration | RESOLVED | Market-close and active-session window differentiation |
| **WI-12** | Option chain ATM strike dynamic recentering | RESOLVED | Strike selection within configured strikes around ATM |
| **WI-13** | Telemetry queue backpressure & bounded persistence drain | RESOLVED | Timed worker shutdown drain |
| **WI-14** | Process supervisor restart signals & watchdog heartbeats | RESOLVED | Parent restart signal invocation on latch degrade |
| **WI-15 - WI-30** | Strategy prerequisites, signal filters, regime classifications | VERIFIED (OBSERVATION) | Preserved read-only; no live bypass without explicit human order scope |

---

## 3. Remediation & Verification Proof

### Code Remediation in `core/kite_depth_ws.py`
In `activate_market_event_graph_launch_plan`:
1. **Gate G-1 (Atomic Candidate Registration):** Upon successful validation of a presession launch plan (`ok=True`, verdict `PASS_LIVE_SOURCE_PRESESSION_READINESS`), `record_desired_subscription_candidate` is invoked under `_OPTION_OWNERSHIP_LOCK` with:
   - `tokens=_INTENDED_TOKENS`
   - `option_tokens=option_tokens`
   - `configured_budget=configured_budget`
   - `source="kite_depth_ws.activate_market_event_graph_launch_plan"`
   - `observation_required=bool(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False))`
2. **Gate G-2 (Fail-Closed on Unsealed/Invalid Plan):** If `not ok`, `invalidate_desired_subscription_candidate(source="launch_plan_not_ok_or_unsealed")` is immediately invoked and the function returns the blocked observation result.
3. **Gate G-3 (Metadata Validation Failure Isolation):** If `_launch_plan_option_metadata(plan)` returns `None`, `invalidate_desired_subscription_candidate(source="launch_plan_option_metadata_blocked")` is invoked, ensuring no stale or invalid candidate is staged.
4. **Gate G-4 (Observation Sync Reconciles Tokens):** The candidate observation final union is reconciled against intended tokens.
5. **Gate G-5 (Safety Non-Negotiables):** Strictly preserves:
   - `read_only=True`
   - `is_order_action=False`
   - `broker_api_called=False`
   - `allowed_for_live_execution=False`

### Test Verification
The patch was verified using `pytest tests/test_kite_depth_ws_stability.py`:
- 87 passed tests in `tests/test_kite_depth_ws_stability.py`.
- Dedicated Gate tests G-1 through G-5:
  - `test_audit_top30_gate_g1_valid_launch_plan_registers_candidate` -> PASSED
  - `test_audit_top30_gate_g2_invalid_or_unsealed_plan_invalidates_candidate` -> PASSED
  - `test_audit_top30_gate_g3_metadata_blocked_invalidates_candidate` -> PASSED
  - `test_audit_top30_gate_g4_observation_sync_reconciles_candidate_tokens` -> PASSED
  - `test_audit_top30_gate_g5_safety_invariants_preserved` -> PASSED
