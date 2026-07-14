# PR #91 — Strict Paper Order State Machine

## Agent Work Contract

**Work item:** Add a strict in-memory paper order lifecycle state machine.

**Scope:**

- Add a paper order record model.
- Add explicit lifecycle states and allowed transitions.
- Reject invalid transitions.
- Reject duplicate/same-state transitions.
- Reject transitions after terminal states.
- Enforce fill quantity rules for partial/full fills.
- Keep the state machine in-memory and deterministic.

**Out of scope:**

- Broker calls.
- Live orders.
- Realistic fill/slippage modeling.
- Ledger mutation.
- Persistence/event writing.
- Dashboard/runtime wiring.
- Strategy/scoring/ranking changes.
- Agent webhook/API/dashboard/auto-merge expansion.
- External agent auto-calling.

## Grill Me Review

**Verdict:** Approved with constraint.

**Hard criticism:** A paper order state machine can easily become fake trading if it silently includes fills, broker-like behavior, or ledger mutation. This PR is acceptable only because it models lifecycle transitions and rejects unsafe/invalid transitions without pretending to execute anything.

**Required proof:**

- Terminal states reject further transitions.
- Invalid jumps reject.
- Fill quantity rules are explicit.
- Creation requires an approved paper decision.
- No broker/live/order side effect exists.

## Hermes Review

**Verdict:** Approved.

**Safety checks:**

- No broker adapter touched.
- No runtime loop touched.
- No dashboard touched.
- No ledger mutation added.
- No file persistence added.
- No fill/slippage model added.
- State record has `broker_order_action=false` and `live_order_action=false`.

**Risk:** Later PRs must not bypass this state machine when creating paper lifecycle records.

## GSD Review

**Verdict:** Approved to implement.

**Plan check:**

1. Add `core/paper_order_state_machine.py`.
2. Add `tests/test_paper_order_state_machine.py`.
3. Test creation preconditions.
4. Test valid transitions.
5. Test invalid transitions.
6. Test terminal rejection.
7. Test fill quantity invariants.
8. Keep diff isolated and reviewable.

## Scope Guard

**Decision:** PASS.

**Files allowed:**

- `core/paper_order_state_machine.py`
- `tests/test_paper_order_state_machine.py`
- `docs/agent_reviews/PR91_STRICT_PAPER_ORDER_STATE_MACHINE.md`

**Files forbidden for this PR:**

- broker/execution/router files
- dashboard files
- strategy/ranking/scoring files
- runtime scripts
- ledger/persistence files unless explicitly scoped later

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
