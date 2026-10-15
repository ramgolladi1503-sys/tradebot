# REVIEWER D: ADVERSARIAL QA & STATE MACHINE REPORT

**Reviewer Role:** Adversarial QA & State Machine Engineer (Reviewer D)  
**Mandate:** Attack PE/CE symmetry, target/stop collision ordering, WAL restoration, crash/outage behavior, guard bypass, test fixtures, and CI.  
**Branch:** `research/sentinel-quant-audit-20261015`  
**Evaluation Scope:** `core/active_position_manager.py`, `runtime/sentinel_apm_wal.json`, fail-closed crash recovery.

---

## 1. APM State Machine Architecture Audit

The `ActivePositionManager` (APM) is an event-driven position manager designed to track open trades, manage trailing stop ratchets, enforce 15-minute time exits, and persist atomic WAL snapshots.

### States Audited:
- `IDLE`: No trade in flight. Ready to accept new advisory signals.
- `ARMED`: Trade armed and pending first tick confirmation.
- `OPEN`: Position active; intrabar high/low and option tick LTPs monitored.
- `LIQUIDATED`: Position closed due to `TARGET_HIT`, `TRAILING_STOP_HIT`, `STOP_LOSS_HIT`, or `TIME_EXIT`.
- `CRASH_RECOVERY_FAIL_CLOSED`: Corrupted, unverified, or anomalous state preserved safely without re-entry.

---

## 2. Adversarial Attacks & Vulnerabilities Found

### Attack D.1: Intrabar Collision Priority (Target vs Stop Loss)
- **Vulnerability Scenario:** A high-volatility 1-minute candle expands both upwards and downwards, touching both the Target price and the Stop Loss price within the same 60-second window.
- **Audit in Baseline Code (`core/active_position_manager.py:440`):**
  - In `evaluate_bar`:
    ```python
    hit_tp = bar_high >= p.target_price if p.direction == "CE" else bar_low <= p.target_price
    hit_sl = bar_low <= p.current_sl if p.direction == "CE" else bar_high >= p.current_sl
    ```
  - If both `hit_tp` and `hit_sl` evaluate to `True`, which one executes?
  - In baseline: Target evaluation was checked first! If `hit_tp` was True, it recorded `TARGET_HIT` and exited, ignoring the stop loss!
- **Adversarial Invariant Violation:** This is an optimistic execution bias. In real trading, when a bar expands wildly in both directions, the stop loss may have been hit at second 05, but backtests award a target fill at second 55.
- **Remediation In Challenger:** **Fail-Closed Conservative Ordering.** When both target and stop loss boundaries are touched within the same candle, the state machine must resolve as `STOP_LOSS_HIT`.

### Attack D.2: WAL Persistence Non-Atomic Flushes
- **Vulnerability Scenario:** Power loss or SIGKILL during `wal.json` write.
- **Baseline Behavior:** Earlier versions performed direct file open and write. PR #968 hardened this with `.tmp.<pid>` writing and `os.replace` atomic renaming.
- **Verified Status:** Fixed in baseline commit `64f6fbcbe`.

### Attack D.3: Reproducing & Isolating DEF-01 in Test Fixture
- Reviewer D created `research/sentinel_quant_audit_v2/tests/test_pe_stop_loss_defect.py`.
- **Proof:**
  - `test_pe_stop_loss_inequality_counterexample` proves that `scripts/run_walk_forward_optimizer.py:119` (`curr_bar['high'] <= pos['sl_spot']`) immediately stops out winning PE trades.
  - `test_active_position_manager_is_unaffected_by_def01` proves that live runtime `core/active_position_manager.py:450` correctly used `>=` and avoided corrupting live paper runs.
- **Test Execution:**
  ```bash
  pytest -q research/sentinel_quant_audit_v2/tests/test_pe_stop_loss_defect.py
  # 2 passed in 0.15s
  ```

---

## 3. Reviewer D Recommendation & Verdict
- **Verdict:** **APM RUNTIME ROBUST; CONSERVATIVE COLLISION ORDERING AND DEF-01 OPTIMIZER FIX REQUIRED IN CHALLENGER.**
- The live APM handles crashes cleanly and persisted WALs without corrupting trade history. Intrabar collision resolution must be made strictly pessimistic.
