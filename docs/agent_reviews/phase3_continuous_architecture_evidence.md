# Phase 3 Continuous Architecture

## Agent Work Contract
- source_agent: Antigravity
- action: GENERATE_PATCH
- title: Route AlphaDecay State to Execution Engine
- scope: Link `AlphaDecayState` to `ExecutionEngine.evaluate_alpha_decay` to allow FORCE_EXIT triggers on alpha decay exhaustion.
- requested_paths: `core/execution_engine.py`, `core/orchestrator.py`, `tests/core/test_phase3_alpha_decay_streaming.py`
- allowed_paths: `core/execution_engine.py`, `core/orchestrator.py`, `tests/core/test_phase3_alpha_decay_streaming.py`
- forbidden_paths: `main.py`, `run_live.sh`, `.env`, `credentials.py`
- expected_tests: Unit tests for `evaluate_alpha_decay` processing and intent application.
- acceptance_proof: All core tests must pass (98 passed locally) and PR gates green.

## Scope Guard
Verified that we only touched `execution_engine.py` to add `evaluate_alpha_decay` and `orchestrator.py` to route quotes. No bypass of any risk limits.

## Grill Me Review
CRITIQUE_SCOPE: We are routing live market metrics into `evaluate_alpha_decay` which modifies runtime state. 
Risk: High risk due to modifying execution flow and triggering exits.
Mitigation: The `FORCE_EXIT` only triggers `apply_exit_intent` with `reason_code="decay_exhausted"`, which passes through the normal execution state machine safely.

## High-Risk Path Review
Modified `core/execution_engine.py` and `core/orchestrator.py`. 
These are high-risk files.
Changes are explicitly limited to passing the `AlphaDecayState` through to evaluate it, applying standard exit intent via `self.apply_exit_intent(intent)`. No direct broker calls or live credentials were leaked or altered. Tests added in `tests/core/test_phase3_alpha_decay_streaming.py`.

## Hermes Review
DESIGN_ARCHITECTURE:
`Orchestrator` -> receives market quote -> calls `ExecutionEngine.evaluate_alpha_decay(trade_id, decay_state, l2, momentum)`
If decay conditions hit threshold -> `apply_exit_intent` with `FULL_EXIT`.

## GSD Review
PLAN_PR: Implemented the aforementioned architecture routing.

## QA / Safety Review
`read_only=true` (Not applicable as we apply intent, but no broker calls directly)
`is_order_action=false` (Applies intent, does not execute order directly in this fn)
`broker_api_called=false`
`mode=SIM`
`candidate_id=N/A`
`decision=ROUTE_STATE`
`reason=continuous_architecture_phase3`
`timestamp=1781171000`
`source=Antigravity`
`allowed_for_live_execution=false unless explicitly scoped and human-approved`
`append=false`

Tested via: `pytest tests/core/test_phase3_alpha_decay_streaming.py`
Verified unit tests ensure the state correctly triggers an exit intent when decay is exhausted.

## Acceptance Proof
1. Files changed: `core/execution_engine.py`, `core/orchestrator.py`, `tests/core/test_phase3_alpha_decay_streaming.py`
2. Design approach: Forward real-time metrics to execution engine which processes the continuous edge model.
3. Risks: Inadvertent exits. Prevented by strict logic in `monitor_alpha_decay`.
4. Tests: `test_phase3_alpha_decay_streaming.py` validates object instantiation and evaluation return value.
5. What was not touched: No strategies or broker connection logic.
6. Acceptance proof: 98 tests pass in `tests/core/`.

## Runtime Proof Required After Merge
Need to observe real-time decay state transitions in SIM mode to ensure proper metrics tracking.

## What This PR Does Not Prove
Does not prove profitability of the exit logic, only that the routing architecture functions properly.

## Human Approval
Approved via user "proceed" prompt.
