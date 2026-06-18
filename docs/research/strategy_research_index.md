# Strategy Research Index

This document tracks the current lifecycle status of all tested strategies.

## LIVE EXECUTION
*(None)*

## REAL PAPER VALIDATION (Observation Only)
- **`HTF_RANGE_EXPANSION`**: `READY_FOR_REAL_PAPER_VALIDATION`
  - *Spec Locked*: Yes
  - *Note*: Only structurally viable candidate. Explores the opening and trend-continuation volatility expansion edge.

## REJECTED
- **`VOL_EXPANSION_NAIVE`**: `REJECTED_TOXIC_REGIME`
  - *Note*: Naive breakouts in this regime suffer negative mathematical expectancy across all structures.
- **`ORB_BREAKOUT`**: `REJECTED_REGIME_PASSENGER`
  - *Note*: Holds 0 independent alpha. Expectancy was purely derived from the underlying volatility state, and its gating actively reduced performance relative to the baseline.
- **`HTF_OPENING_DRIVE_CONT`**: `A. Dead signal`
- **`HTF_15M_TREND_CONT`**: `A. Dead signal`
- **`HTF_15M_VWAP_PULLBACK`**: `A. Dead signal`
- **`HTF_FAILED_BREAKOUT_REVERSAL`**: `E. Too rare to judge`
- **`HTF_PDH_PDL_HOLD`**: `E. Too rare to judge`
