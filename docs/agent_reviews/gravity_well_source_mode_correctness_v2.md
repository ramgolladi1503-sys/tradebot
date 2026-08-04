# Agent Review — Gravity-Well Source-Mode Correctness V2

## Agent Work Contract

Correct the earlier source-fidelity error, implement the published-description Trend, Midline and Bands state machines separately, preserve state across sessions, add an authoritative TRUE_VWMA lane that fails closed without positive volume, and keep option/runtime integration prohibited.

## Scope Guard

Allowed changes are limited to the source-mode research runner, focused tests, compact evidence and research documentation. Production strategies, TradeBuilder, ranking, feed runtime, risk, approval, broker, order, execution and dashboard paths are out of scope.

## Grill Me Review

The previous campaign overclaimed. It tested custom extensions rather than all built-in modes, used EMA instead of a neutral VWMA proxy, and reset state daily in the first correction. Those defects are now explicit and corrected. The current archive still cannot prove the true VWMA or option hypothesis.

## Hermes Review

Published-description signals use completed bars, persistent state across sessions, next-bar entry and same-session exits. TRUE_VWMA requires positive volume and fails closed otherwise. Price-only proxy evidence is labelled diagnostic and cannot certify source-code or option profitability.

## GSD Review

The change replaces a misleading source-fidelity claim with a bounded, reproducible study. No parameter search was performed. No validation survivor exists, so holdout remains sealed and production integration remains blocked.

## QA / Safety Review

- 493 sessions; 36,849 NIFTY five-minute bars;
- 295/99/99 chronological development/validation/sealed-holdout split;
- 7/7 focused tests passed;
- source state preserved across sessions;
- trade outcomes cannot cross sessions;
- TRUE_VWMA fails closed without positive volume;
- all executed proxy lanes have negative validation expectancy and PF below one;
- no broker call, order action, paper authority or live authority.

## Acceptance Proof

Bands reclaim validation expectancy is -2.36 bps under the uniform-volume SMA proxy and -4.82 bps under EMA sensitivity, with both bootstrap intervals entirely below zero. Trend and Midline variants are also negative with PF below one. The actual TRUE_VWMA lane is correctly blocked because the archive contains no positive NIFTY volume.

## Runtime Proof Required After Merge

None. This is a research-only draft and must not be promoted or merged as a production strategy. A later promotion requires a volume-bearing underlying, real option identity and a separate shadow campaign.

## What This PR Does Not Prove

It does not replicate the Pine source code exactly, prove true-VWMA profitability, prove option profitability, validate execution, or establish production readiness.

## Human Approval

The user explicitly requested a correctness audit and strategy correction. No approval was given to merge, register or trade the strategy.

## Final Review Verdict

```text
PREVIOUS_SOURCE_FIDELITY_CLAIM_INVALID
PUBLISHED_DESCRIPTION_MODES_REBUILT
NO_PRICE_ONLY_PUBLISHED_MODE_VALIDATION_SURVIVOR
TRUE_VWMA_HYPOTHESIS_NOT_EVALUATED
REAL_OPTION_EDGE_NOT_EVALUATED
HOLDOUT_SEALED
NO_STRATEGY_INTEGRATION
```

mode: RESEARCH
candidate_id: GRAVITY_WELL_SOURCE_MODES_V2
decision: FAIL_CLOSED
reason: Published-description proxy modes have no validation survivor; authoritative VWMA and real-option evidence are unavailable.
timestamp: 2026-08-04T16:16:00+05:30
is_order_action: false
broker_api_called: false
source: agent
