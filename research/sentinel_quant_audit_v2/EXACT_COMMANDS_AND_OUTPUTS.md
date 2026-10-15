# REPRODUCIBILITY LOG: EXACT COMMANDS AND OUTPUTS

This document records the exact terminal commands and tool executions performed during the Adversarial Quant Research Mission.

---

## 1. Protected Baseline Verification

```bash
# Verify PR #968 HEAD
git -C /Users/madhuram/tradebot rev-parse HEAD
# Output: e6d0ae46643ba21767e13e0c40fa8389e51d1acb

# Verify PR #980 HEAD
git -C /private/tmp/tradebot-sensex-engine rev-parse HEAD
# Output: c87688055c3df2d77a4220eb1c0c4d763db9c5c2
```

---

## 2. DEF-01 Reproduction & Regression Test

```bash
pytest -q research/sentinel_quant_audit_v2/tests/test_pe_stop_loss_defect.py
```
**Output:**
```text
..                                                                       [100%]
2 passed in 0.15s
```

---

## 3. Seven-Session Trade Reconciliation & Track Compilation

```bash
python3 research/sentinel_quant_audit_v2/reconcile_wal_history.py
```
**Output:**
```text
Processed 26 total positions (20 NIFTY, 6 SENSEX). Output saved to SEVEN_SESSION_TRADE_LEDGER.csv
```

---

## 4. Multi-Track Session Metrics Execution

```bash
python3 -c "
import csv
with open('research/sentinel_quant_audit_v2/SESSION_METRICS.csv') as f:
    for line in f:
        print(line.strip())
"
```
**Output:**
```text
asset,session_date,total_trades,evaluable_trades,wins,losses,breakeven,win_rate_pct,track0_spot_pts,track1_gross_opt_pts,track1_slipped_opt_pts,statutory_friction_rs,track2_net_rupee_pnl
NIFTY,2026-10-13,6,6,6,0,0,100.0,+49.95,+36.85,+36.25,315.89,+590.36
NIFTY,2026-10-14,9,8,5,3,1,62.5,-102.35,-62.80,-63.60,462.36,-2052.36
NIFTY,2026-10-15,5,5,5,0,0,100.0,+81.60,+29.75,+29.25,285.65,+445.60
SENSEX,2026-10-15,6,6,6,0,0,100.0,+188.11,+70.95,+70.35,320.42,+383.08
```
