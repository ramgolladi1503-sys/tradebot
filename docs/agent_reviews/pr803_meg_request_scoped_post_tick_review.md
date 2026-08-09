# PR #803 — MEG Request-Scoped Post-Tick Review

producer_commit_sha: `b02b8436a4615103703126036a75a5d6b6eb2a9e`
base_commit_sha: `69825050936de4c4bd329949fdc205f7fddca028`
decision: governance evidence for pre-live observation review; live evidence pending
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
allowed_for_paper_execution: false
broker_write_authority: false
live_authorized: false

## Agent Work Contract

source_agent: Codex
action: REVIEW_PR_AND_REPAIR_GOVERNANCE_EVIDENCE
title: PR #803 MEG request-scoped post-tick review
scope: Add the missing truthful review artifact required by the repository governance gate. Do not alter runtime behavior or launch a market session.
requested_paths: `docs/agent_reviews/pr803_meg_request_scoped_post_tick_review.md`
allowed_paths: `docs/agent_reviews/pr803_meg_request_scoped_post_tick_review.md`
forbidden_paths: broker/order APIs; strategy, ranking, threshold, capital, risk, execution, feed, MEG semantics, authorization, credentials, and runtime evidence
expected_tests: repository agent-review validator and focused PR #803 lifecycle/bridge tests
acceptance_proof: This document records the exact candidate SHA and explicitly leaves live proof pending.

## Scope Guard

The reviewed implementation delta from #786 (`69825050936de4c4bd329949fdc205f7fddca028`) to #803 changes only `core/kite_depth_ws.py`, `core/market_event_graph_live_runtime_bridge.py`, and their two focused tests. It is limited to request-scoped post-subscription tick evidence. No strategy, graph, ranking, allocation, risk, broker, execution, order, or authorization semantics are changed. This governance repair changes no runtime code.

## Grill Me Review

- This document does not claim live success; the next governed market-hours observation is pending.
- Focused tests prove implementation compatibility only, not live feed, persistence, or market-session behavior.
- Request-scoped evidence must not fall back to the session-first tick.
- Wrong-session, wrong-generation, and wrong-symbol evidence must be rejected.

## Hermes Review

The repair preserves the boundary between a feed session's first tick and the first tick causally attributable to a specific subscription request. Request ID, request generation, feed session, reconnect generation, tick identity, and symbol/token provenance must remain linked through receipt, bridge selection, and persistence. No authority is inferred from non-executable evidence.

## GSD Review

Implementation scope is governance-only: add this review artifact and run the repository validator plus narrow relevant suites. If a reproducible functional defect is found, stop and report it before changing runtime code. Do not start a live session while the market is closed.

## QA / Safety Review

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
allowed_for_paper_execution=false
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
```

No order placement, modification, cancellation, exit, broker write, paper authorization, or live authorization is permitted by this review.

## High-Risk Path Review

- `core/kite_depth_ws.py`: subscription-request lifecycle, request ID/generation, feed session identity, reconnect generation identity, tick identity, and symbol/token provenance must be explicit and fail closed.
- `core/market_event_graph_live_runtime_bridge.py`: post-request causal timing, selected-tick provenance, wrong-generation/wrong-symbol rejection, and persistence reconciliation must not substitute stale or unrelated evidence.

The observation must preserve request-scoped first post-request tick epoch, request ID, request generation, first/selected post-request tick IDs, callback row/token provenance, session identity, and reconnect generation. MEG traversal/export ledgers, authority snapshots, append-only persistence, producer/consumer reconciliation, canonical sealing, manifests, SHA256SUMS, and `SEALED` integrity remain separate evidence obligations.

## Acceptance Proof

Pending until run on the final candidate SHA. Required proof includes the Agent Review Evidence gate, focused lifecycle/bridge tests, compile/import validation, diff-check validation, and inspection of inherited observation, persistence, sealing, and read-only safety paths. No result is pre-asserted here.

## Runtime Proof Required After Merge

A governed market-hours observation must independently prove actual Kite connection, NIFTY and frozen constituent coverage, FULL packets, request/tick causal identity, MEG bars/traversals/exports, persistence drain/reconciliation, authority snapshots, controlled shutdown, immutable evidence root, manifest, SHA256SUMS, and SEALED integrity. Runtime proof is pending.

## What This PR Does Not Prove

- It does not prove a live market session occurred, feed readiness, constituent coverage, persistence completeness, or sealed evidence integrity.
- It does not certify the MEG edge, options edge, paper trading, shadow trading, live trading, broker writes, orders, or PR #805 lockbox admission.
- It does not authorize any order action.

## Human Approval

Human approval is required before any market-hours observation launch. This artifact is governance evidence only; it is not approval to run, trade, or modify broker state.
