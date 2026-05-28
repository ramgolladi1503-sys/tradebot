# AGENT-ELITE-05 — Cerberus Broker/Mode Call-Graph Guard

mode: REVIEW
candidate_id: AGENT-ELITE-05-CERBERUS-CALL-GRAPH-GUARD
decision: review_pending
reason: cerberus_static_broker_mode_call_graph_guard
source: docs/agent_reviews/AGENT_ELITE_05_CERBERUS_CALL_GRAPH.md
timestamp: 2026-05-28T17:00:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

Issue: #377
Parent: #372
Depends on: #376 / PR #392 / merge commit 3218c6e0caafbb0a6ddf97e180328b2013a3ba3c

## Agent Work Contract

This PR implements AGENT-ELITE-05 only.

The work upgrades the existing static safety-boundary audit so Cerberus can reason over AST imports, calls, and assignments instead of relying only on raw text markers. The goal is to better distinguish real broker/order leakage from harmless string fixture text.

It must not run product runtime code, call brokers, place orders, modify broker code, change dashboard behavior, change strategy behavior, or change ranking behavior.

## Scope Guard

Allowed:

- Update `tools/repo_forensics/safety_boundary.py`.
- Update focused tests in `tests/test_repo_forensics_safety_boundary.py`.
- Add this agent-review evidence file.

Not allowed:

- Runtime execution.
- Broker calls.
- Broker code changes.
- Live order behavior.
- Dashboard behavior changes.
- Strategy/ranking behavior changes.
- Broad repo-forensics refactor.
- Test skip/xfail.

## High-Risk Path Review

This PR modifies static forensics code only.

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

Question: Does this allow real broker/order leakage to pass?

Answer: No. Real AST calls into order-action methods still produce findings, with CRITICAL severity in paper/sim/read-only paths.

Question: Does this reduce false positives?

Answer: Yes. Harmless order words inside string-only test fixtures are no longer treated as hard broker leakage.

Question: Does this execute code to build a call graph?

Answer: No. It parses Python AST only.

Question: Does this touch trading behavior?

Answer: No. It is static analysis only.

## Hermes Review

The implementation is intentionally additive and narrow:

- Extract imported modules from AST.
- Extract called names from AST.
- Extract literal assignments from AST.
- Flag read-only imports of broker/execution-adjacent modules.
- Flag paper/sim imports of broker-adjacent modules.
- Flag paper/sim call paths that combine broker-adjacent import and order-action call.
- Preserve existing action-field assignment checks.

## GSD Review

Smallest safe implementation:

- Refine existing `safety_boundary.py` instead of adding a parallel scanner.
- Keep the public entry point `audit_safety_boundaries(...)` unchanged.
- Add focused tests for the acceptance criteria.

Files changed:

- `tools/repo_forensics/safety_boundary.py`
- `tests/test_repo_forensics_safety_boundary.py`
- `docs/agent_reviews/AGENT_ELITE_05_CERBERUS_CALL_GRAPH.md`

## QA / Safety Review

Focused command:

```bash
PYTHONPATH=. pytest tests/test_repo_forensics_safety_boundary.py -q
```

Recommended additional command:

```bash
PYTHONPATH=. pytest tests/test_repo_forensics_safety_boundary.py tests/test_repo_forensics_critical_negative_matrix.py -q
```

Safety assertions:

- No runtime import of target modules.
- No broker calls.
- No order behavior.
- No live execution.
- No dashboard behavior change.
- Broker code is untouched.

## Acceptance Proof

The tests prove:

- Paper path order-action calls are critical.
- Read-only action fields remain critical.
- Read-only broker-client imports are flagged.
- Paper path plus broker-client import plus order-action call reports a critical call path.
- String fixture text containing order words does not create false hard failure.
- Safe regular files produce no findings.

## Runtime Proof Required After Merge

No live runtime proof is required for this PR. This is static safety-boundary analysis only.

## What This PR Does Not Prove

- Does not prove live startup succeeds.
- Does not prove candidate quality.
- Does not prove ranking formula quality.
- Does not prove broker readiness.
- Does not prove profitability.
- Does not prove dashboard accuracy.
- Does not trace dynamic runtime dispatch.

## Human Approval

Required before merge.
