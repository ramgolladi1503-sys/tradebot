# VWAP Failed Discovery Hypothesis V1 — Research Review

mode: HYPOTHESIS_RESEARCH_ONLY
candidate_id: VWAP_FAILED_DISCOVERY_RETURN_TO_VALUE_H1_V1
stage: HYPOTHESIS_FROZEN
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_strategy_design: false
allowed_for_runtime_wiring: false
allowed_for_live_execution: false

## Research boundary

This candidate tests one falsifiable market-behavior claim. It does not test an option strategy and cannot grant paper or live eligibility.

Signal authority is active NIFTY futures 1-minute OHLCV with strictly positive authoritative traded volume. NIFTY spot/unit-weight VWAP is forbidden. Option data is not consumed.

## Frozen claim

After accepted VWAP price discovery fails back inside the discovery band while remaining on the same side of VWAP, the probability of reaching frozen signal-time VWAP before re-breaking the failed discovery extreme is greater than for matched non-event controls, with positive directional-return uplift.

## Primary falsification target

The candidate should be rejected when sufficient DEV support exists but the frozen event does not achieve at least +5 percentage-point primary success-rate uplift versus matched controls or lacks positive directional-return uplift at the required 5/10/15-minute horizons.

Insufficient event support is `INCONCLUSIVE`, not a positive result.

## Leakage controls

1. Detector features are causal and use completed bars only.
2. Appending a future bar cannot alter prior VWAP values.
3. Event formation occurs before the VWAP outcome target has been touched.
4. Same-bar target/invalidation ambiguity resolves adversely as invalidation.
5. Controls are non-events, same direction, same 30-minute time bucket, same ATR/close volatility bucket, different trading date, deterministic and non-reused.
6. Holdout tuning is forbidden; formula changes after outcome access require a new version and new untouched boundary.
7. Strategy fields are prohibited from hypothesis code and checked in focused CI.

## Required validation order

1. DEV support and primary endpoint.
2. Matched controls.
3. Direction-flip and deterministic time-shift negative controls.
4. Small one-factor parameter-neighborhood robustness; no broad winner-selection grid.
5. Month/time-of-day/volatility concentration analysis.
6. Walk-forward OOS.
7. Independent oracle reproduction.
8. Untouched holdout.

Only after every gate passes may the verdict become `ROBUSTLY_SUPPORTED`.

## Strategy boundary

Even `ROBUSTLY_SUPPORTED` does not prove a monetizable strategy. It only authorizes opening a separate strategy-design candidate. That later candidate must independently determine execution vehicle, option structure, strike/DTE, fill model, exits, costs, sizing, paper behavior and commercialization viability.

## What this PR must not claim

- profitability;
- positive option expectancy;
- paper readiness;
- live readiness;
- commercial viability;
- that the hypothesis is already supported before authoritative corpus evaluation.

## Current engineering evidence

The PR contains the frozen contract, causal detector, outcome/control evaluator, focused invariants, and contamination CI. Economic validation remains pending until the kernel-authoritative historical futures corpus and preserved DEV/OOS/HOLDOUT partition are evaluated without rewriting V1.
