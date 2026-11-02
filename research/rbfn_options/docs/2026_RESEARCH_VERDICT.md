# Independent RBFN NIFTY Historical CE/PE Research Verdict

**Date:** 2026-11-02  
**Investigation:** Autonomous RBFN Option-Premium Research & OptionMate Level Validation  
**Evaluator:** Antigravity Autonomous Research Engine  
**Governance Standard:** Aixion Agent OS & TradeBot Safety Governance  
**Branch:** `feat/rbfn-nifty-options-research`  
**Verdict:** **`NO-GO / RESEARCH-ONLY`**

---

## Executive Summary

| Core Research Question | Empirical Finding | Status |
| :--- | :--- | :--- |
| **1. Can independent RBFN generate strike-specific option levels without look-ahead?** | **YES.** Successfully extracted strictly point-in-time features at 09:19 IST using completed 09:15–09:19 bars. Trained on 614 contract-sessions across 2024–2025 and forecasted 270 valid strike-specific level sets for 2026 holdout sessions. | **VALIDATED** |
| **2. Does a BUY-ONLY NIFTY CE/PE strategy deliver positive net INR after all estimated costs on untouched 2026 holdout data?** | **NO.** Across all 81 executed trades on 2026 holdout data, the strategy yielded **negative net INR (-₹5,604.68 base, -₹8,316.11 stress, -₹11,707.09 worst)** with a win rate of 44.44% (profit factor 0.8856). Friction and spread decay eliminate option buying profitability. | **FAILED / NEGATIVE** |
| **3. How close are our levels to OptionMate's morning levels?** | **NOT MEASURABLE.** Genuine ground-truth morning timestamped levels from OptionMate are absent from historical records. No match is claimed. | **NOT MEASURABLE** |

---

## 1. Empirical Results on Untouched 2026 Holdout Data

- **Evaluation Window:** 2026-01-01 to 2026-07-21 (135 trading sessions).
- **Candidate Universe:** Daily nearest-expiry ATM CE and PE contracts selected at 09:19 IST (270 candidate contracts).
- **Executed Trades:** 81 trades (1 trade/day global cap, remaining signals skipped or did not trigger level reclaims).
- **Model Comparison:** RBFN mean absolute error on target excursion was `0.4163` vs `0.4432` for training-mean baseline.

### Cost Sensitivity Matrix (81 Completed Trades)

| Cost Scenario | Half-Spread (pts) | Slippage/side (pts) | Gross PnL (INR) | Total Costs (INR) | Net PnL (INR) | Win Rate | Profit Factor |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Base** | 0.25 | 0.25 | -₹1,367.50 | ₹4,237.18 | **-₹5,604.68** | 44.44% (36W / 45L) | 0.8856 |
| **Stress** | 0.50 | 0.50 | -₹4,081.25 | ₹4,234.86 | **-₹8,316.11** | 39.51% (32W / 49L) | 0.6956 |
| **Worst** | 1.00 | 1.00 | -₹7,473.50 | ₹4,233.59 | **-₹11,707.09** | 37.04% (30W / 51L) | 0.5277 |

### Monthly Breakdown (Base Cost Scenario)

| Month | Trades | Gross PnL (INR) | Statutory & Broker Fees (INR) | Net PnL (INR) |
| :--- | :--- | :--- | :--- | :--- |
| **2026-01** | 15 | -₹1,112.50 | ₹761.30 | -₹1,873.80 |
| **2026-02** | 14 | -₹105.00 | ₹714.25 | -₹819.25 |
| **2026-03** | 10 | -₹875.00 | ₹530.52 | -₹1,405.52 |
| **2026-04** | 9 | -₹1,368.75 | ₹491.65 | -₹1,860.40 |
| **2026-05** | 12 | +₹948.75 | ₹649.22 | +₹299.53 |
| **2026-06** | 12 | +₹20.00 | ₹621.15 | -₹601.15 |
| **2026-07** | 9 | +₹1,125.00 | ₹469.09 | +₹655.91 |
| **Total** | **81** | **-₹1,367.50** | **₹4,237.18** | **-₹5,604.68** |

---

## 2. Independent Manual Trace Examples

### Trace A: Call Option (CE)
- **Contract:** NIFTY 26200 CE (Expiry 2026-01-06)
- **Date:** 2026-01-06
- **Lot Size:** 25
- **Forecast Generation:** 09:20:00 IST (Level: Lower Reversal = 13.8)
- **Signal Time:** 12:10:00 IST (reclaim of lower reversal level)
- **Entry Time & Price:** 12:11:00 IST @ 13.80
- **Exit Time & Price:** 12:55:00 IST @ 14.75 (Exit Reason: TIME, 45 min hold limit reached)
- **Gross PnL:** (14.75 - 13.80) * 25 = +₹23.75
- **Charges:** ₹48.01 (Brokerage Rs 40 + GST + STT + Turnover + Stamp)
- **Net PnL:** +₹23.75 - ₹48.01 = **-₹24.26** (Transaction fees turned a gross positive into net loss).

### Trace B: Put Option (PE)
- **Contract:** NIFTY 26200 PE (Expiry 2026-01-06)
- **Date:** 2026-01-02
- **Lot Size:** 25
- **Forecast Generation:** 09:20:00 IST (Level: Lower Reversal = 42.55)
- **Signal Time:** 10:49:00 IST
- **Entry Time & Price:** 10:50:00 IST @ 42.55
- **Exit Time & Price:** 11:34:00 IST @ 34.35 (Exit Reason: TIME, 45 min hold limit reached)
- **Gross PnL:** (34.35 - 42.55) * 25 = -₹205.00
- **Charges:** ₹49.24
- **Net PnL:** -₹205.00 - ₹49.24 = **-₹254.24**.

---

## 3. Statutory Cost & Friction Findings

1. **Fee Drag:** Across 81 trades, statutory charges and brokerage accumulated to **₹4,237.18** (an average penalty of ₹52.31 per round-trip trade).
2. **STT Surge:** From 2026-04-01 onwards, the STT on options sell turnover increased from 0.10% to 0.15%, expanding friction on option sellers and buyer exits.
3. **Spread Drag:** Because real bid/ask spreads are unobserved in vendor 1-minute OHLC files, simulated half-spreads (0.25 to 1.00 pts) degrade gross expectancy by an additional ₹2,713.75 (stress) to ₹6,106.00 (worst).

---

## 4. Final Verdict and Next Action

- **Verdict:** **NO-GO FOR LIVE TRADING.** The independent RBFN buy-only option premium replay fails the profitability gate on untouched 2026 holdout data.
- **Classification:** Research prototype is retained as a benchmark module under `research/rbfn_options/`.
- **Recommended Smallest Next Action:** Archive research artifacts, commit tests and documentation on branch `feat/rbfn-nifty-options-research`, and keep production live execution isolated.
