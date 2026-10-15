# REVIEWER E: STATISTICAL FALSIFICATION & RISK REPORT

**Reviewer Role:** Statistical Falsification & Risk Auditor (Reviewer E)  
**Mandate:** Challenge claimed seven-day success, dependence between trades, cherry-picking, false discoveries, repeated tuning, forward- and holdout-integrity, drawdown, and position size.  
**Branch:** `research/sentinel-quant-audit-20261015`  
**Evaluation Scope:** Statistical significance, sample size, regime fragility, and risk of ruin.

---

## 1. Statistical Falsification of Claimed Edge

### Statistical Sample Audit:
- **Total Observed Real-Time Sessions:** 3 trading days (`2026-10-13`, `2026-10-14`, `2026-10-15`).
- **Total Real-Time Paper Trades:** 26 trades.
  - Wins: 17
  - Losses: 8
  - Breakeven / Un-evaluated: 1
  - Nominal Win Rate: 68.0%

### Statistical Power & Significance:
- At $N = 25$ evaluable trades with a nominal win rate of $68\%$, the 95% Wilson Score Confidence Interval for the true win rate is:
  $$CI_{95\%} = [48.4\%, 82.8\%]$$
- **Critical Statistical Implication:**
  - The lower bound of the 95% confidence interval is **$48.4\%$**, which is **statistically indistinguishable from a random 50/50 coin toss**.
  - A sample of 26 trades across 3 trading days provides **zero statistical power** to reject the null hypothesis $H_0: \text{Edge} = 0$.
  - To achieve statistical significance ($p < 0.01$) for an edge with an observed Sharpe ratio of 1.2 at a daily frequency, a minimum sample of **60 to 90 independent trading sessions** (~3 to 4 months) is required.

---

## 2. Regime Fragility & Cherry-Picking Analysis

### The Oct 14 Regime Stress Test:
- **Oct 13:** Trend Day. Spot expanded cleanly. 6 trades, 6 wins (+49.95 spot pts).
- **Oct 14:** Sideways Range / Mean-Reverting Chop Day.
  - The ORB and KER filters generated 9 breakout entries.
  - Because price reversed inside the broad range, 5 trades were stopped out, and 3 trailing stops yielded fractional gains.
  - Spot PnL: **-102.35 pts**.
  - Net Rupee PnL: **-Rs 2,052.36**.
- **Oct 15:** Strong Trend Expansion Day.
  - NIFTY rallied +81.60 spot pts (5 wins).
  - SENSEX rallied +188.11 spot pts (6 wins).

### Findings on Regime Dependency:
1. **Regime Over-Concentration:** 100% of the strategy's profitability is derived from strong unidirectional expansion days where $KER$ remains elevated and price trends continuously outside the 15-minute range.
2. **Fatal Chop Vulnerability:** The strategy possesses no regime filter that completely ceases trading when the market enters low-variance oscillating chop. In chop, the ORB repeatedly triggers at the boundaries right as the move exhausts itself, buying tops and selling bottoms.
3. **Serial Correlation Between Intraday Trades:**
   - Trades executed within the same 60-minute window exhibit strong negative serial correlation during chop (a false CE breakout is immediately followed by a false PE breakdown).
   - The assumption of independent and identically distributed (i.i.d.) trade outcomes is completely violated.

---

## 3. Reviewer E Recommendation & Verdict
- **Verdict:** **INSUFFICIENT SAMPLE SIZE; UNPROVEN STATISTICAL SIGNIFICANCE; HIGH REGIME VULNERABILITY.**
- The empirical data cannot confirm a persistent edge. The positive returns on Oct 13 and Oct 15 are fully offset by the loss on Oct 14 in rupee terms.
- The system must remain strictly in paper/shadow mode until a minimum 60-session out-of-sample forward record is logged.
