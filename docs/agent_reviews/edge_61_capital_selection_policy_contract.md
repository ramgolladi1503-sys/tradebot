# Agent Review — EDGE-61 Capital Allocation / Selection Policy Contract

mode: PAPER
candidate_id: EDGE-61-CAPITAL-SELECTION-POLICY-CONTRACT
decision: APPROVED_FOR_READ_ONLY_SELECTION_POLICY_PR
reason: Adds deterministic read-only capital and selection policy evidence without broker, live, order, scoring, strategy, or runtime allocation behavior.
timestamp: 2026-05-24T18:05:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge_61_capital_selection_policy_contract.md

## Agent Work Contract

### Scope

Implement a pure/read-only capital and selection policy contract that explains which candidates may be selected, capped, skipped, or blocked.

### Files changed

- `core/capital_selection_policy.py`
- `tests/test_edge61_capital_selection_policy_contract.py`
- `docs/EDGE_61_CAPITAL_SELECTION_POLICY_CONTRACT.md`
- `docs/agent_reviews/edge_61_capital_selection_policy_contract.md`

### Explicit non-goals

- No runtime allocation wiring
- No strategy tuning
- No score-weight changes
- No threshold loosening
- No ML
- No aggressive capital optimization
- No broker imports
- No broker API calls
- No submit, modify, cancel, or exit behavior
- No dashboard rewrite

## Grill Me Review

### Challenge 1 — Is this secretly changing allocation behavior?

Risk: A capital policy PR could accidentally alter existing runtime allocation.

Answer: The PR adds a new pure contract module and does not modify `core/capital_allocator.py` or `core/opportunity_engine.py`.

Proof:

- Changed files are limited to the new module, tests, docs, and agent-review evidence.

### Challenge 2 — Can fallback or advisory rows still receive capital?

Risk: Fallback/advisory rows could look selected if they keep legacy executable-looking fields.

Answer: The policy classifies fallback and advisory evidence first and assigns zero allocation with explicit reasons.

Proof:

- `test_non_executable_advisory_and_fallback_candidates_get_zero_allocation`

### Challenge 3 — Can a candidate exceed configured max allocation?

Risk: Requested allocation could exceed per-candidate cap.

Answer: Assigned allocation is capped by `max_allocation_per_candidate` and remaining capital.

Proof:

- `test_candidate_allocation_never_exceeds_configured_maximum`

### Challenge 4 — Can eligible skipped candidates get vague NO_SELECTION reasons?

Risk: The report might skip candidates without explainable reason, recreating the UI problem at the allocation layer.

Answer: Skipped eligible candidates receive concrete reasons such as `selection_limit_reached`, `symbol_cap_reached`, `family_cap_reached`, or `capital_budget_exhausted`.

Proof:

- `test_no_eligible_skipped_candidate_has_empty_or_no_selection_reason`

## Hermes Review

### Contract quality

The module exposes one public function, `explain_capital_selection_policy(...)`, and immutable dataclass outputs. It does not mutate candidate rows.

### Determinism

Records are produced in input rank order with deterministic reasons. Output is deterministic except `generated_epoch`.

Proof:

- `test_report_has_explicit_non_action_metadata_and_deterministic_payload`

### Backward compatibility

The existing runtime allocator remains untouched. This PR is additive and read-only.

## GSD Review

### What changed

Added a read-only capital/selection explanation contract after EDGE-60 directional bias audit.

### Why this matters

The product needs to prove why a candidate would be selected, capped, skipped, or blocked before any future runtime allocation or selection behavior is trusted.

### Smallest useful implementation

A pure contract module with focused tests and docs. No runtime wiring, dashboard integration, or allocation mutation.

## QA / Safety Review

### Safety boundaries checked

- No broker import was added.
- No live runtime path was modified.
- No order-action function was added.
- No strategy score or threshold was changed.
- Existing `core/capital_allocator.py` was not modified.
- The report exposes `is_order_action=false` and `broker_api_called=false`.

### Negative and edge-case tests

- Advisory and fallback candidates get zero allocation.
- Unknown/non-executable candidates fail closed to zero allocation.
- Selection limits are enforced.
- Symbol caps are enforced.
- Family caps are enforced.
- Budget exhaustion is enforced.
- Candidate max allocation caps are enforced.
- Eligible skipped candidates must have explainable reasons.

## Scope Guard

### In scope

- Add read-only capital selection policy contract.
- Add focused unit tests.
- Add docs and agent-review evidence.

### Out of scope

- Runtime allocation wiring.
- Existing allocator rewrite.
- Portfolio optimization changes.
- Strategy tuning.
- Scoring changes.
- Broker behavior.
- Dashboard rewrite.

### Files not touched

- `core/capital_allocator.py`
- `core/opportunity_engine.py`
- `core/execution_engine.py`
- `core/execution_router.py`
- `core/kite_client.py`
- `core/risk_engine.py`
- `strategies/*`
- `dashboard/streamlit_app.py`
- `dashboard/streamlit_app_runtime.py`

## Acceptance Proof

Required command:

```bash
PYTHONPATH=. python -m pytest tests/test_edge61_capital_selection_policy_contract.py
```

Expected proof:

- No candidate can exceed configured max allocation.
- Non-executable/advisory/fallback candidates get zero allocation.
- Selection limit is enforced.
- Family and symbol caps are explainable.
- No eligible skipped candidate produces an empty or `NO_SELECTION` reason.
- Report output is deterministic except timestamp evidence.
- Existing tests remain green in CI.

## Runtime Proof Required After Merge

EDGE-61 has no runtime wiring, so runtime proof is limited to confirming no runtime behavior changed.

Required after merge:

1. Confirm the existing runtime and dashboard entrypoints still start unchanged.
2. Confirm no new broker calls appear in logs because this PR has no broker path.
3. Confirm the contract can be imported in a local shell without side effects.

## What This PR Does Not Prove

- It does not prove real profitability.
- It does not prove the selected candidate should be traded live.
- It does not prove portfolio optimization is correct.
- It does not prove feed freshness is solved.
- It does not prove risk limits are complete.
- It does not wire allocation into runtime.

## Human Approval

Human approval required before merge:

- Reviewer must verify this PR remains read-only.
- Reviewer must verify CI is green.
- Reviewer must verify existing allocator/runtime behavior was not modified.
- Reviewer must verify no broker/live/order scope entered the patch.

## Remaining Risk

This contract is intentionally conservative and schema-flexible. Future `CandidateIntent`, `MarketState`, and final executable quality gates should provide canonical fields so this policy can consume stricter inputs instead of loose candidate rows.
