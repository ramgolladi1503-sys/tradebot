# Canonical Feed Runtime Snapshot Truth

mode: REVIEW
candidate_id: PR-CANONICAL-FEED-RUNTIME-SNAPSHOT-TRUTH
decision: add_canonical_feed_runtime_snapshot_truth
reason: Normalize feed/runtime snapshot mirrors so blocked feed truth cannot appear partially OK in one artifact and blocked in another, without changing runtime behavior, strategy, ranking, Phase2, broker, or dashboard code.
timestamp: 2026-06-06T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/canonical-feed-runtime-snapshot-truth.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (read-only runtime snapshot normalization + deterministic regression tests + review doc)
title: Canonical Feed Runtime Snapshot Truth
scope: make feed/runtime truth serialize consistently across all runtime snapshot mirrors so blocked feed state cannot appear partially OK in one file and correctly blocked in another
requested_paths:
  - core/feed/runtime_store.py
  - core/kite_depth_ws.py
  - tests/test_feed_runtime_states.py
  - tests/test_feed_truth_contract.py
  - docs/agent_reviews/canonical-feed-runtime-snapshot-truth.md
allowed_paths:
  - core/feed/runtime_store.py
  - core/kite_depth_ws.py
  - tests/test_feed_runtime_states.py
  - tests/test_feed_truth_contract.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/broker*
  - core/order*
  - strategies/*
  - core/runtime_execution_truth.py
  - core/orchestrator.py
  - core/review_queue.py
  - dashboard/*
  - runtime/live*
  - logs/*
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_feed_runtime_states.py -vv
  - PYTHONPATH=. pytest -q tests/test_feed_truth_contract.py -vv
  - git diff --check
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr492_changed_paths.txt
acceptance_proof:
  - all feed runtime mirrors share the same blocked truth fields
  - blocked snapshots never report executable candidates as allowed
  - healthy snapshots still report executable truth as allowed
  - no broker/order, strategy, ranking, or Phase2 behavior changes
```

## Scope Guard

- This PR is off-market and read-only.
- It must not change live runtime behavior, broker calls, order behavior, strategy logic, ranking math, or Phase 2 selection.
- It must fail closed for blocked feed truth and keep evidence explicit.

## Grill Me Review

- Blocked snapshots must not serialize `OK` option block reasons while the feed is dead or recovery-blocked.
- Canonical truth must be identical across all mirror files.
- The fix must not mask stale-feed or terminal restart conditions.

## Hermes Review

- The canonicalizer belongs at the snapshot boundary, not in downstream candidate logic.
- Runtime evidence should remain observable and reversible.
- Shared normalization avoids split-brain artifact consumers.

## GSD Review

- Code changes are limited to snapshot serialization and regression tests.
- No runtime execution path, broker adapter, or strategy selection code is changed.

## QA / Safety Review

- `read_only=true`, `append=false`, `is_order_action=false`, and `broker_api_called=false` remain enforced.
- Blocked snapshots must still preserve evidence like restart-block reasons and token counts.
- Healthy snapshots must still be able to report `feed_truth_allows_executable_candidates=true`.

## High-Risk Path Review

- `core/kite_depth_ws.py` is a high-risk feed/WebSocket lifecycle path, so this PR keeps the change boundary narrow and snapshot-only.
- The patch does not alter reconnect decisions, subscription policy, strategy logic, ranking math, Phase 2, broker behavior, or order behavior.
- The fix only normalizes serialized feed/runtime truth so mirror artifacts cannot disagree on blocked vs executable state.

## Acceptance Proof

- `.runtime/logs/feed_runtime_latest.json`, `.runtime/feed_runtime_latest.json`, and `logs/feed_runtime_latest.json` agree on blocked truth.
- Blocked mirrors never emit `feed_truth_allows_executable_candidates=null`.
- Blocked mirrors never emit `option_feed_block_reason_by_symbol=OK` for symbols in a dead/recovery-blocked snapshot.
- Healthy mirrors continue to emit `feed_truth_allows_executable_candidates=true`.

## Runtime Proof Required After Merge

- Run the live feed/runtime session that produced the split-brain evidence and confirm all mirrors agree.
- Confirm the terminal WS1006 path still fails closed and does not reintroduce the old restart storm.

## What This PR Does Not Prove

- It does not prove trading edge, profitability, or strategy quality.
- It does not change execution truth classification for top candidates.
- It does not authorize any live order or broker activity.

## Human Approval

This is safe to review as a narrow snapshot-truth normalization patch.
