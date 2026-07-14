# Tighten Live RCA Auth Failure Classification

mode: REVIEW
candidate_id: PR-LIVE-RCA-AUTH-TIGHTENING
decision: tighten_live_rca_auth_failure_classification
reason: Restrict Live RCA auth failure classification to explicit auth evidence so generic AUTH-related text does not override the real feed lifecycle blocker in the command center.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/live-rca-auth-tightening.md

## Agent Work Contract

### Scope

Tighten the Live RCA classifier so it only emits `AUTH_FAILURE` for explicit auth blocker evidence. Keep the command center feed-first blocker ordering intact.

### Files changed

- `core/agents/live_rca_agent.py`
- `tests/test_live_rca_agent.py`
- `tests/test_agent_command_center.py`
- `docs/agent_reviews/live-rca-auth-tightening.md`

### Out of scope

- No broker/order changes.
- No live orders.
- No websocket reconnect behavior changes.
- No strategy changes.
- No ranking or scoring changes.
- No Phase2 changes.
- No dashboard/UI changes.
- No risk gate changes.

## Grill Me Review

- Generic AUTH-like words must not override the actual feed blocker.
- 401 handling must be explicit and line-scoped, not substring-driven.
- The smoke report must stay feed-first.

## Hermes Review

- Live RCA should distinguish explicit auth blockers from noisy runtime text.
- The classifier should prefer concrete evidence over broad token matches.
- The command center should keep reporting `FEED_STABILITY` first when feed evidence is stronger.

## GSD Review

- Keep the patch narrow: classifier, tests, and this review doc only.
- Add regressions for generic AUTH text, explicit auth blockers, and the current feed-churn smoke case.

## Scope Guard

This PR is evidence-classification only. It does not change runtime trading behavior, feed recovery behavior, ranking, Phase 2, or broker logic.

## QA / Safety Review

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- `no_order_action=true`
- Generic AUTH noise must not classify as `AUTH_FAILURE`.
- Missing or malformed evidence must still fail closed.

## Acceptance Proof

- `AUTH_FAILURE` only appears for explicit auth evidence.
- Generic AUTH text does not trigger `AUTH_FAILURE`.
- The current feed-churn logs still resolve to `FEED_STABILITY` / `FIX_FEED_LIFECYCLE`.
- The command center does not say `Investigate auth_failure first.` for the current feed-churn logs.

## Runtime Proof Required After Merge

- Re-run the command center smoke against current runtime logs and confirm the top-level blocker remains `FEED_STABILITY`.
- Re-run Live RCA against current runtime logs and confirm it reports the feed blocker, not generic auth noise.

## What This PR Does Not Prove

- It does not prove live trading edge.
- It does not prove feed lifecycle stability is fixed.
- It does not change or validate broker/order behavior.
- It does not change ranking, Phase 2, or strategy formulas.

## Human Approval

Human approval required before merge.


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
