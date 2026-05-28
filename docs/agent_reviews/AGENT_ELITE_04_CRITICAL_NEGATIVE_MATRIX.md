# AGENT-ELITE-04 — Critical Negative Test Matrix

mode: REVIEW
candidate_id: AGENT-ELITE-04-CRITICAL-NEGATIVE-TEST-MATRIX
decision: review_pending
reason: minerva_required_negative_test_matrix
source: docs/agent_reviews/AGENT_ELITE_04_CRITICAL_NEGATIVE_MATRIX.md
timestamp: 2026-05-28T16:40:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

Issue: #376
Parent: #372
Depends on: #375 / PR #391 / merge commit f6f121f7cdcedf89dae003a570ccccdc73a0ce08

## Agent Work Contract

This PR implements AGENT-ELITE-04 only.

The work adds an evidence-only critical negative test matrix for Minerva. It checks supplied static test records against the required negative categories from the repo-forensics configuration:

- fallback candidate cannot become executable
- stale feed blocks order intent
- paper path cannot call live broker
- required evidence field absence fails contract

It must not run product runtime code, call brokers, place orders, modify strategy logic, change ranking behavior, or change dashboard behavior.

## Scope Guard

Allowed:

- Add `tools/repo_forensics/critical_negative_matrix.py`.
- Add focused tests in `tests/test_repo_forensics_critical_negative_matrix.py`.
- Add this agent-review evidence file.

Not allowed:

- Runtime execution.
- Broker calls.
- Live order behavior.
- Strategy/ranking behavior changes.
- Dashboard/UI changes.
- Broad repo-forensics refactor.
- Test skip/xfail.

## High-Risk Path Review

This PR adds static repo-forensics tooling only.

High-risk Tradebot paths intentionally unchanged:

- `core/kite_client.py`
- `core/execution_engine.py`
- `core/execution_router.py`
- `core/risk_engine.py`
- `core/orchestrator.py`
- `strategies/`
- `dashboard/`
- `config/`

## Grill Me Review

Question: Does this prove the full application has all negative tests?

Answer: No. It proves supplied records satisfy the required matrix. Future wiring can feed discovered repo tests into this matrix.

Question: Can a single keyword fake coverage?

Answer: No. Requirements use grouped signals. A lone weak keyword does not cover a category.

Question: Does this change Minerva scoring from AGENT-ELITE-03?

Answer: No. It adds a separate matrix report and does not change existing score calculations.

Question: Does this touch trading behavior?

Answer: No. It is static evidence analysis only.

## Hermes Review

The contract is intentionally additive:

- `NegativeTestRequirement`
- `NegativeTestCoverage`
- `CriticalNegativeTestMatrixReport`
- `build_critical_negative_test_matrix(...)`
- `render_critical_negative_test_matrix_report(...)`

## GSD Review

Smallest safe implementation:

- Define default required negative categories.
- Match grouped signals from supplied test records.
- Fail closed when a category lacks proof.
- Render a deterministic markdown report.

Files changed:

- `tools/repo_forensics/critical_negative_matrix.py`
- `tests/test_repo_forensics_critical_negative_matrix.py`
- `docs/agent_reviews/AGENT_ELITE_04_CRITICAL_NEGATIVE_MATRIX.md`

## QA / Safety Review

Focused command:

```bash
PYTHONPATH=. pytest tests/test_repo_forensics_critical_negative_matrix.py -q
```

Recommended additional command:

```bash
PYTHONPATH=. pytest tests/test_repo_forensics_critical_negative_matrix.py tests/test_repo_forensics_test_reality.py -q
```

Safety assertions:

- No runtime import of target modules.
- No broker calls.
- No order behavior.
- No live execution.
- No dashboard changes.

## Acceptance Proof

The tests prove:

- Complete supplied matrix records pass.
- A category without proof fails closed.
- Grouped signals are required; one loose keyword is insufficient.
- Rendered report includes a clear fail verdict.

## Runtime Proof Required After Merge

No live runtime proof is required for this PR. This is static negative-test matrix evidence only.

## What This PR Does Not Prove

- Does not prove live startup succeeds.
- Does not prove candidate quality.
- Does not prove ranking formula quality.
- Does not prove broker readiness.
- Does not prove profitability.
- Does not prove dashboard accuracy.
- Does not automatically scan the full repository test suite yet.

## Human Approval

Required before merge.
