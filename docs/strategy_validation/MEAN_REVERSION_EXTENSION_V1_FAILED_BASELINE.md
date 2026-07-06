# MEAN_REVERSION_EXTENSION V1 Failed Baseline Report

**Strategy Version:** V1
**Status:** MRE_V1_PARAMETER_SPACE_FAILED
**Data Source:** Audited Upstox NIFTY/BANKNIFTY 1-minute candles
**Data Period Used:** 
- Train: 2024-07-01 to 2025-03-31
- Validation: 2025-04-01 to 2025-12-31
- Final Holdout: 2026-01-01 to 2026-07-03

## Validation Phases Completed
- **Phase 4.5:** Truth Audit (Passed)
- **Phase 4.7:** Integrity / Overtrading (Passed)
- **Phase 4.8:** Selection Quality / Cap Saturation (Passed)
- **Phase 4.9:** Cohort Edge Decomposition (Passed)
- **Phase 4.10:** Accounting Invariants / Unit-Coherent Cost Model (Passed)
- **Phase 4.11B:** Nested Parameter Discovery / Anti-Overfit Guard (FAILED)

## Full Grid Results
- **Full Grid Combinations Tested:** 972
- **Train Pass Count:** 16
- **Validation Pass Count:** 0
- **Region Stable Count:** 0
- **Final Holdout Evaluated Count:** 0

## Final Classification
**MRE_V1_PARAMETER_SPACE_FAILED**

## Reason for Failure
Train-only profitability failed completely to generalize to the Validation epoch after rigorous proxy option execution costs were applied. Every single parameter combination that survived the Train period collapsed and lost money Out-Of-Sample.

## Execution Rule
Phase 5 Walk-Forward Analysis (WFA) is permanently blocked for MEAN_REVERSION_EXTENSION V1.

*Note: This strategy V1 is preserved as a failed benchmark to ensure future systems must overcome strict execution costs before being granted access to holdout data.*
