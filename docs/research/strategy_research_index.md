# Strategy Research Index

This document tracks the current lifecycle status of all tested strategies.

## LIVE EXECUTION
*(None)*

## REAL PAPER VALIDATION (Observation Only)
- **`HTF_RANGE_EXPANSION`**: `READY_FOR_REAL_PAPER_VALIDATION`
  - *Spec Locked*: Yes
  - *Note*: Only structurally viable candidate. Explores the opening and trend-continuation volatility expansion edge.

## FROZEN / DATA-GATED RESEARCH (Not Outcome-Evaluated)
- **`NIFTY_45DTE_VRP_V1`**: `SPEC_FROZEN_DATA_GATED`
  - *Spec Locked*: Yes
  - *Compatibility*: Research only; direct option selling is not production-compatible with BUY_ONLY.
  - *Note*: Canonical-family 42–48 DTE / ~16-delta NIFTY short-vol reproduction. Exact historical outcome evaluation is blocked until real multi-expiry option data with sufficient contract identity and executable bid/ask evidence is hash-bound and passes the candidate data audit. Synthetic/realish chains cannot certify it.
- **`NIFTY_45DTE_VRP_TRANSLATOR_BUYONLY_V1`**: `SPEC_FROZEN_DATA_GATED`
  - *Spec Locked*: Yes (`research/nifty_45dte_vrp_v1/translator_spec_v1.json`)
  - *Compatibility*: BUY-only research context gate; cannot create a trade or change CE/PE direction.
  - *Note*: Tests whether a leakage-safe 45-DTE implied-vs-realized volatility state improves an exact-SHA frozen BUY-only baseline. Morning signals can consume only prior available volatility states.

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
