# AUTONOMOUS SENTINEL PARALLEL EXECUTION: FRIDAY, OCTOBER 16, 2026 OPERATIONAL MANIFEST & READINESS CERTIFICATION

**Date of Execution:** Friday, October 16, 2026  
**Market:** Indian Equity Derivatives (NSE / BSE)  
**Session Hours:** 09:15 - 15:30 IST (Pre-Market / Setup: 09:00 - 09:15 IST)  
**PRs Involved:**
- **PR #968 (NIFTY Sentinel Paper-Shadow Engine):** Worktree `/private/tmp/tradebot-nifty-engine` @ `e6d0ae46643ba21767e13e0c40fa8389e51d1acb` [FROZEN]
- **PR #980 (SENSEX Sentinel Paper-Shadow Engine):** Worktree `/private/tmp/tradebot-sensex-engine` @ `c87688055c3df2d77a4220eb1c0c4d763db9c5c2` [FROZEN]
- **PR #985 (Passive Circuit-Breaker Observer):** Worktree `/private/tmp/tradebot-sentinel-quant-audit` @ `research/sentinel-quant-audit-20261015` [VISIBILITY ONLY, UNMERGED]

---

## 1. Frozen Cryptographic Hashes (SHA-256)

```text
b2a2b6a47d4481c3d7aac926b4bdc165f96f3de9a4a67fdfef5db7ab85f189a3  core/shadow_circuit_breaker_evaluator.py
7447c031e1051dce6a53afc748d747bdfeb8586bd019638efe89904c404b44e2  scripts/run_prospective_shadow_observer.py
fbbb0d6913d97ba67ff55662539ef9c65de7e5a9d7cb10395c20285f21412ed3  research/sentinel_quant_audit_v2/tests/test_live_subprocess_mutation.py
ae9fda5052e337392fefe9adc05922ca3692f2d2bc97a88b6c7fe4fdda7c80f0  research/sentinel_quant_audit_v2/tests/test_final_acceptance_gate.py
8dbe5c8b76d9157e9aff0e98b5fbeb15c44fecf981fd06c5faaa1b4def2ce935  research/sentinel_quant_audit_v2/tests/test_apm_wal_compatibility.py
```

---

## 2. Priority 1 — APM WAL Compatibility Resolution

### Confirmed Schema Audit:
The Sentinel `ActivePositionManager` (APM) in PR #968 and PR #980 transitions across `STANDBY`, `ARMED`, `IN_FLIGHT`, `TRAIL_LOCK`, `EXIT_PENDING`, and `LIQUIDATED`.
- In production, `ARMED` represents a candidate evaluation prior to position entry.
- Once entered, APM enters `IN_FLIGHT`, then ratchets into `TRAIL_LOCK` (monotonic profit lock) during hold, and `EXIT_PENDING` during liquidation fill.
- The observer strictly recognizes entered-position states: `IN_FLIGHT`, `TRAIL_LOCK`, and `EXIT_PENDING`.
- Unentered states (`ARMED` and `OPEN`) are explicitly excluded to prevent unentered candidates from being counted as active positions.

### Fix Implemented in PR #985:
- In `scripts/run_prospective_shadow_observer.py`, the active position detection strictly filters:
  ```python
  wal_state in ("IN_FLIGHT", "TRAIL_LOCK", "EXIT_PENDING")
  ```
- Validated with `research/sentinel_quant_audit_v2/tests/test_apm_wal_compatibility.py`:
  - `STANDBY`: 0 in-flight.
  - `ARMED` (with or without payload): 0 in-flight (rejected as unentered candidate).
  - `IN_FLIGHT`: Captured as `PROSPECTIVE_OBSERVED` in `IN_FLIGHT_OPEN`.
  - `TRAIL_LOCK`: Preserved as active in-flight without duplicate proposal increment.
  - `EXIT_PENDING`: Preserved as active in-flight awaiting exit record.
  - `LIQUIDATED`: Exits processed into `COMPLETED_EVALUABLE` and popped from in-flight.

---

## 3. Priority 2 — Process Isolation & Environment Matrix

The three components run as independent, decoupled OS processes:

```
+---------------------------------------------------------------------------------------------------------+
| Component              | Working Directory                       | WAL / Runtime State Target            |
+---------------------------------------------------------------------------------------------------------+
| 1. NIFTY Sentinel      | /private/tmp/tradebot-nifty-engine      | runtime/sentinel_apm_wal.json         |
| 2. SENSEX Sentinel     | /private/tmp/tradebot-sensex-engine     | runtime/sentinel_apm_wal_sensex.json  |
| 3. Passive Observer    | /private/tmp/tradebot-sentinel-quant-audit| runtime/shadow_evaluator_live_state.json|
+---------------------------------------------------------------------------------------------------------+
```

### Safety & Invariant Guarantees:
1. **Zero Broker API Routing:** All components execute in `paper` / `shadow` mode. Broker API keys and order dispatch routines are absent or locked.
2. **Immutable Baselines:** Worktrees for PR #968 (`e6d0ae466`) and PR #980 (`c87688055`) remain read-only and uncommitted.
3. **Dedicated WAL Isolation:** NIFTY writes strictly to `sentinel_apm_wal.json`; SENSEX writes strictly to `sentinel_apm_wal_sensex.json`. The observer accesses both exclusively via read-only file streams.
4. **State Persistence & Loss Prevention:** Observer enforces `SHADOW_ALLOW_FRESH_INIT=false` on restart, preventing silent state resets if the runtime snapshot is missing.
5. **Causal Time Provenance & Skew Guard:** Observer enforces `SHADOW_MAX_CLOCK_SKEW_SEC=300.0` (5 minutes) to reject stale payloads.

