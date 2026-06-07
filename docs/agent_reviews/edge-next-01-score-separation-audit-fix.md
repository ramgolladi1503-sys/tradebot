mode: REVIEW
candidate_id: EDGE-NEXT-01-SCORE-SEPARATION-AUDIT-FIX
decision: improve_score_separation
reason: Tighten ranking separation for strong, weak, fallback, duplicate, regime-mismatched, and low-liquidity candidates without changing broker, live order, strategy, or dashboard behavior.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge-next-01-score-separation-audit-fix.md

# Agent Work Contract

## Scope Guard
- This PR only changes score separation and ranking penalties where existing evidence already exists.
- It does not add live trading behavior, broker calls, order actions, or strategy logic.
- It does not relax any fallback, stale-feed, or safety gate.

## Grill Me Review
- The current scoring stack is heuristic and can cluster candidates when it does not consume explicit regime alignment or crowding evidence.
- Duplicates and correlated candidates need an explicit penalty path so the top ranks do not overrepresent the same idea.
- Wide-spread and weak-liquidity candidates should be separated more aggressively than they are by the legacy neutral defaults.

## Hermes Review
- Add explicit score components for crowding and explicit regime alignment where the candidate already carries that evidence.
- Preserve read-only contracts and existing rank score fields.
- Keep edge ranking deterministic by preserving existing tie-breaking behavior.

## GSD Review
- Implement only additive scoring and ranking changes.
- Add tests for score separation, duplicate/correlated penalty, regime mismatch, and deterministic tie resolution.
- Verify no broker/order imports are introduced.

## QA / Safety Review
- Fallback/recovered candidates must remain non-executable.
- Missing inputs must degrade score, not invent confidence.
- No hidden auto-promotion should be introduced.
- Existing fallback, expectancy, and review-queue safety tests must stay green.

## Acceptance Proof
- `candidate_scoring` shows a clearer gap between strong and weak candidates.
- `edge_ranking` shows lower scores for duplicate/correlated and regime-mismatched candidates.
- `top_opportunity_selector` remains deterministic on score ties.
- `review_queue` fallback protections still pass unchanged.

## Runtime Proof Required After Merge
- No runtime proof is required for this PR because it is a static scoring and ranking change only.
- The repo still requires CI and deterministic regression tests to validate the behavior.

## What This PR Does Not Prove
- It does not prove durable market alpha.
- It does not prove the strategies are profitable live.
- It does not prove the ranking model is learned or statistically calibrated.
- It does not prove real-world fill quality beyond the existing deterministic gates.

## Human Approval
- Human approval is required before any future change that touches broker behavior, live execution, or runtime feed lifecycle.
