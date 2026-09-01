# Future-selected-tick drain repair review

## Agent Work Contract

mode: READ_ONLY_RUNTIME_REPAIR
candidate_id: FUTURE_SELECTED_TICK_DRAIN_REPAIR
decision: REVIEW_REQUIRED_BEFORE_MERGE
reason: interval projection selected a tick newer than its cutoff and aborted shutdown
timestamp: 2026-09-01T12:50:00+05:30
is_order_action: false
broker_api_called: false
source: protected main c526d570af2fb40ef615469aa27aedf2cdc39a71

## Scope Guard

Only MEG request-scoped tick projection and its tests are changed. Strategy, CAS, instrument authority, authentication, execution, broker writes, and feed ownership are untouched.

## Grill Me Review

Newer ticks are not cleared or silently accepted. The projection chooses an eligible tick at or before the interval cutoff; if none exists, it fails closed. Duplicate tick identities remain rejected.

## Hermes Review

`future_selected_tick` is a cutoff-boundary selection error, not a persistence queue slot. Newer lifecycle data remains available for a later interval; the current cycle requires a causally eligible tick.

## GSD Review

The repair is bounded to one projection function and regression tests, based on the exact failed-session evidence.

## QA / Safety Review

Tests cover no eligible tick, eligible prior tick with newer latest tick, idempotence, stale reuse, and complete causal evidence. No broker or order call is introduced.

## Acceptance Proof

The repaired projector never emits a tick after the cycle cutoff, does not duplicate a selected tick, and preserves fail-closed behavior when no eligible tick exists.

## Runtime Proof Required After Merge

Run a bounded read-only session with an explicit shutdown request and require all queues zero, staged state resolved, SQLite durable commit, workers joined, and locks released.

## What This PR Does Not Prove

It does not prove CAS eligibility, structural edge, execution viability, or full-session coverage.

## Human Approval

This repair follows the explicitly supplied `TRADEBOT_20260901_FUTURE_SELECTED_TICK_DRAIN_REPAIR_CAS_RECOVERY.md` specification.
