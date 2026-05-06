# Pro Strategy Layer Elite Design

> **For agentic workers:** This design is for an isolated hardening branch only. Do not touch `main` until the offline validation gates below are met and the branch has a clear rollback story.

**Goal:** Turn `feature/pro-strategy-layer` into a conservative, high-precision pro strategy layer that emits fewer but materially better signals, proves itself offline and in shadow evaluation, and can later be integrated into `main` behind feature flags and kill switches.

**Architecture:** The pro layer stays separate from the legacy ensemble. Signal generators must become specialist detectors with strict confirmation gates, the aggregator must prefer silence over conflict, and the adapter must only convert very high-quality signals into decision-engine candidates. Ranking is deterministic and conservative, with explicit penalties for weak data, regime conflict, stale quotes, and low execution quality.

**Tech Stack:** Python, `pytest`, existing `core.decision_engine`, `core.execution_quality`, `core.feature_builder`, `core.threshold_audit`, `core.reject_shadow`, `strategies.pro_layer`.

---

## Scope

This branch will harden the new pro strategy layer in isolation.

In scope:
- stricter signal generation rules
- stricter ranking and conflict handling
- offline validation and replay-based evaluation
- shadow telemetry compatibility
- later integration hooks guarded by config

Out of scope for this phase:
- changing live execution behavior in `main`
- broad refactors unrelated to the pro layer
- loosening gates to increase signal volume

## Strategy Requirements

The pro layer must be precision-first.

- Emit fewer signals.
- Require confirmation, not single-feature triggers.
- Prefer no trade over borderline trade.
- Reject conflicting directional evidence.
- Bias against stale, thin, or noisy inputs.

### Signal families

The current families remain, but each one must become stricter:

- `VolatilityExpansionStrategy`
- `LiquidityImbalanceStrategy`
- `VWAPMeanReversionStrategy`
- `OptionsFlowStrategy`
- `TimeWindowStrategy`

Each family must have:
- a primary trigger
- at least one confirmation check
- an explicit invalidation path
- a regime allowance list

### Precision rules

- Volatility expansion requires both movement and volatility confirmation.
- Liquidity imbalance requires clear depth imbalance plus acceptable spread and freshness.
- VWAP mean reversion requires extension plus momentum exhaustion evidence.
- Options flow requires directional alignment across price and options pressure.
- Time window momentum is a booster only, not a standalone free pass.

## Ranking Requirements

Ranking must be deterministic and conservative.

The pro aggregator should:
- drop low-confidence signals early
- return nothing when call/put strength is conflicted
- keep only the dominant direction when there is moderate but not overwhelming agreement
- penalize stale or degraded market data
- reward execution readiness only when the quote, spread, and liquidity gates already pass

The adapter must:
- map a pro signal into a decision-engine candidate without inflating confidence
- preserve the original signal and evidence in `source_flags`
- keep the candidate non-executable unless upstream data already supports execution
- never widen gates just to produce more candidates

## Offline Validation

Before any runtime integration, validate the pro layer offline with:

- deterministic unit tests for each family
- conflict and suppression tests
- replay-oriented tests on ranked decisions
- shadow telemetry tests for `reject_shadow` and `threshold_audit`
- precision-oriented acceptance checks on candidate quality

Validation should answer:
- how many signals survive per regime
- how often the aggregator suppresses conflict
- whether precision improves when coverage drops
- whether the top-ranked signal is stable across identical inputs

## Safety and Governance

The branch must fail closed.

- Default behavior must remain conservative.
- Any new runtime path must be behind a feature flag.
- Any integration hook must have a kill switch.
- No live execution logic changes until the offline bar is met.
- Every new field written to telemetry must be backward compatible.

## Success Criteria

The branch is considered ready for integration only if:

- strategy tests pass
- replay and shadow validation pass
- the pro layer emits fewer, higher-quality signals
- ranking is deterministic
- no conflicts or stale-data cases leak through as executable candidates
- integration can be staged behind flags without altering existing live behavior

## Rollout Plan

1. Harden signal logic and ranking inside `strategies/pro_layer`.
2. Expand offline tests for precision, conflict suppression, and regime selectivity.
3. Verify telemetry compatibility in `core.reject_shadow` and `core.threshold_audit`.
4. Add integration hooks behind flags only after offline validation is clean.
5. Re-verify with focused tests, then broader branch tests.

## Risks

- Over-tightening can suppress too many valid opportunities.
- Hidden regressions can appear if telemetry fields are dropped or renamed.
- Integration too early would blur the difference between signal quality and runtime safety.

## Operational Notes

- Do not merge this work into `main` until the branch proves itself in isolated validation.
- Keep the current workspace and `main` untouched while hardening happens in the separate worktree.
- Preserve rollback: the pro layer must remain separable from the legacy path.