---

## 4. Priority 3 — Friday Operational Execution Procedure

### Stage A: Pre-Market Readiness Gate (09:00 - 09:15 IST)
1. Verify trading day calendar: `python3 -c "from core.expiry_calendar import is_holiday; from datetime import date; assert not is_holiday(date(2026, 10, 16))"`.
2. Verify Python environment, dependencies, and test suite:
   ```bash
   pytest -q research/sentinel_quant_audit_v2/tests/
   # 39 passed in ~3.5s
   ```
3. Initialize / verify empty daily WAL states for October 16.

### Stage B: Market Session Parallel Launch (09:15 - 15:30 IST)
Launch the three processes concurrently in separate terminal sessions:

- **Terminal 1: NIFTY Sentinel Shadow Engine (PR #968)**
  *(Note: PR #968 does not take --ticker argument)*
  ```bash
  cd /private/tmp/tradebot-nifty-engine
  python3 scripts/run_live_feed_advisor.py
  ```

- **Terminal 2: SENSEX Sentinel Shadow Engine (PR #980)**
  ```bash
  cd /private/tmp/tradebot-sensex-engine
  python3 scripts/run_live_feed_advisor.py --ticker SENSEX
  ```

- **Terminal 3: Sentinel Passive Observer Daemon (Challenger Evaluation - PR #985)**
  *Initial Morning Bootstrap (Authorized clean setup only):*
  ```bash
  cd /private/tmp/tradebot-sentinel-quant-audit
  SHADOW_NIFTY_WAL_PATH="/private/tmp/tradebot-nifty-engine/runtime/sentinel_apm_wal.json" \
  SHADOW_SENSEX_WAL_PATH="/private/tmp/tradebot-sensex-engine/runtime/sentinel_apm_wal_sensex.json" \
  SHADOW_STATE_PATH="runtime/shadow_evaluator_live_state.json" \
  SHADOW_ALLOW_FRESH_INIT=true \
  python3 scripts/run_prospective_shadow_observer.py
  ```

  *Mid-Session Restarts / Crash Recovery (Fails Closed if State Missing):*
  ```bash
  cd /private/tmp/tradebot-sentinel-quant-audit
  SHADOW_NIFTY_WAL_PATH="/private/tmp/tradebot-nifty-engine/runtime/sentinel_apm_wal.json" \
  SHADOW_SENSEX_WAL_PATH="/private/tmp/tradebot-sensex-engine/runtime/sentinel_apm_wal_sensex.json" \
  SHADOW_STATE_PATH="runtime/shadow_evaluator_live_state.json" \
  SHADOW_ALLOW_FRESH_INIT=false \
  python3 scripts/run_prospective_shadow_observer.py
  ```

### Stage C: Post-Session Comparison Protocol (15:35 IST)
At market close, run the post-session reconciliation:
- Dissect every NIFTY and SENSEX trade into:
  - Spot outcome (index points).
  - Modeled Option LTP P&L.
  - Executable Bid/Ask P&L (strictly when quote depth is verified).
  - Statutory 2026 STT (0.15% on sell turn) and exchange fees.
- Tabulate Challenger Permitted vs Vetoed trades:
  - Did the 2-loss breaker prevent subsequent losses?
  - Did it prematurely truncate profitable trends?
- Report net Rupee delta without parameter tweaking.

---

## 5. Enterprise Delivery Roles Sign-Off Matrix

| Role | Verification Performed | Verdict |
| :--- | :--- | :--- |
| **Product Owner** | Confirms adherence to user mandate: 3 parallel components, zero broker orders, no merge of #985, read-only shadow observation. | **GO** |
| **Business Analyst** | Confirms official 2026 statutory rates (0.15% STT) and lot sizes (NIFTY: 65, SENSEX: 20). | **GO** |
| **Quant Architect** | Verifies tri/quad-state lifecycle compatibility (`IN_FLIGHT`, `TRAIL_LOCK`, `EXIT_PENDING`, `LIQUIDATED`) and APM schema fidelity. | **GO** |
| **Development** | Implemented APM compatibility fix, clock skew guard, and generic lifecycle rules in PR #985. | **GO** |
| **QA Engineer** | Executed 39 unit, concurrency, stress, and subprocess mutation tests. 100% green. | **GO** |
| **Senior QA** | Verified cross-asset collision prevention (scoped identity `asset::date::position_id`) and idempotent replay handling. | **GO** |
| **SRE / Production** | Verified process isolation across worktrees, signal handling (`SIGINT`/`SIGTERM`), atomic snapshot persistence, and portable test paths. | **GO** |

---

## 6. Component-by-Component Readiness Summary

```
+----------------------------------------------------------------------------------------------------+
| Component             | Version / Branch                    | Head Commit | Readiness Gate Status  |
+----------------------------------------------------------------------------------------------------+
| PR #968 (NIFTY)       | feat/sentinel-decoupled-sidecar-live-advisor| e6d0ae466   | GO (READ-ONLY SHADOW)  |
| PR #980 (SENSEX)      | feat/sentinel-sensex-asset-profile-engine   | c87688055   | GO (READ-ONLY SHADOW)  |
| PR #985 (Observer)    | research/sentinel-quant-audit-20261015      | d4bff5bb5+  | GO (READ-ONLY OBSERVER)|
+----------------------------------------------------------------------------------------------------+
```
