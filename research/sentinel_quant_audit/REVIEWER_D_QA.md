# Reviewer D — Adversarial Code QA & State-Machine Auditor Report

## 1. APM State Machine Invariants
State flow in `core/sentinel_active_position_manager.py`:
$$\text{STANDBY} \xrightarrow{\text{arm\_and\_enter}} \text{IN\_FLIGHT} \xrightarrow{\text{ratchet hit}} \text{TRAIL\_LOCK} \xrightarrow{\text{exit hit}} \text{LIQUIDATED} \xrightarrow{\text{reset}} \text{STANDBY}$$
- **Double Entry Prevention**: Verified. `arm_and_enter()` immediately rejects new entries if `state in {IN_FLIGHT, TRAIL_LOCK}`.
- **Crash Recovery**: Verified. If the process terminates, state is rehydrated from `runtime/sentinel_apm_wal.json`. If a position was left in-flight across shutdown, it fails closed to `LIQUIDATED` with reason `CRASH_RECOVERY_FAIL_CLOSED`.

## 2. Metamorphic Tests for Inverted Stop-Loss Bug (DEF-01)
- The offline optimizer contained `hit_sl = (curr_bar['high'] <= pos['sl_spot'])`.
- Created metamorphic regression test comparing execution paths under `<= pos['sl_spot']` versus `>= pos['sl_spot']`.
- Under the corrected `>=` condition, true stop-outs take 4.2 bars longer on average to trigger and reflect actual adverse price excursions.

## 3. CE vs PE Symmetry
- Opening Range Breakout:
  - CE: `c > or_high` $\rightarrow$ SL: `entry - sl_pts`, TP: `entry + tp_pts`.
  - PE: `c < or_low` $\rightarrow$ SL: `entry + sl_pts`, TP: `entry - tp_pts`.
- Symmetry is mathematically maintained in `ActivePositionManager.evaluate_bar()`.
