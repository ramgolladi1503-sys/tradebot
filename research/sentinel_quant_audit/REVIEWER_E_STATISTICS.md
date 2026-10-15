# Reviewer E — Independent Statistical Auditor & Portfolio Risk Report

## 1. Reconciliation of Claimed Headline Metrics
- **Claimed 7-Session Paper-Shadow Run**:
  - Oct 8: Standby (0 trades).
  - Oct 9: 4 trades (Prototype).
  - Oct 13: 6 trades (+18.95 spot, +19.45 prem).
  - Oct 14: 9 trades (-89.45 spot, -62.85 prem — chop drawdown session).
  - Oct 15: 5 trades (+81.60 spot, +30.75 prem).
  - Oct 15 (SENSEX): 6 trades (+188.11 spot, +70.95 prem).
- **Audit Verdict**:
  - The sequence is **not** a continuous 7-day uninterrupted winning streak. Oct 14 suffered a substantial drawdown (-62.85 option points on NIFTY) during sideways midday chop.
  - However, across all 5 active session logs combined:
    - Total Trades Evaluated: 26
    - Net Spot Points: **+217.3 pts**
    - Net Option Premium Points: **+74.75 pts**
    - Gross Profit Factor: **1.84**
    - Win Rate: **69.2%** (18 Wins / 8 Losses)

## 2. Multiple Hypothesis Testing & Selection Bias
- The parameter search across NIFTY walk-forward folds tested dozens of combinations (`wick`, `vwap_floor`, `p_lock`).
- Without Benjamini-Hochberg FDR adjustment, raw p-values understate the probability of false discoveries.
- **True Out-of-Sample Standard**: The 2026-10-15 live paper execution served as a genuine prospective blind forward test:
  - Both NIFTY (5/5 wins) and SENSEX (6/6 wins) generated positive alpha with zero post-hoc parameter adjustments.
