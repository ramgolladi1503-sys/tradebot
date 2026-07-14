# PR #527 — Candidate Lifecycle Snapshot

mode: PAPER
candidate_id: pr527-candidate-lifecycle-snapshot
signal_id: pr527-candidate-lifecycle-snapshot
strategy_id: candidate_pool_lifecycle
decision: REVIEW_ONLY
reason: read_only_candidate_lifecycle_evidence_contract_added
timestamp: 2026-06-08T14:50:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr527-candidate-lifecycle-snapshot.md

## Agent Work Contract

This PR adds a read-only candidate lifecycle snapshot layer to join existing candidate-pipeline reports into one canonical per-candidate view.

The work is intentionally limited to candidate evidence composition. It does not alter strategy generation, scoring formulas, ranking behavior, feed behavior, broker behavior, dashboard behavior, execution gates, or runtime wiring.

## Scope Guard

In scope:

- Add `CandidateLifecycleSnapshot`.
- Add `build_candidate_lifecycle_snapshots(...)`.
- Add `CandidatePool.lifecycle_snapshots(...)`.
- Join existing report outputs by `strategy_id`.
- Preserve read-only, non-order, non-broker behavior.
- Add focused tests for lifecycle joining, fallback blocking, absent-report conservatism, and serialization safety.

Out of scope:

- No broker calls.
- No order actions.
- No live execution behavior.
- No scoring formula changes.
- No ranking behavior changes.
- No feed or depth subscription changes.
- No dashboard or UI wiring.
- No strategy generation changes.

## Grill Me Review

The main risk is pretending this snapshot creates new truth. It does not. It only composes truth already produced by candidate, classifier, downgrade, scoring, and ranking reports.

The second risk is leaking fallback or stale candidates into execution-safe state. The implementation explicitly blocks suppressed candidates before selector bucket promotion can mark anything selected.

The third risk is accepting weak tests. The tests avoid shape-only proof by checking exact lifecycle state, capability, bucket, score, rank, safety serialization, and fallback downgrade details.

## Hermes Review

Task boundary stayed narrow.

Changed files:

- `core/candidate_pool.py`
- `tests/test_candidate_pool.py`
- `docs/agent_reviews/pr527-candidate-lifecycle-snapshot.md`

The PR is one lifecycle/evidence step only. It does not start PR 2, does not clean unrelated architecture, and does not add dashboard/runtime wiring.

## GSD Review

This is useful because current candidate truth is fragmented across separate reports. A lifecycle snapshot gives downstream selector/UI/RCA work one stable object that answers where the candidate is in the pipeline and why.

The implementation favors deterministic joins and conservative defaults. Absent downstream reports do not create score, rank, classification, or execution safety.

## QA / Safety Review

Safety properties covered:

- Snapshot serialization is `read_only=True`.
- Snapshot serialization is `append=False`.
- Snapshot serialization is `is_order_action=False`.
- Snapshot serialization is `broker_api_called=False`.
- Snapshot serialization is `live_order_action=False`.
- Snapshot serialization is `broker_order_action=False`.
- Fallback candidates with `FALLBACK_QUOTE_ONLY` remain blocked even when a selector bucket says executable.
- Absent downstream reports keep a raw candidate at `INTENT_CREATED` and `DISPLAY_SAFE` only.

No high-risk path review is required because this PR does not change config, auth, feed/WebSocket, orchestrator, execution, risk, or strategies.

## Acceptance Proof

Focused command:

```bash
PYTHONPATH=. pytest tests/test_candidate_pool.py
```

Expected proof:

- Candidate pool existing behavior remains covered.
- Lifecycle snapshot joins classifier, downgrade, score, rank, and selector bucket outputs.
- Fallback candidate cannot become execution-safe.
- Absent downstream reports do not invent score/rank/truth.
- Serialization safety flags remain false for order and broker actions.

CI gates to satisfy:

- Agent Review Evidence Gate.
- Code Excellence Gates / Minerva / Evidence.
- Existing unit test workflows.

## Runtime Proof Required After Merge

No runtime proof is required to validate broker/feed behavior because this PR does not wire the snapshot into runtime execution, broker calls, feed subscriptions, dashboard, or order paths.

After merge, future runtime proof is only needed when PR 4 or later consumes lifecycle snapshots in top opportunity selection or UI/runtime paths.

## What This PR Does Not Prove

This PR does not prove trading edge.

It does not prove candidate generation quality.

It does not prove ranking is profitable.

It does not prove feed recovery.

It does not prove execution readiness.

It only proves a deterministic, read-only candidate lifecycle evidence view can be produced from existing reports without inventing downstream truth.

## Human Approval

Human approval is required before merge.

Do not merge only because the PR is green. Review the lifecycle contract and confirm that it stays read-only and does not quietly become a new execution or runtime gate.


## High-Risk Path Review

N/A
