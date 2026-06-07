mode: REVIEW
candidate_id: EDGE-08-EXPECTANCY-BASED-RANKING-ENGINE
decision: add_expectancy_based_ranking_engine
reason: Add a deterministic edge ranking layer that uses historical expectancy while preserving the existing rank_score contract and all hard safety gates.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge-08-expectancy-based-ranking-engine.md

# Agent Work Contract

## Scope Guard
- This PR only adds an additive edge ranking contract and narrow review-queue wiring.
- No broker, order, strategy, UI, websocket, or feed lifecycle changes are allowed.
- The existing `rank_score` contract must remain intact and untouched.

## Grill Me Review
- The edge rank must fail closed when expectancy is missing, weak, or blocked by fallback/feed truth.
- KEEP may improve the edge rank, but it must never bypass fallback, stale feed, or other hard safety gates.
- The new score must be additive only and must not replace the existing ranking selector.

## Hermes Review
- The edge rank combines expectancy evidence with existing execution/ranking quality.
- KILL rows get zero edge rank and stay non-executable.
- INSUFFICIENT_DATA and WATCH rows remain capped and advisory.
- KEEP can be ranked normally only when the rest of the lifecycle is already safe.

## GSD Review
- Files touched are limited to the edge ranking helper, narrow review-queue wiring, focused tests, and this review doc.
- `rank_score` is preserved as the existing contract field.
- No selector rewrite or upstream strategy change is introduced.

## QA / Safety Review
- Read-only proof only.
- `is_order_action: false`
- `broker_api_called: false`
- `read_only: true`
- `append: false`
- No live orders, no broker calls, no runtime mutation beyond additive ranking metadata.

## Acceptance Proof
- KEEP positive expectancy candidates receive a high `edge_rank_score`.
- KILL candidates receive zero edge rank and remain non-executable.
- INSUFFICIENT_DATA and WATCH candidates are capped.
- Fallback and stale-feed candidates cannot rank executable.
- Lower-confidence proven-positive expectancy outranks higher-confidence unproven expectancy.
- Existing `rank_score` remains preserved.

## Runtime Proof Required After Merge
- Confirm edge rank fields are emitted on review-queue rows after expectancy handling.
- Confirm blocked lifecycle rows still stay blocked even when the edge rank helper runs.
- Confirm the existing ranking selector still uses the unchanged `rank_score` contract.

## What This PR Does Not Prove
- It does not prove strategy edge.
- It does not rewrite ranking order selection.
- It does not make weak setups profitable.

## Human Approval
- This contract is conservative by design.
- Any future attempt to replace the existing rank selector with edge rank requires a separate approved PR.
