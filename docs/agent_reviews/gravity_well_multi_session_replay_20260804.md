# Agent Review — Gravity-Well Multi-Session Replay Update (2026-08-04)

## Agent Work Contract

Audit the uploaded `kite_candidate_replay(11).zip`, preserve source lineage, execute only a predeclared price-only diagnostic when the full mechanism fails its data-authority gate, keep holdout sealed, and update draft PR #785 without changing production behavior.

## Scope Guard

This update is evidence-only. Permitted changes are the research result, multi-session manifest, frozen diagnostic specification, compact evidence report and review record. Production strategy, runtime, ranking, risk, broker, order, dashboard and execution paths remain prohibited.

## Grill Me Review

The archive contains many sessions, but session count alone does not make it certification-grade. Every underlying volume value is zero, no constituents exist, and all 30 option files are explicitly `OPT_MOCK` without expiry, strike, CE/PE or immutable contract identity. Treating those files as option truth would be fabricated evidence.

## Hermes Review

The diagnostic uses completed five-minute bars, prior-completed 15-minute and 30-minute levels, next-bar entry, no cross-session outcomes and a chronological 295/99/99 split. The primary full mechanism remains fail-closed before outcomes because its required inputs are absent.

## GSD Review

The work stayed within a frozen EMA-centre proxy with one canonical length and two predeclared neighbours. No profitability grid search was performed. No validation survivor existed, so the holdout was not opened and no further hypothesis mutation is justified on this corpus.

## QA / Safety Review

- source ZIP SHA-256: `f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d`;
- 1,509/1,509 Parquet files parsed with zero failures;
- 493 independent NIFTY sessions and 36,849 completed five-minute rows;
- underlying authority flags: zero synthetic, fallback and mock rows;
- nonzero underlying-volume rows: zero;
- NIFTY constituent rows: zero;
- all option paths explicitly mock-named and contract identity absent;
- 10/10 causal and integrity checks passed;
- no broker call, order action, paper authority or live authority.

## Acceptance Proof

Escape acceptance failed at `-3.49 bps` after 2 bps costs with PF `0.39` and a wholly negative session-bootstrap interval. Cluster break failed at `-3.96 bps`. Failed escape produced only seven validation trades and collapsed under severe costs, winner/session removal and both neighbouring centre lengths. All predeclared baselines were negative. Deterministic reruns produced byte-identical event-ledger and certification hashes.

## Runtime Proof Required After Merge

No runtime proof applies to this evidence-only draft because no runtime path is changed and the PR should remain unmerged. A future promotion would require a separate real-data shadow proof with constituents, authoritative option contracts and execution-grade quote truth.

## What This PR Does Not Prove

It does not prove the complete volume-weighted Gravity-Well plus participation mechanism has no edge. It does not establish option profitability, expiry behavior, real fills, slippage, production readiness, structural edge or incremental value over the existing Market Event Graph.

## Human Approval

The user approved continuing the research and repository evidence update. Human approval to merge, register or trade the mechanism has not been granted.

## Final Review Verdict

```text
DATA_BLOCKED_MISSING_VOLUME_CONSTITUENTS_AND_REAL_OPTIONS
NO_PRICE_ONLY_VALIDATION_SURVIVOR
HOLDOUT_SEALED
NO_STRATEGY_INTEGRATION
```

mode: RESEARCH
candidate_id: GRAVITY_WELL_MULTI_SESSION_REPLAY_20260804
decision: FAIL_CLOSED
reason: Full mechanism data absent and no price-only validation survivor.
timestamp: 2026-08-04T14:19:00+05:30
is_order_action: false
broker_api_called: false
source: agent
