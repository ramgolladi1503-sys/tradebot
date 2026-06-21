# HTF Cost-Adjusted Edge Retest Report

## Executive Summary
This report summarizes the cost-adjusted edge retest for the HTF strategies following their integration into the strict execution-truth boundary pipeline. The tests were run over 493 days (approx 2 years) of 1-minute historical NIFTY spot data, resampled to 15-minute bars to perfectly emulate HTF production execution boundaries.

> [!CAUTION]
> **Limitations & Caveats**
> This replay uses spot movement scaled to option-equivalent points. It is not a substitute for real option-chain replay using executable bid/ask quotes. No actual Option LTP/Bid/Ask data was used; P&L estimates assume symmetric Delta ~0.5 scaling.

## Evaluation Dataset
- **Date Range:** Approx 2 years (July 2022 onwards)
- **Total Trading Days:** 493
- **Total 1m Bars:** 183,861
- **Total 15m Bars:** 12,286

## Results by Strategy

### HTF_OPENING_DRIVE_CONT
* **Verdict:** `READY_FOR_PAPER_RETEST`
* **Trades:** 427
* **Win Rate:** 39.34%
* **Gross Expectancy:** 1.16 points
* **Realistic Net Expectancy (0.8pt cost):** 0.36 points
* **Average Win:** 14.78 points
* **Average Loss:** -7.68 points
* **Max Drawdown:** 323.58 points
* **Exit Distribution:** Targets: 145, Stops: 254, Time Stops: 28, EOD: 0
* **Month-by-Month Stability:** Profitable in 8 out of 14 active months.
* **Notes:** This strategy exhibits a genuine cost-adjusted edge. While the win rate is low (~39%), the asymmetric R:R (avg win is double the avg loss) allows it to survive realistic options cost structures.

### HTF_PDH_PDL_HOLD
* **Verdict:** `COST_KILLED_AFTER_CORRECT_IMPLEMENTATION`
* **Trades:** 8,766
* **Win Rate:** 36.84%
* **Gross Expectancy:** 0.66 points
* **Realistic Net Expectancy (0.8pt cost):** -0.14 points
* **Average Win:** 14.88 points
* **Average Loss:** -7.64 points
* **Max Drawdown:** 3273.75 points
* **Exit Distribution:** Targets: 2921, Stops: 5425, Time Stops: 420, EOD: 0
* **Month-by-Month Stability:** Profitable in only 10 out of 24 active months.
* **Notes:** This strategy triggers far too frequently. While it shows a tiny gross expectancy (0.66 pts), it is entirely consumed by friction and costs (slippage/brokerage) resulting in negative net expectancy. It must be abandoned for execution.

### HTF_15M_TREND_CONT
* **Verdict:** `FEATURE_ONLY_NOT_EXECUTABLE`
* **Trades:** 0
* **Notes:** The strategy logic is mathematically sound, but its strict baseline entry conditions never trigger against historical VWAP/Trend baselines without further dynamic relaxation.

### HTF_15M_VWAP_PULLBACK
* **Verdict:** `FEATURE_ONLY_NOT_EXECUTABLE`
* **Trades:** 0
* **Notes:** Fails to trigger. Suitable only as a secondary feature/context factor.

### HTF_FAILED_BREAKOUT_REVERSAL
* **Verdict:** `FEATURE_ONLY_NOT_EXECUTABLE`
* **Trades:** 0
* **Notes:** Fails to trigger.

## Cost Sensitivity Matrix (OPENING_DRIVE_CONT)
To understand the robustness of OPENING_DRIVE_CONT against varying friction, here is the cost-decay matrix (in points):
- **0.0 pt (Zero Cost):** 1.16 Net Expectancy
- **0.5 pt:** 0.66 Net Expectancy
- **0.8 pt (Realistic):** 0.36 Net Expectancy
- **1.2 pt:** -0.04 Net Expectancy (Cost Killed threshold)
- **1.5 pt:** -0.34 Net Expectancy
- **2.0 pt:** -0.84 Net Expectancy

## Next Step Paper Plan
Given that `OPENING_DRIVE_CONT` is the only survivor, the following protocol must be observed:
1. **Paper-Only:** No live orders.
2. **Execution Environment:** Capture actual option LTP/bid/ask using the live feed pipeline.
3. **Verification:** Compare expected spot-scaled P&L vs actual option P&L to validate the 0.8pt friction estimate.
4. **Volume:** Minimum 30 to 50 paper trades before any promotion discussion to LIVE.
