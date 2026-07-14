# PR #90 — Paper Decision Contract Snapshots

## Agent Work Contract

**Work item:** Lock the paper decision output contract created by the read-only paper decision orchestrator.

**Scope:**

- Add deterministic snapshot tests for paper decision reports.
- Add fixtures for clean paper-ready, fallback-blocked, risk-blocked, empty/no-trade, and near-executable/wait reports.
- Prove safety invariants: `read_only=true`, `is_order_action=false`, `append=false`, and `allowed_for_live_execution=false`.

**Out of scope:**

- Production code changes.
- Broker calls.
- Paper order lifecycle.
- Ledger mutation.
- Dashboard work.
- Agent webhook/API/dashboard/auto-merge expansion.
- External agent auto-calling.

## Grill Me Review

**Verdict:** Approved with constraint.

**Hard criticism:** Snapshot-only work can become fake progress if it does not protect a product-critical boundary. This PR is acceptable only because it locks the newly introduced paper-decision center before later dashboard, replay, ledger, and edge-gate work depend on it.

**Required proof:**

- Snapshot fixtures must be deterministic.
- No timestamps/run IDs/dynamic fields in the snapshot contract.
- Fallback and risk-blocked cases must remain blocked.
- Clean case may allow paper order creation, but never live execution.

**Result:** Scope is valid. Do not add new reporting abstractions or production behavior.

## Hermes Review

**Verdict:** Approved.

**Safety checks:**

- No broker/order/live path touched.
- No runtime wiring added.
- No dashboard behavior changed.
- No strategy/scoring/ranking changes.
- Snapshot contract enforces non-order-action fields.
- Blocked cases preserve explicit blocker reasons.

**Risk:** Fixture drift can hide intentional product changes if updated casually. Any future fixture update must explain the contract change in the PR body.

## GSD Review

**Verdict:** Approved to implement.

**Plan check:**

1. Add snapshot tests.
2. Add five fixtures.
3. Validate top-level schema keys.
4. Validate core safety flags.
5. Keep diff reviewable and isolated to tests/fixtures/docs.

**Merge gate:**

- CI green.
- Portfolio CI green.
- CodeQL green.
- PR comment must include this 3-agent evidence summary.

## Scope Guard

**Decision:** PASS.

**Files allowed:**

- `tests/test_paper_decision_contract_snapshots.py`
- `tests/fixtures/paper_decision_contract/*.json`
- `docs/agent_reviews/PR90_PAPER_DECISION_CONTRACT_SNAPSHOTS.md`

**Files forbidden for this PR:**

- `core/*`
- `dashboard/*`
- `strategies/*`
- broker/execution/router files
- runtime wiring scripts

## Approval + Evidence

Approved for PR creation after the above files are committed.

Evidence expected in PR:

- This document committed.
- PR body contains the same mandatory review-gate summary.
- PR conversation has a top-level agent review evidence comment.


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
