# Agent Review — EDGE-70 Candidate Normalization and Dedup Contract

## Agent Work Contract

- PR: EDGE-70 — Candidate Normalization and Dedup Contract
- Scope: read-only normalization and deduplication for EDGE-69 candidate metadata
- Runtime behavior changed: no
- Broker behavior changed: no
- Order behavior changed: no
- Dashboard behavior changed: no
- Strategy execution changed: no
- Ranking behavior changed: no
- Scoring behavior changed: no

## Evidence Contract Fields

```yaml
mode: PAPER
candidate_id: EDGE_70_CANDIDATE_NORMALIZATION_DEDUP
message_decision: CANDIDATE_NORMALIZATION_DEDUP
decision: CANDIDATE_NORMALIZATION_DEDUP
reason: Adds deterministic candidate normalization and duplicate rejection before any future ranking work.
timestamp: 2026-05-25T16:40:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge_70_candidate_normalization_dedup.md
```

## Grill Me Review

Challenge: Did this introduce ranking under another name?

Answer: No. The normalizer only canonicalizes identity and rejects duplicates or malformed candidates. It does not assign score, priority, confidence, rank, edge, or capital.

Challenge: Can duplicate candidates survive?

Answer: No. Canonical identity uses `strategy_id:instrument:direction:regime`. The first valid candidate is preserved and later candidates with the same canonical key are rejected.

Challenge: Can invalid EDGE-69 pool output pass through?

Answer: No. Invalid pool reports produce an invalid normalization report with zero normalized candidates.

Challenge: Can malformed payloads silently disappear?

Answer: No. Malformed candidates are returned in `rejected_candidates` with explicit blockers.

## Hermes Review

- Canonical IDs are deterministic and JSON serializable.
- Report and row payloads preserve read-only and non-action fields.
- Rejections are explicit and inspectable.
- Normalized output is sorted by canonical candidate ID for stable snapshots.
- The module consumes EDGE-69 metadata only.

## GSD Review

- Smallest useful step: normalize and deduplicate candidate identities only.
- No overengineering: no scorer, no ranker, no runtime writer, no strategy plugin loader, no dashboard panel.
- No unrelated cleanup.
- Tests cover canonical ID stability, read-only payloads, duplicate rejection, malformed candidate rejection, empty input, invalid pool fail-closed behavior, and metadata-only behavior.

## QA / Safety Review

- Safety boundary: normalization is read-only evidence only.
- Broker boundary: no broker APIs, no live calls, and no broker payload generation.
- Strategy boundary: no strategy modules are imported and no strategy callables are invoked.
- Runtime boundary: no runtime files are written and no runtime decision behavior changes.
- Failure handling: empty input and invalid pool fail closed; malformed rows are rejected.
- Test safety: tests use metadata-only specs and EDGE-69 candidate pool output.

## Scope Guard

This PR must not:

- modify strategy implementations
- wire runtime strategy selection
- call strategy functions
- rank candidates
- score candidates
- allocate capital
- call broker APIs
- add dashboard UI
- mutate runtime artifacts
- weaken existing tests

## Acceptance Proof

```bash
PYTHONPATH=. python -m pytest tests/test_edge_70_candidate_normalization_dedup.py tests/test_edge_69_strategy_candidate_pool.py tests/test_edge_68_strategy_eligibility.py
```

## Runtime Proof Required After Merge

No runtime proof is required for EDGE-70 because this PR is not wired into runtime execution.

Future runtime proof is required only when a later scoped PR reads normalized candidates from runtime, ranking, or dashboard code. That proof must show:

- read-only usage only
- no strategy execution from candidate descriptors
- no broker calls
- no order actions
- no mutation of runtime decision artifacts

## What This PR Does Not Prove

- Strategy profitability
- Strategy expectancy
- Regime-specific edge
- Signal quality
- Candidate ranking quality
- Paper/live trading readiness
- Dashboard usability
- Broker/order safety beyond preserving non-action metadata

## Human Approval

Ready for review after CI passes.
