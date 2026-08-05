# Agent Review — Keltner/Hilega Shadow V1

mode: PROSPECTIVE_SHADOW_RESEARCH
candidate_id: KELTNER_HM_IMMEDIATE_CONFIRMATION_V1
decision: OFFLINE_IMPLEMENTATION_ACCEPTED_LIVE_EVIDENCE_REQUIRED
reason: Adds a frozen read-only observer that records causal underlying shadow events without entering ranking, risk, TradeBuilder, option selection, or execution paths.
timestamp: 2026-08-06T00:00:00Z
is_order_action: false
broker_api_called: false
source: PR_798_BRANCH_AND_FOCUSED_OFFLINE_TESTS
allowed_for_live_execution: false

## Purpose

Implement the frozen Keltner/Hilega immediate-confirmation candidate as a prospective observer so genuinely new sessions can validate or reject the retrospective signal without changing strategy parameters.

## Scope

The implementation is additive and read-only. It consumes completed five-minute bars, aggregates completed 15-minute and 75-minute bars, emits append-only evidence events, persists observer state, and calculates a fixed 60-minute underlying outcome.

## Files changed

- `core/keltner_hm_shadow/**`
- `scripts/run_keltner_hm_shadow_observer.py`
- `scripts/verify_keltner_hm_live_run.py`
- `tests/test_keltner_hm_shadow.py`
- `.github/workflows/keltner-hm-shadow-v1.yml`
- this review, the runbook, and the offline certificate

## Scope guard

In scope: causal completed-bar aggregation, frozen indicators, pending-event state transitions, deterministic event identity, durable restart state, append-only evidence, fixed 60-minute outcome, focused tests, and live-run verification.

Out of scope: production strategy registration, candidate ranking, capital allocation, option selection, order routing, broker connectivity, automatic promotion, parameter tuning, and profitability certification.

## Files not touched

No strategy registry, TradeBuilder, opportunity ranking, risk engine, execution router, broker client, authentication, feed subscription, dashboard, Telegram, or live configuration file is modified.

## Tests or reason not required

Focused tests prove exact aggregation output, incomplete-group rejection, EMA/WMA/RSI/ATR behavior, atomic persistence, permanent non-executable authority, exact JSONL writes, causal confirmation-to-entry-to-outcome sequencing, and duplicate completed-bar rejection.

## Evidence

The dedicated workflow runs the focused suite and compiles all observer modules and CLIs. The contract permanently sets `research_only=true`, `rankable=false`, `executable=false`, `execution_allowed=false`, `allowed_for_live_execution=false`, `broker_api_called=false`, and `is_order_action=false`.

## Risks

The observer is not yet wired to a completed-candle callback in a real market session. Startup history availability, market-hours sequencing, restart reconciliation, session-end outcome completion, and evidence sealing remain unproven live.

## Remaining proof

One real market-hours shadow run must produce `PASS_LIVE_SHADOW_RUN`, zero duplicate event IDs, zero authority violations, restart-safe reconciliation, clean shutdown, and complete due outcomes.

## What this PR does not prove

This PR does not prove a structural edge, future profitability, option profitability, executable fills, live trading readiness, or eligibility for ranking or execution. It proves only that the prospective observer implementation is causally testable and permanently read-only.

## Next PR

No production-integration PR is allowed unless the frozen observer first collects the required genuinely new signals and passes the prospective statistical gate. Any later promotion must be separately scoped and reviewed.

## Human approval

Keep the PR draft and unmerged until all repository checks pass and one live shadow session passes the integration verifier. Human approval remains mandatory.
