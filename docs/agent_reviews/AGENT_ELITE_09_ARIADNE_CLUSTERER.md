# AGENT-ELITE-09 — Ariadne CI/Test Failure Clusterer

mode: REVIEW
candidate_id: AGENT-ELITE-09-ARIADNE-CI-TEST-FAILURE-CLUSTERER
decision: review_pending
reason: ariadne_static_failure_clustering
source: docs/agent_reviews/AGENT_ELITE_09_ARIADNE_CLUSTERER.md
timestamp: 2026-05-28T18:35:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

Issue: #381
Parent: #372
Depends on: #380 / PR #396 / merge commit 38136fa6dc98f30aa1510c32e8f3f0acf4cb77f8

## Agent Work Contract

This PR implements AGENT-ELITE-09 only.

The work adds a static Ariadne failure clusterer that groups pytest and CI failure text by proof-backed root-cause signals before any remediation contract is allowed.

It must not run product runtime code, call brokers, modify broker code, change strategy/ranking formulas, change dashboard/UI behavior, create PRs, auto-fix code, or call external agents.

## Scope Guard

Allowed:

- Add `tools/code_excellence/ariadne/`.
- Add focused tests in `tests/test_ariadne_failure_clustering.py`.
- Add Ariadne docs in `docs/code_excellence/ariadne/`.
- Add this agent-review evidence file.

Not allowed:

- Runtime execution.
- Broker calls.
- Broker code changes.
- Strategy/ranking formula changes.
- Dashboard/UI changes.
- Auto-fix behavior.
- PR creation behavior from Ariadne.
- External agent calls.
- Test skip/xfail.

## High-Risk Path Review

This PR adds isolated static code-excellence tooling only.

High-risk Tradebot paths intentionally unchanged:

- `core/kite_client.py`
- `core/execution_engine.py`
- `core/execution_router.py`
- `core/risk_engine.py`
- `core/orchestrator.py`
- `strategies/`
- `dashboard/`
- `config/`

## Grill Me Review

Question: Does this fix failed tests?

Answer: No. It clusters failure text by likely root cause so future fixes target causes rather than symptoms.

Question: Does this create PRs or patches?

Answer: No. Ariadne only emits clusters and optional fix-contract permission. It does not mutate code.

Question: What happens when confidence is low?

Answer: The cluster is marked UNKNOWN.

Question: What happens when a cluster has no proof?

Answer: Fix-contract creation is blocked.

Question: Does this call any external AI or service?

Answer: No. The parser is static and local.

## Hermes Review

The implementation is intentionally additive:

- Adds `FailureSignal`, `FailureCluster`, `FailureClusterReport`, and `FixContract`.
- Parses pytest and CI failure text into per-failure signals.
- Clusters by fixture and schema-field drift.
- Clusters by safety boundary and runtime flow step.
- Clusters by ranking/candidate concept, normalized error text, and module fallback.
- Emits confidence as `CONFIRMED`, `LIKELY`, or `UNKNOWN`.
- Blocks fix contracts when proof is absent.

## GSD Review

Smallest safe implementation:

- Keep Ariadne isolated under `tools/code_excellence/ariadne/`.
- No integration into CI gates yet.
- No remediation planner behavior.
- No repo mutation behavior.
- Deterministic pure parsing tests only.

Files changed:

- `tools/code_excellence/ariadne/__init__.py`
- `tools/code_excellence/ariadne/clusterer.py`
- `tests/test_ariadne_failure_clustering.py`
- `docs/code_excellence/ariadne/FAILURE_CLUSTERING.md`
- `docs/agent_reviews/AGENT_ELITE_09_ARIADNE_CLUSTERER.md`

## QA / Safety Review

Focused command:

```bash
PYTHONPATH=. pytest tests/test_ariadne_failure_clustering.py -q
```

Safety assertions:

- No runtime import of target Tradebot modules.
- No broker calls.
- No order behavior.
- No live execution.
- No dashboard behavior change.
- Broker code is untouched.
- Strategy/ranking formulas are untouched.
- No PR creation or auto-fix path exists.

## Acceptance Proof

The tests prove:

- Four failures from the same fixture drift are grouped into one cluster.
- Unrelated failures are separated into distinct clusters.
- Low-confidence failures are marked UNKNOWN.
- A cluster without proof cannot produce an allowed fix contract.
- A proof-backed cluster can produce an allowed fix contract.

## Runtime Proof Required After Merge

No live runtime proof is required for this PR. This is static code-excellence analysis only.

## What This PR Does Not Prove

- Does not prove live startup succeeds.
- Does not prove candidate quality.
- Does not prove ranking formula quality.
- Does not prove broker readiness.
- Does not prove profitability.
- Does not prove dashboard accuracy.
- Does not validate dynamic runtime dispatch.

## Human Approval

Required before merge.
