# Candidate Trade Forensics Report

## 1. Target Placement Failure (The Dominant Flaw)
Looking at the `target_reach_probability.csv`, we can see the exact drop-off in MFE.
- **TrendContinuation_BREAK_AND_RETEST** MFE probabilities:
  - Hit 0.5R: 82.4%
  - Hit 1.0R: 58.8%
  - Hit 1.5R: 58.8%
  - Hit 2.0R: 41.2%
- **TrendContinuation_EMA_PULLBACK** MFE probabilities:
  - Hit 0.5R: 66.3%
  - Hit 1.0R: 46.5%
  - Hit 1.5R: 38.4%
  - Hit 2.0R: 26.7%
- **TrendContinuation_OPENING_DRIVE** MFE probabilities:
  - Hit 0.5R: 67.7%
  - Hit 1.0R: 55.4%
  - Hit 1.5R: 43.1%
  - Hit 2.0R: 26.2%
- **TrendContinuation_PDH_PDL** MFE probabilities:
  - Hit 0.5R: 50.0%
  - Hit 1.0R: 37.5%
  - Hit 1.5R: 37.5%
  - Hit 2.0R: 6.2%
- **TrendContinuation_VWAP_RECLAIM** MFE probabilities:
  - Hit 0.5R: 0.0%
  - Hit 1.0R: 0.0%
  - Hit 1.5R: 0.0%
  - Hit 2.0R: 0.0%

**Conclusion:** The trades are generating positive directional momentum initially (often hitting 0.5R to 1R), but the hardcoded 2.0R target is statistically too far. The price action reverses and stops out the trade before 2R is reached.

## 2. Stop Placement Failure
The `mfe_mae_distribution.csv` shows the average MAE. Because stops are placed very tight (often 2-4 points on 1-min VWAP entries), natural noise wicks the trade out. The market then proceeds to the target without us. The MAE is hitting -1.0R (Stop Loss) aggressively.

## 3. Holding Time Decay
`holding_time_analysis.csv` demonstrates that trades exiting via `EOD_EXIT` (15:15) have significantly lower or negative PnL compared to trades that hit targets early. If a 'momentum' strategy hasn't hit its target within 30-45 minutes, momentum has decayed, and it usually bleeds out to a loss or time-exit.

## 4. Regime Mismatch
`regime_mfe_mae_matrix.csv` highlights that taking Trend Continuation entries during `CHOP` regimes yields highly negative net edge. The 1-minute 9/21 EMA slope is generating false 'TREND_UP' signals in what is actually a daily range. The signal quality relies on a broader timeframe regime filter that is currently absent.

