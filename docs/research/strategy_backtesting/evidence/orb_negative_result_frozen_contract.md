# ORB negative result frozen contract

Date: 2026-07-14
Worktree: `/Users/madhuram/.codex/worktrees/tradebot/orb-candle-validation`
Branch: `agent/codex-orb-candle-validation`
Starting HEAD: `3c369185ebd26b174a4b89b6d4b31af1be8578f8`

This document freezes the committed candle-research contract used to verify the opening-range breakout result.

## Frozen dataset and selection

- source root: `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`
- deterministic selection: committed 60-session NIFTY sample used by `docs/research/strategy_backtesting/evidence/orb_ohlcv_source_manifest.json`
- timestamp convention: exchange-local bar timestamps in the prepared candle frame
- session ordering: chronological, complete sessions only
- session timezone: exchange-local / IST-aligned session dates in the source corpus

## Frozen strategy semantics

- strategy label: `OPENING_RANGE_BREAKOUT`
- production callable used by the research harness: `strategies/movement/opening_range_breakout.py::generate_opening_range_retest_candidates`
- opening range: documented ORB research opening range in the candle harness
- signal condition: breakout/retest detection after the opening range completes
- direction mapping:
  - BUY_CALL profits when underlying rises
  - BUY_PUT profits when underlying falls
- feature proxy: `atr_volatility_z_proxy`
- price-context proxy: deterministic candle research proxy used by the harness
- entry model: next legal same-session candle open for the corrected research policy
- holding duration: fixed 15 minutes in the corrected research policy
- overlap policy: non-overlapping Layer C research trades
- friction: 2.0 bps baseline round-trip, with 5.0 bps and 10.0 bps sensitivity checks

## Frozen result status

The earlier candidate/trade numbers are preserved for traceability but are not the operative evidence for the final conclusion. The validated result is the corrected, session-safe research run and its independent verification.

- candidate count: 1,628 on the corrected replayed candle study
- trade count: 1,628 on the corrected replayed candle study
- cross-session trades: 0
- overlapping Layer C trades: 0
- current verification conclusion: `NEGATIVE_RESULT_CONFIRMED`
- signal-level verdict: `ORB_SIGNAL_EDGE_NOT_SUPPORTED`
- OHLCV research-policy verdict: `NO_STRUCTURAL_EDGE`

## Strict replay lane

The strict option-replay lane is separate and remains:

- `INVALID_DUE_TO_DATA`

