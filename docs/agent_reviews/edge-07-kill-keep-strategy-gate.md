mode: REVIEW
candidate_id: EDGE-07-KILL-KEEP-STRATEGY-GATE
decision: add_kill_keep_strategy_gate
reason: Add a deterministic expectancy gate that can only tighten lifecycle state so weak or unproven setups do not become executable.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge-07-kill-keep-strategy-gate.md

# Agent Work Contract

## Scope Guard
- This PR only adds a read-only expectancy gate and narrow review-queue integration.
- No broker, order, strategy, ranking, UI, websocket, or feed lifecycle changes are allowed.
- The gate may only make lifecycle state stricter.

## Grill Me Review
- The gate must fail closed when expectancy evidence is missing or weak.
- KEEP must never bypass fallback, stale feed, or other existing hard safety gates.
- Manual override evidence must be logged and never relax hard safety.

## Hermes Review
- The gate consumes expectancy status and maps it to stricter lifecycle constraints.
- KILL and INSUFFICIENT_DATA are advisory-blocking states, not execution approvals.
- KEEP is permissive only in the sense that it does not add a new restriction.

## GSD Review
- Files touched are limited to the expectancy gate helper, a narrow review-queue hook, tests, and this review doc.
- No runtime trading behavior is loosened.

## QA / Safety Review
- Read-only proof only.
- `is_order_action: false`
- `broker_api_called: false`
- `read_only: true`
- `append: false`
- No live orders, no broker calls, no runtime mutation beyond lifecycle restriction.

## Acceptance Proof
- KILL cannot become executable.
- INSUFFICIENT_DATA cannot become executable.
- WATCH becomes queue-only/advisory.
- KEEP passes through unchanged if otherwise eligible.
- Fallback and stale feed remain blocked even when expectancy says KEEP.
- Missing lookup defaults to safe INSUFFICIENT_DATA behavior.

## Runtime Proof Required After Merge
- Confirm expectancy gate fields are emitted on rows that include expectancy evidence.
- Confirm review_queue applies the gate only when expectancy evidence is attached.
- Confirm fallback and feed truth gates still dominate when they are stricter.

## What This PR Does Not Prove
- It does not prove strategy edge.
- It does not change ranking formulas.
- It does not make weak setups profitable.

## Human Approval
- This gate is conservative by design.
- Any future attempt to relax safety or to make the gate auto-promote rows requires a separate approved PR.


## Agent Work Contract

N/A

## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
