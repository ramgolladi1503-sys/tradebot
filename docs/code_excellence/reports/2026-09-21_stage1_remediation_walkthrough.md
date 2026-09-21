# Stage 1 Remediation & Institutional Verification Walkthrough

**Target Worktree**: `/Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1`  
**Branch**: `fix/stage1-remediation-depth-bridge-orchestrator`  
**Candidate Commit SHA**: [`2aec7ef9f895e0de96e8bfe94c9e7314d843547b`](file:///Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1)  
**Safety Mandate**: `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`

---

## 1. Executive Summary & Epistemic Boundaries

This patch completes Stage 1 remediation following the 2026-09-21 live observation session. It resolves the two observed runtime anomalies (`depth_persistence_queue_full` and `DUPLICATE_INTERVAL`) and the morning launcher blockers (`MROS env propagation` and `BSE SENSEX token 265 authority reconciliation`).

### Critical Epistemic Claims Clarification
- **What is proven**: Zero **unaccounted** depth snapshot loss after accounting entry:
  $$\text{ENQUEUED} = \text{PERSISTED} + \text{IN\_FLIGHT} + \text{QUEUE\_DEPTH} + \text{REJECTED} \quad (\Delta = 0)$$
  Any queue drop is strictly accounted for in `depth_rejections.jsonl` with explicit timestamps and reasons.
- **What is NOT claimed**: We do **not** claim mathematical zero drops under infinite burst pressure. If write pressure exceeds consumer drain rate indefinitely and the 32,768-capacity queue saturates, explicit rejection continues to occur safely without stalling WebSocket callbacks.

---

## 2. Root Cause Analyses (RCA) & Remediations

### A. Depth Persistence Queue Contention & Drop Elimination
- **Empirical Measurement**:
  - Initial hypothesis: `DELETE ... NOT IN (SELECT ...)` query execution was the primary bottleneck.
  - **Falsification**: Direct disk WAL execution of the pruning query across 30,000 snapshots measured at $\approx 10\text{ ms}$.
  - **True Root Cause**: Process-wide `_SQLITE_TRANSACTION_LOCK` held during tick ingestion and WAL maintenance created concurrent lock contention spikes $> 1,175\text{ ms}$. With the previous queue `put(timeout=1.0s)` timeout, thread contention caused timeouts and 7,060 dropped records.
- **Remediations**:
  - Decoupled retention pruning into an asynchronous periodic maintenance loop in [`core/depth_store.py`](file:///Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1/core/depth_store.py) and extracted pruning from the hot batch insert transaction in [`core/trade_store.py`](file:///Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1/core/trade_store.py).
  - Reduced `put_timeout_sec` from `1.0s` to `0.05s` so WebSocket ingestion callbacks never stall on a saturated queue.
  - Increased `queue_maxsize` from 16,384 to 32,768 and `batch_size` from 50 to 100.
  - Added continuous tracking of dequeued in-flight records (`_persist_in_flight`), guaranteeing strict conservation.

### B. Bridge Interval Disambiguation (`DUPLICATE_INTERVAL`)
- **Cardinality Audit**: 5,022 bridge calls = 29 exported 1-minute bars + 4,744 identical interval polls + 249 transient startup/sync rejections (0 unaccounted).
- **Remediation**:
  - In [`core/market_event_graph_live_runtime_bridge.py`](file:///Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1/core/market_event_graph_live_runtime_bridge.py), disambiguated benign duplicate polling (`interval_start == last_interval_start`) logged at `DEBUG` as `IDLE_UNCHANGED_INTERVAL` from genuine chronological errors (`interval_start < last_interval_start`) logged at `ERROR` as `TIME_REGRESSION`.
  - Updated [`core/read_only_live_evidence.py`](file:///Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1/core/read_only_live_evidence.py) to recognize `IDLE_UNCHANGED_INTERVAL`.

### C. Autonomous Morning Launcher Blockers
- **Orchestrator MROS Environment**:
  - In [`core/governed_morning_orchestrator.py`](file:///Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1/core/governed_morning_orchestrator.py), explicit child process environment propagation ensures `MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE="true"`, `MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH`, and `FEED_FORENSICS_ENABLED="true"` are inherited by child observer processes.
- **BSE SENSEX Token 265 Authority Reconciliation**:
  - Included `"BSE"` in `fetch_current_instruments` in [`core/governed_morning_orchestrator.py`](file:///Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1/core/governed_morning_orchestrator.py) and added `"BSE"` to default exchanges in [`core/read_only_instrument_authority.py`](file:///Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1/core/read_only_instrument_authority.py).

---

## 3. Empirical Verification Results

### Acceptance Gate 1: 50,000 Snapshot Contention Stress Test
- **Execution**: 50,000 depth snapshots enqueued against 3 background worker threads continuously holding write transactions on SQLite.
- **Outcome**:
  - Invariant: $\text{ENQUEUED} (50,000) = \text{PERSISTED} (50,000) + \text{IN\_FLIGHT} (0) + \text{QUEUED} (0) + \text{REJECTED} (0)$.
  - Accounting Discrepancy: $\Delta = 0$ throughout the entire run.

### Acceptance Gate 2: Callback Latency Profile (5,000 Updates)
- $\text{P50} = 0.018\text{ ms}$
- $\text{P90} = 0.022\text{ ms}$
- $\text{P99} = 0.116\text{ ms}$ (comfortably $< 5.0\text{ ms}$)
- $\text{Max} = 2.184\text{ ms}$

### Full Focused Regression Suite
- Ran 64 unit and property tests across:
  - `tests/test_depth_store_accounting.py`
  - `tests/test_market_event_graph_bridge_interval_state_machine.py`
  - `tests/test_governed_morning_orchestrator.py`
  - `tests/test_market_event_graph_live_source.py`
  - `tests/test_trade_store_depth_snapshot_resilience.py`
- **Command**:
  ```bash
  /opt/anaconda3/bin/python3 -m pytest -q \
    tests/test_depth_store_accounting.py \
    tests/test_market_event_graph_bridge_interval_state_machine.py \
    tests/test_governed_morning_orchestrator.py \
    tests/test_market_event_graph_live_source.py \
    tests/test_trade_store_depth_snapshot_resilience.py
  ```
- **Result**: `64 passed, 3 warnings in 17.28s`.

---

## 4. Governed Repository Artifacts & Git Status
- **Architecture Spec**: [`docs/code_excellence/reports/2026-09-21_stage1_remediation_architecture_spec.md`](file:///Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1/docs/code_excellence/reports/2026-09-21_stage1_remediation_architecture_spec.md)
- **Institutional Walkthrough**: [`docs/code_excellence/reports/2026-09-21_stage1_remediation_walkthrough.md`](file:///Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1/docs/code_excellence/reports/2026-09-21_stage1_remediation_walkthrough.md)
- **Git Status**: Clean worktree on branch `fix/stage1-remediation-depth-bridge-orchestrator`.

---

## 5. Next Live Forward Acceptance Gates

For the next live observation session (2026-09-22), promotion from `OFFLINE_REMEDIATION_SUPPORTED` to `LIVE_FORWARD_OPERATIONAL_REMEDIATION_SUPPORTED` requires satisfying:

```text
LIVE_STAGE_1_FORWARD_GATES

DEPTH_QUEUE_REJECTIONS == 0
UNACCOUNTED_REMAINDER == 0
QUEUE_HIGH_WATER < 32768
CALLBACK_P99 < 5ms

TIME_REGRESSION == 0
IDLE_UNCHANGED_INTERVAL allowed

MISSING_RUNTIME_TOKENS == []
SENSEX_265_RESOLVED == true

MROS_CHILD_STARTED == true
MROS_CHILD_PREFLIGHT == PASS

ORDERS_PLACED == 0
ORDERS_MODIFIED == 0
ORDERS_CANCELLED == 0
BROKER_WRITE_CALLS == 0
```

