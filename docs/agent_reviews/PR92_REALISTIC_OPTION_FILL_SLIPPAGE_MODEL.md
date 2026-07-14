# PR #92 — Realistic Option Fill and Slippage Model

## Agent Work Contract

**Work item:** Add a pure option paper fill/slippage model.

**Scope:**

- Calculate BUY entry paper fill price from ask plus slippage.
- Calculate BUY exit paper fill price from bid minus slippage.
- Reject LTP-only fills.
- Reject stale quotes.
- Reject missing/low depth.
- Reject wide spreads.
- Reject fallback/advisory quotes.
- Preserve upstream quote blockers/warnings.

**Out of scope:**

- Paper order state mutation.
- Paper risk ledger mutation.
- Broker calls.
- Live orders.
- Runtime wiring.
- Dashboard work.
- Persistence/event writing.
- Strategy/scoring/ranking changes.
- Agent webhook/API/dashboard/auto-merge expansion.
- External agent auto-calling.

## Grill Me Review

**Verdict:** Approved with constraint.

**Hard criticism:** A paper fill model is dangerous if it uses LTP-only prices or optimistic mid-price fills. That creates fake profitability. This PR is acceptable only because it rejects LTP-only data and uses ask for BUY entry and bid for BUY exit with explicit slippage.

**Required proof:**

- BUY entry uses ask plus slippage.
- BUY exit uses bid minus slippage.
- LTP-only quote is rejected.
- Stale/wide/missing-depth/fallback/advisory quotes are rejected.
- No order or ledger mutation exists.

## Hermes Review

**Verdict:** Approved.

**Safety checks:**

- No broker adapter touched.
- No live order path touched.
- No runtime loop touched.
- No dashboard touched.
- No paper ledger mutation.
- No paper order state transition.
- Fill decision has `broker_order_action=false`, `live_order_action=false`, `is_order_action=false`, and `append=false`.

**Risk:** Later PRs must not bypass this model with LTP-only fills.

## GSD Review

**Verdict:** Approved to implement.

**Plan check:**

1. Add `core/option_fill_model.py`.
2. Add `tests/test_option_fill_model.py`.
3. Test approved entry/exit calculations.
4. Test LTP-only rejection.
5. Test stale quote, wide spread, missing depth, fallback/advisory rejection.
6. Keep diff isolated and reviewable.

## Scope Guard

**Decision:** PASS.

**Files allowed:**

- `core/option_fill_model.py`
- `tests/test_option_fill_model.py`
- `docs/agent_reviews/PR92_REALISTIC_OPTION_FILL_SLIPPAGE_MODEL.md`

**Files forbidden for this PR:**

- broker/execution/router files
- dashboard files
- strategy/ranking/scoring files
- runtime scripts
- paper risk ledger files
- paper order state machine mutation unless explicitly scoped later

## Approval + Evidence

Approved for PR creation after the above files are committed.

Evidence expected in PR:

- This document committed.
- PR body includes 3-agent evidence summary.
- PR conversation includes top-level 3-agent evidence comment.


## QA / Safety Review

N/A

## High-Risk Path Review

N/A

## Acceptance Proof

N/A

## Runtime Proof Required After Merge

N/A

## What This PR Does Not Prove

N/A

## Human Approval

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
