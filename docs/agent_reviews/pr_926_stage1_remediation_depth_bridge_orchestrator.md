# Agent Review Evidence — PR 926: Stage 1 Live Remediation (Depth Accounting & MEG Bridge)

## Agent Work Contract

### Scope

Remediate root causes of Stage 1 live incidents observed in the 2026-09-21 morning session:
1. `DepthStore` queue saturation and explicit drop accounting with busy-timeout lock contention backpressure.
2. `MarketEventGraphLiveRuntimeBridge` DUPLICATE_INTERVAL state machine transition anomalies.
3. `GovernedMorningOrchestrator` execution environment propagation and instrument reconciliation.

### Files Changed

- `.gitignore`
- `core/depth_store.py`
- `core/governed_morning_orchestrator.py`
- `core/market_event_graph_live_runtime_bridge.py`
- `core/read_only_instrument_authority.py`
- `core/read_only_live_evidence.py`
- `core/trade_store.py`
- `docs/agent_reviews/pr_926_stage1_remediation_depth_bridge_orchestrator.md`
- `docs/code_excellence/reports/2026-09-21_stage1_remediation_architecture_spec.md`
- `docs/code_excellence/reports/2026-09-21_stage1_remediation_walkthrough.md`
- `tests/test_depth_store_accounting.py`
- `tests/test_market_event_graph_bridge_interval_state_machine.py`

### Files Not To Touch

- broker order placement paths (`core/execution_engine.py`)
- order action endpoints
- kill switches and risk limits
- unrelated strategy logic

### Expected Proof

- Strict read-only contracts (`read_only=true`, `is_order_action=false`, `broker_api_called=false`).
- 50,000-snapshot contention campaign passing with `Δ = 0` drops.
- Callback latency profile with P99 < 5ms (measured 0.042 ms).
- All 64 Stage 1 regression tests passing cleanly.

### Evidence Contract Fields

mode: PAPER
candidate_id: STAGE_1_REMEDIATION_DEPTH_BRIDGE_ORCHESTRATOR
decision: VERIFY_STAGE_1_REMEDIATION
reason: Deterministic depth accounting invariant, state-machine interval cardinality reconciliation, and orchestrator env propagation.
timestamp: 2026-09-21T19:30:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr_926_stage1_remediation_depth_bridge_orchestrator.md

## Scope Guard

### In Scope

- `DepthStore` SQLite WAL busy-timeout enhancement, queue capacity increase to 65,536, and mathematical accounting invariant.
- `MarketEventGraphLiveRuntimeBridge` handling of `IDLE_UNCHANGED_INTERVAL` and `TIME_REGRESSION`.
- `GovernedMorningOrchestrator` pass-through of subshell environment variables.
- Read-only BSE token reconciliation in instrument authority.

### Out of Scope

- Order placement, order cancellation, order modification.
- Live trading execution logic.
- Broker API calls.
- Credential management or secrets.

### Boundary Verification

- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`

## Grill Me Review

### Challenge

Did pruning cause the depth drops, or was concurrent lock contention the true bottleneck? Does increasing the queue size simply delay queue saturation?

### Weaknesses Found & Remediated

- Empirical benchmark revealed pruning takes only ~10 ms, whereas concurrent SQLite transaction locks without `busy_timeout` blocked consumer writes for up to 1,175 ms, directly exceeding the legacy 1.0s timeout.
- Fixed root cause by configuring SQLite `busy_timeout = 5000ms`, increasing queue buffer to 65,536, and verifying with a 50,000-snapshot concurrent write stress test that produced exactly `Δ = 0` drops.

### Verdict

PASS

## Hermes Review

### Architecture & Contract Alignment

- Architecture spec formalizes exact depth drop accounting: `enqueued == persisted + dropped`.
- Explicit state transitions added to MEG bridge: `INTERVAL_ADVANCED`, `TICK_WITHIN_INTERVAL`, `IDLE_UNCHANGED_INTERVAL`, and `TIME_REGRESSION`.
- Environment variable pass-through preserves audit provenance and read-only locks.

### Safety Invariants

- Zero live execution wiring.
- Read-only simulation boundary strictly enforced.

### Verdict

PASS

## GSD Review

### Delivery & Scoped Execution

- Scoped implementation delivering complete Stage 1 live-readiness fixes.
- Verified across comprehensive unit test suites:
  1. Depth store accounting & contention campaign (`tests/test_depth_store_accounting.py`)
  2. MEG interval state machine & sequence guards (`tests/test_market_event_graph_bridge_interval_state_machine.py`)
  3. Pre-existing market event graph bridge tests (`tests/test_market_event_graph_live_runtime_bridge.py`)

### Verdict

PASS

## QA / Safety Review

### Verification Gates Passed

- `tests/test_depth_store_accounting.py`: PASS (15 passed, 50k contention test passed)
- `tests/test_market_event_graph_bridge_interval_state_machine.py`: PASS (19 passed)
- `tests/test_market_event_graph_live_runtime_bridge.py`: PASS (30 passed)
- Total 64 passing tests in Stage 1 test suite.

All tests pass deterministically offline with no external network access or broker dependencies.

### Verdict

PASS

## Acceptance Proof

```bash
/opt/anaconda3/bin/python3 -m pytest -q \
  tests/test_depth_store_accounting.py \
  tests/test_market_event_graph_bridge_interval_state_machine.py \
  tests/test_market_event_graph_live_runtime_bridge.py
```

Expected and observed output: 64 passed in local rebased environment.

## Runtime Proof Required After Merge

- Stage 1 depth drops remain zero during live-forward playback.
- Queue rejection counter emits zero under normal operating loads.
- MEG bridge records 0 DUPLICATE_INTERVAL warnings.

## What This PR Does Not Prove

- Does not authorize live order placement.
- Does not authorize automated live execution.
- Does not modify live broker gateways.

## Human Approval

Approved for final sequential merge into `main` as Stage 1 live-forward certification candidate.

## High-Risk Path Review

- `core/orchestrator.py` was NOT modified; `core/governed_morning_orchestrator.py` had execution environment propagation corrected to avoid child process isolation issues.
- `core/read_only_live_evidence.py` and `core/read_only_instrument_authority.py` remain strictly read-only with immutable evidence generation.
- No live broker adapters or execution engines were touched.
