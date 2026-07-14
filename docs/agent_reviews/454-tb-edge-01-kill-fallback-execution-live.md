# TB-EDGE-01 — Kill Fallback Execution in LIVE

mode: LIVE
candidate_id: TB-EDGE-01-kill-fallback-execution-live
decision: add_live_fallback_execution_contract
reason: Make fallback/synthetic/unknown-source candidates visible for debug but non-executable in LIVE.
timestamp: 2026-05-29T17:36:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/454-tb-edge-01-kill-fallback-execution-live.md

## Agent Work Contract
Implement Issue #454 only: TB-EDGE-01 — Kill Fallback Execution in LIVE.

## Scope Guard
In scope:
- Add a pure LIVE fallback execution normalization contract.
- Prove LIVE startup fails closed when Phase2 force-fallback flags are enabled.
- Prove fallback/synthetic/unknown-source rows become non-executable watchlist rows in LIVE.
- Preserve PAPER/SIM fallback shape.

Out of scope:
- Strategy scoring.
- Ranking weights.
- Broker calls.
- Live orders.
- Dashboard/UI.
- TB-EDGE-02 and later stories.

Files changed:
- `core/live_fallback_execution_contract.py`
- `tests/test_phase2_live_fallback_disabled.py`
- `docs/agent_reviews/454-tb-edge-01-kill-fallback-execution-live.md`

Files not touched:
- `core/engine_phase2_adapter.py`
- `core/execution_engine.py`
- `core/orchestrator.py`
- `strategies/`
- `dashboard/`

## Grill Me Review
The risk is a high-score fallback row becoming `ENTER` in LIVE. The contract explicitly sets:
- `execution_allowed=false`
- `truth_allows_execution=false`
- `tradable=false`
- `execution_ok=false`
- `forced_fallback_execution=false`
- `candidate_status=watchlist`
- `execution_status=not_executable`
- `max_final_action=QUEUE_ONLY`
- `primary_blocker=LIVE_FALLBACK_EXECUTION_BLOCKED`

Weak assumptions:
- A fallback row can still look attractive by score.
- A synthetic or unknown quote source can look complete enough for display.
- Startup safety and candidate safety must both fail closed.

Failure modes:
- LIVE with force-fallback config is rejected by runtime boot safety.
- LIVE fallback/unknown/synthetic candidates normalize to watchlist/non-executable.
- PAPER fallback shape is preserved for non-LIVE testing.

Missing proof:
- This PR does not wire the contract into every candidate handoff path; that remains later strict data and handoff stories.

Verdict: PASS — no open blocker in this review evidence.

## Hermes Review
Evidence remains read-only and machine-readable through deterministic tests. No broker API is called and no order action is introduced.

Scope pass/fail: PASS.
Boundary violations: none.
Files not to touch check: passed; no strategy, broker, dashboard, or execution engine files were modified.
Verdict: PASS.

## GSD Review
Purpose: make fallback-driven LIVE execution shape impossible at the contract level.
Scope: pure fallback execution contract and focused tests only.
Files changed: listed in Scope Guard.
Tests or reason not required: tests are required and added.
Evidence: tests cover startup unsafe flags, unknown quote source, nested source flags, PAPER preservation, and high-score fallback candidate behavior.
Risks: full candidate handoff wiring remains for later stories.
Next PR: TB-EDGE-02 only after this PR is merged.
Delivery verdict: PASS.
Evidence summary: focused safety tests prove LIVE fallback rows become non-executable.
Next action: merge only after all CI gates pass.

## QA / Safety Review
Tests prove:
- LIVE fails closed for `PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE=true`.
- LIVE fails closed for `PHASE2_FORCE_FALLBACK_ALLOW_LIVE=true`.
- Unknown quote source is blocked from LIVE execution.
- Nested synthetic/fallback source flags are blocked.
- PAPER fallback shape remains preserved.
- Existing high-score synthetic LIVE candidate still cannot enter.

Safety status:
- live_order_action=false
- broker_order_action=false
- is_order_action=false
- broker_api_called=false

## Acceptance Proof
Planned commands:

```bash
python -m py_compile core/live_fallback_execution_contract.py core/engine_phase2_adapter.py core/runtime_safety_boot_guard.py
PYTHONPATH=. python -m pytest -q tests/test_phase2_live_fallback_disabled.py
PYTHONPATH=. python -m pytest -q tests/test_engine_phase2_adapter.py
PYTHONPATH=. python -m pytest -q tests/test_runtime_safety_boot_guard.py
```

## Runtime Proof Required After Merge
During the next LIVE dry-observation or PAPER/SIM validation run, inspect any candidate/debug rows that carry fallback, synthetic, or unknown quote-source evidence.

Expected for LIVE fallback rows:
- `execution_allowed=false`
- `truth_allows_execution=false`
- `forced_fallback_execution=false`
- `candidate_status=watchlist`
- `execution_status=not_executable`
- `max_final_action=QUEUE_ONLY`
- `primary_blocker=LIVE_FALLBACK_EXECUTION_BLOCKED`

Expected for PAPER/SIM fallback rows:
- existing fallback debug shape remains visible unless another gate blocks it.

## What This PR Does Not Prove
It does not prove strict Phase2 live data contract, candidate handoff root-cause ledger, indicator prewarm, or ranking edge. Those remain later TB-EDGE stories.

## Human Approval
Human approval is required before merge. Do not start TB-EDGE-02 until this story is merged.


## High-Risk Path Review

N/A
