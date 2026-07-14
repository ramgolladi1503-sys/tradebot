# PR #101 — Fallback Contract Execution Firewall

## Agent Work Contract

### Scope

Block fallback-resolved option contracts from ever surviving as executable Phase2 candidates. The live-observation validator found fallback-linked NIFTY traces reaching executable-looking shape (`permission=EXECUTE`, `final_action=EXECUTE`, `execution_allowed=True`). That is unsa-fe because fallback contract resolution means the orderable instrument mapping is uncertain.

### Files changed

- `core/engine_phase2_adapter.py`
- `tests/test_phase2_fallback_contract_firewall.py`
- `docs/agent_reviews/PR101_FALLBACK_CONTRACT_EXECUTION_FIREWALL.md`

### Hard boundaries

- No broker calls.
- No live order submission.
- No submit/modify/cancel/exit behavior.
- No runtime wiring.
- No dashboard changes.
- No strategy rewrite.
- No feed subscription changes.
- No paper order mutation.
- No paper risk ledger mutation.
- No fill/slippage changes.
- No external agent auto-calling, webhook, API, auto-merge, or dashboard agent work.

### Contract

A candidate carrying contract-resolution fallback evidence must be forced into a non-executable shape:

- `execution_allowed=False`
- `tradable=False`
- `execution_ok=False`
- `truth_allows_execution=False`
- `execution_blocked=True`
- `permission=QUEUE_ONLY`
- `final_action=QUEUE_ONLY`
- `max_final_action=QUEUE_ONLY`
- hard blocker `CONTRACT_RESOLUTION_FALLBACK_BLOCKED`

The candidate must not survive Phase2 ranking/output as an executable candidate.

## Grill Me Review

### Challenge

A fallback-resolved contract becoming executable-looking is not a cosmetic bug. It can route attention or later execution toward the wrong/inexact instrument. The fix must block at the candidate boundary, not only in logs.

### Findings

- Good: firewall is at Phase2 adapter boundary where candidates are filtered before selection.
- Good: fallback evidence is detected from direct flags, nested `source_flags`, and resolution status/source fields.
- Good: blocked candidates are visibly marked with hard blockers and non-executable fields.
- Constraint: this PR does not repair why fallback resolution happens; it prevents unsafe promotion.

### Result

Approved with no-strategy-rewrite/no-feed-change constraint.

## Hermes Review

### Scope verification

- No broker adapter imports.
- No order placement code touched.
- No dashboard files touched.
- No feed subscription code touched.
- No paper ledger/state-machine mutation.
- No fill/slippage changes.
- No runtime live-run command added.

### Safety verification

- Unsafe fallback contract candidates are forced to queue-only/blocked.
- Phase2 hard drop prevents fallback contract candidates from ranking output.
- Raw fallback candidates are not re-added by the adapter compatibility path.

### Result

Approved.

## GSD Review

### Implementation plan

1. Add explicit fallback-contract detection helper.
2. Add non-executable blocking helper.
3. Apply the firewall inside `_phase2_contract_hard_drop`.
4. Preserve existing Phase2 score/ranking behavior for clean candidates.
5. Add focused tests for direct flag, nested flag, hard drop, output drop, and raw re-add prevention.

### Test command

```bash
PYTHONPATH=. pytest -q tests/test_phase2_fallback_contract_firewall.py
```

### Result

Approved.

## Scope Guard

### In scope

- Phase2 candidate firewall.
- Tests proving fallback contracts cannot survive as executable candidates.
- 3-agent evidence.

### Out of scope

- Live-market validation rerun.
- Broker API calls.
- Runtime wiring.
- Dashboard.
- Strategy/scoring/ranking rewrite.
- Feed subscription repair.
- Contract resolver algorithm changes.
- Paper order mutation.
- Ledger mutation.
- PR #102+ work.

### Result

PASS.

## Approval + Evidence

PR #101 is approved for PR creation once targeted tests pass.

Evidence summary for PR body/comment:

- Agent Work Contract: PASS
- Grill Me: PASS with no-strategy-rewrite/no-feed-change constraint
- Hermes: PASS
- GSD: PASS
- Scope Guard: PASS


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
