# NIFTY MEG Missing Data Gap Matrix V1

This document outlines the gap analysis between the baseline 2026-08-04 Upstox V3 NIFTY-50 capture and the extended data requirements needed to validate Market Event Graph (MEG) causal propagation patterns.

---

## 1. Core Propagation Causal Chain
```text
Constituent Behaviour (EQ ticks)
  ↓
Sector/Leadership Propagation (Sector Indices)
  ↓
NIFTY Index & Futures Reaction (Spot & FUT ticks)
  ↓
Option Premium Response (ATM Option ticks, Greeks, IV)
```

---

## 2. Gap Matrix

| Data Dimension | Baseline V1 Corpus | Extended V1 Corpus (This Work) | Gap Status | MEG Causal Utility |
| :--- | :--- | :--- | :--- | :--- |
| **NIFTY Constituents** | 50 EQ Tick Streams | 50 EQ Tick Streams | Filled | Measures individual leadership/lagging behaviour. |
| **Index Spot** | NIFTY 50, Nifty Bank, Sensex, India VIX | NIFTY 50, Nifty Bank, Sensex, India VIX | Filled | Baseline target for overall market response. |
| **NIFTY Futures** | None | Front and Next Month Futures | Filled | Captures institutional/basis positioning and hedging flows. |
| **NIFTY Options (Weekly)** | Nearest Expiry (ATM ± 10) | Nearest Weekly Expiry (ATM ± 10) | Filled | Measures premium response and tail risk of near-term signals. |
| **NIFTY Options (Monthly)** | None | Nearest Monthly Expiry (ATM ± 5) | Filled | Captures longer-term position structures and macro regimes. |
| **Sector Indices** | None | Bank, IT, Auto, FMCG, Pharma, Metal, Energy, Financial Services | Filled | Identifies sectoral rotation and leadership propagation. |
| **Constituent Weights** | None | Dated snapshot files with neutral free-float weights | Filled | Weighs constituent ticks to calculate sector/index drift. |
| **Subscription Events** | Implicit in files | Explicit `subscription_events.jsonl` ledger | Filled | Ensures auditability of feed coverage and changes. |

---

## 3. Disclaimers

- **NO_STRUCTURAL_EDGE_CLAIM**: This document and the associated corpus do not claim to identify any structural edge or alpha-generating anomalies.
- **NO_PROFITABILITY_CLAIM**: None of the metrics, weights, or datasets in this repository are guaranteed to lead to profitable trading strategies.
- **NOT_A_KITE_LIVE_CERTIFICATION**: This data structure is specific to offline research and does not constitute a live trading certification for Zerodha Kite or any other broker.
