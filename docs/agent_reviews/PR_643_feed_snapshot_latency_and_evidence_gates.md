# PR-643 — Feed Snapshot Latency and Evidence Gates

mode: REVIEW
candidate_id: PR-643-FEED-SNAPSHOT-LATENCY-AND-EVIDENCE-GATES
decision: review_pending
reason: feed_snapshot_latency_and_evidence_gates
source: docs/agent_reviews/PR_643_feed_snapshot_latency_and_evidence_gates.md
timestamp: 2026-07-10T00:00:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

This PR is limited to feed snapshot latency hardening, runtime cycle truth reuse, and PR evidence output clarity.

It must not place orders, call broker APIs, weaken feed freshness gates, weaken risk gates, or broaden runtime behavior beyond the scoped snapshot and evidence paths.

## Scope Guard

Allowed:

- Update `core/events.py` for bounded atomic write deduplication.
- Update `core/runtime_snapshot_producer.py`, `core/runtime_snapshot_store.py`, `core/ranking_orchestrator.py`, and `core/candidate_ranking.py` for cycle truth reuse and timing metrics.
- Add `core/runtime_cycle_context.py` and `core/runtime_snapshot_stages.py`.
- Update `tools/code_excellence/pr_evidence_pack.py` and its focused test.
- Update focused snapshot/ranking tests.
- Add this agent review evidence file.

Not allowed:

- Broker calls.
- Live order actions.
- Feed freshness relaxation.
- Risk gate relaxation.
- Strategy threshold changes.
- Dashboard behavior changes.
- Hidden fallbacks that mask broken feed data.

## High-Risk Path Review

High-risk Tradebot paths touched in this PR are intentionally scoped and fail closed:

- `config/config.py`
- `core/candidate_ranking.py`
- `core/events.py`
- `core/observability/metrics.py`
- `core/ranking_orchestrator.py`
- `core/runtime_feed_truth_snapshot.py`
- `core/runtime_snapshot_producer.py`
- `core/runtime_snapshot_store.py`

These paths only change snapshot reuse, bounded reads, deduplicated writes, timing metrics, and truth propagation. No broker, execution, or live order action path is introduced.

## Grill Me Review

Question: Does this PR reduce freshness by caching the wrong truth?

Answer: No. The cache is per cycle and immutable for the cycle. It is passed through to downstream ranking instead of recomputed.

Question: Does this PR hide broken feed data?

Answer: No. The feed truth snapshot still fails closed on invalid or stale data.

Question: Does this PR weaken evidence review?

Answer: No. It adds explicit agent-review and CE gate wording to the PR evidence pack.

## Hermes Review

The implementation is constrained to the existing snapshot/evidence path.

The new cycle context is a transport object, not a runtime policy change.

The new PR evidence text does not alter execution behavior.

## GSD Review

Files changed are limited to the scoped feed truth, ranking, observability, and evidence pack files plus focused tests.

## QA / Safety Review

Targeted validation:

```bash
PYTHONPATH=. pytest -q tests/test_code_excellence_pr_evidence_pack.py tests/test_code_excellence_unified_gate_runner.py tests/test_repo_forensics_agent_evidence.py tests/test_runtime_snapshot_producer_metrics.py tests/test_runtime_snapshot_producer_tail.py tests/core/test_runtime_snapshot_store.py tests/test_ranking_orchestrator.py
```

Safety assertions:

- No broker calls.
- No live order actions.
- No runtime mutation outside the scoped snapshot/evidence paths.
- No feed freshness bypass.

## Acceptance Proof

This PR is accepted only if:

- focused tests pass,
- the agent review evidence file is present,
- the PR evidence pack explicitly names the agent review gate and code excellence gates,
- CI passes on the clean PR branch.

## Runtime Proof Required After Merge

No extra runtime proof is required beyond the existing snapshot/ranking tests and the CI gate outputs.

## What This PR Does Not Prove

- Does not prove live broker safety.
- Does not prove profitability.
- Does not prove all unrelated dirty worktree changes are safe.
- Does not prove strategy correctness outside the touched snapshot/ranking path.

## Human Approval

Required before merge.
