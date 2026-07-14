mode: REVIEW
candidate_id: EDGE-09-TOP-OPPORTUNITY-SELECTOR
decision: add_top_opportunity_selector
reason: Add a read-only top opportunity selector report from edge-ranked candidates without changing execution behavior or dashboard selection logic.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge-09-top-opportunity-selector.md

# Agent Work Contract

## Scope Guard
- This PR only adds a read-only selector/report over edge-ranked candidates.
- No broker, order, strategy, UI, websocket, or feed lifecycle changes are allowed.
- The selector is observational and must not change execution behavior.

## Grill Me Review
- The selector must fail closed when rows are fallback, blocked, stale, or KILL.
- Executable rows must be a strict subset of KEEP + executable + non-fallback + non-blocked rows.
- The report must not imply that advisory, shadow, or rejected rows are executable.

## Hermes Review
- The selector is a deterministic report layer over already-ranked rows.
- WATCH rows are advisory.
- INSUFFICIENT_DATA rows are shadow/paper.
- KILL, fallback, and blocked rows remain in rejected/debug evidence.

## GSD Review
- Files touched are limited to the selector helper, tests, and this review doc.
- No execution selector rewrite or runtime trading behavior change is introduced.
- The selector consumes already-ranked evidence only.

## QA / Safety Review
- Read-only proof only.
- `is_order_action: false`
- `broker_api_called: false`
- `read_only: true`
- `append: false`
- No live orders, no broker calls, no runtime mutation beyond report generation.

## Acceptance Proof
- Executable section contains only KEEP + executable + non-fallback + non-blocked candidates.
- WATCH appears in advisory.
- INSUFFICIENT_DATA appears in shadow/paper.
- KILL is excluded from executable and shown in rejected/debug.
- Fallback and stale/feed-blocked rows are excluded from executable.
- Rows are sorted deterministically by edge rank score.

## Runtime Proof Required After Merge
- Confirm the JSON and Markdown artifacts are written under `.runtime/opportunities/`.
- Confirm the selector reports executable/advisory/shadow/rejected counts.
- Confirm why-ranked and why-not-ranked text explain the selection and exclusion rationale.

## What This PR Does Not Prove
- It does not prove strategy edge.
- It does not replace the existing execution selector.
- It does not change dashboard behavior or live order routing.

## Human Approval
- This contract is conservative by design.
- Any future attempt to make the selector drive execution requires a separate approved PR.


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
