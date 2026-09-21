# Hermes Stage 1 Architecture Specification: Data Persistence Decoupling, Cadence Disambiguation & Autonomous Launcher Repair

```text
source_agent: hermes
action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS
title: Stage 1 Invariant Contracts & Remediation Architecture for 2026-09-21 Operational Anomalies
scope: Data persistence decoupling, bridge interval advancement state machine, morning orchestrator environment propagation, BSE/SENSEX token reconciliation
requested_paths:
  - core/depth_store.py
  - core/trade_store.py
  - core/market_event_graph_live_runtime_bridge.py
  - core/governed_morning_orchestrator.py
  - core/read_only_instrument_authority.py
  - core/daily_instrument_authority.py
allowed_paths:
  - core/depth_store.py
  - core/trade_store.py
  - core/market_event_graph_live_runtime_bridge.py
  - core/governed_morning_orchestrator.py
  - core/read_only_instrument_authority.py
  - core/daily_instrument_authority.py
  - tests/test_depth_store.py
  - tests/test_trade_store.py
  - tests/test_market_event_graph_live_runtime_bridge.py
  - tests/test_governed_morning_orchestrator.py
  - tests/test_daily_instrument_authority.py
forbidden_paths:
  - main.py
  - run_live.sh
  - config/
  - credentials.py
  - core/execution*
  - core/broker*
  - core/order*
  - core/risk*
  - core/feed*
  - strategies/
  - .env
  - runtime/live*
expected_tests:
  - test_depth_accounting_invariant_enqueued_equals_persisted_plus_queued_plus_rejected
  - test_depth_snapshot_writer_does_not_hold_process_sqlite_lock_under_contention
  - test_retention_prune_isolated_from_hot_depth_batch_write_path
  - test_bridge_interval_state_machine_distinguishes_unchanged_from_regression
  - test_bridge_reconciliation_zero_unaccounted_cycles
  - test_governed_morning_orchestrator_propagates_mros_environment
  - test_bse_sensex_token_265_reconciled_with_fetched_universe
acceptance_proof:
  - Automated unit and property tests verifying all 6 invariants
  - Independent offline reproduction script demonstrating zero queue drops under simulated tick and depth load
  - Clean git status and read-only verification: read_only=true, is_order_action=false, broker_api_called=false
```

---

## 1. Context & Epistemic Baseline (Post 2026-09-21 Live Session)

The authoritative post-market session audit for `2026-09-21` (Session ID: `meg-live-2026-09-21-a4e1fd4fc790-832ef03f93f6`) established:
1. **`DEPTH_PERSISTENCE_COMPLETENESS = FAIL`**:
   - `7,060` depth snapshots were rejected with `QUEUE_REJECTED` and dropped from persistence.
   - Causal tracing confirmed: The SQLite persistence batch worker was starved due to lock contention on the process-global `_SQLITE_TRANSACTION_LOCK` and frequent WAL checkpointing during high-frequency tick ingestion (5.82M ticks).
   - Pruning query duration was measured on disk WAL at ~10ms, disproving it as the primary cause, while concurrent write transactions under the process lock caused latency spikes exceeding 1,175ms, directly triggering the 1.0s queue put timeout.
2. **`DUPLICATE_INTERVAL_DATA_LOSS = NO` (Cardinality Reconciled)**:
   - Exactly `5,022` bridge calls were made.
   - Reconciled to: `29` exported 1-minute intervals + `4,744` duplicate interval queries + `249` startup/misaligned sync queries = `5,022` total invocations (`0` unaccounted).
   - Log severity was defective: Expected polling cadence mismatch (1-second runner vs. 1-minute bars) was logged as a `WARNING` anomaly.
3. **Morning Autonomous Launcher Blockers**:
   - Orchestrator failed to propagate `MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE` and `MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH` to child MROS process.
   - Orchestrator included BSE SENSEX token 265 in `ws_tokens` and `produce_authority`, but `fetch_current_instruments` only queried `("NSE", "NFO", "BFO")` (omitting BSE), causing an authority validation failure.

---

## 2. Invariant Contracts

### Invariant 1: Depth Ingestion Bounded Accounting Invariant
For any interval $[t_0, t_1]$ and across any process lifecycle:
$$\text{ENQUEUED} = \text{PERSISTED} + \text{CURRENTLY\_QUEUED} + \text{EXPLICITLY\_REJECTED}$$
- Every drop or rejection must increment a monotonic counter and emit a cryptographically bound provenance row in `depth_rejections.jsonl`.
- There must be **zero unexplained remainder**.

### Invariant 2: Hot Ingestion Decoupling Invariant
- The WebSocket ingestion callback thread (`kite_depth_ws`) must **never** execute disk I/O, synchronous SQLite transactions, or unbounded locks.
- Maximum callback queue put timeout must be fail-closed but non-stalling ($\le 50\text{ ms}$). If the persistence subsystem falls behind, backpressure must be explicitly tracked without blocking the live WebSocket event loop.

### Invariant 3: Retention Isolation Invariant
- Storage pruning (`DELETE FROM depth_snapshots ...`) must never execute synchronously within `insert_depth_snapshots_batch()` on the critical write path.
- Pruning is exclusively owned by a decoupled, low-priority retention worker or background timer with explicit throttling.

### Invariant 4: Bridge Interval State Machine & Semantic Disambiguation Invariant
For any completed index bar with timestamp $T_{\text{bar}}$ and previous exported interval $T_{\text{last}}$:
1. **$T_{\text{bar}} > T_{\text{last}}$**: Advance interval $\rightarrow$ `NEW_INTERVAL_ACCEPTED`. Export metadata row.
2. **$T_{\text{bar}} == T_{\text{last}}$**: Poll cadence unchanged $\rightarrow$ `IDLE_UNCHANGED_INTERVAL`. Return `attempted=False, exported=False, reason="IDLE_UNCHANGED_INTERVAL"`. Logged strictly at `DEBUG`, incrementing `telemetry.idle_interval_polls`. Zero WARNING logs.
3. **$T_{\text{bar}} < T_{\text{last}}$**: Invariant violation $\rightarrow$ `TIME_REGRESSION`. Logged at `ERROR`, incrementing `telemetry.time_regression_faults`.

### Invariant 5: Autonomous Child Process Environment Propagation Invariant
- `GovernedMorningOrchestrator` must deterministically assemble and inject all governed runtime variables into the child environment:
  - `MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE=true`
  - `MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH=<canonical_universe_path>`
  - `MARKET_EVENT_GRAPH_LIVE_SOURCE_PATH=<session_root>/captured_metadata.jsonl`
  - `MARKET_EVENT_GRAPH_LIVE_LAUNCH_PLAN_PATH=<session_root>/launch_plan.json`
  - `FEED_FORENSICS_ENABLED=true`
  - `TRADEBOT_FEED_FORENSICS_ROOT=<session_root>`
- The child process must never fail preflight due to missing parent configuration.

### Invariant 6: BSE/SENSEX Token Authority Universality Invariant
- Every token declared in `ws_tokens` or `required_tokens` must exist with valid metadata in the instrument master fetched for the session date.
- `fetch_current_instruments` must fetch all exchanges represented in `ws_tokens` (specifically including `"BSE"` if BSE SENSEX token 265 is required, or explicitly scoped to NSE-only indices).

---

## 3. Component Architecture & Workflow Mapping

```
[WebSocket Client]
       │
       ▼ (in-memory dict write: <0.1ms)
[DepthStore.books]
       │
       ▼ (non-blocking / 50ms bounded put)
[_persist_queue (maxsize=32768)]
       │
       ▼ (batch pull: up to 100 items)
[Depth Persistence Worker Thread]
       │
       ├─────────────────────────────────┐
       ▼ (batched INSERT, WAL mode)      ▼ (asynchronous timer: every 60s)
[SQLite depth_snapshots table]     [Background Retention Worker]
                                         │
                                         ▼ (DELETE old rows throttled)
                                   [Pruned depth_snapshots]
```

### Detailed Refactor Boundaries:

#### A. `core/depth_store.py` & `core/trade_store.py`
1. **Dedicated Database / Decoupled Lock**:
   - Depth snapshots must not compete with tick store's `PRAGMA wal_checkpoint(TRUNCATE)` inside `_SQLITE_TRANSACTION_LOCK`.
   - Separate the database connection for depth persistence or use a dedicated database file (`depth.sqlite`) if transaction lock contention persists, or eliminate truncate checkpoints on the hot path.
2. **Remove Pruning from Write Batch**:
   - Remove `_should_prune_depth_snapshots()` from `insert_depth_snapshots_batch()`.
   - Implement `prune_depth_snapshots()` executed on a separate low-frequency maintenance interval.
3. **Exact Accounting Telemetry**:
   - Expose `persistence_accounting()` returning:
     - `enqueued_count`
     - `persisted_count`
     - `queue_depth`
     - `rejected_count`
     - `invariant_delta = enqueued - (persisted + queue_depth + rejected)` (must equal 0).

#### B. `core/market_event_graph_live_runtime_bridge.py`
1. Refactor interval check in `_assemble_snapshot`:
   ```python
   if self._last_source_bar_end_epoch is not None:
       if float(index_end) == float(self._last_source_bar_end_epoch):
           return None, "IDLE_UNCHANGED_INTERVAL", ()
       elif float(index_end) < float(self._last_source_bar_end_epoch):
           return None, "TIME_REGRESSION", ()
   ```
2. In `observe_cycle`:
   - If reason is `"IDLE_UNCHANGED_INTERVAL"`, log at `logger.debug` instead of `logger.warning`. Do not treat as an operational fault.
   - If reason is `"TIME_REGRESSION"`, log at `logger.error`.

#### C. `core/governed_morning_orchestrator.py`
1. Update `step_launch_observer`:
   - Inject required MROS environment variables into `env` passed to `subprocess.Popen(mros_cmd, env=child_env, cwd=...)`.
2. Reconcile BSE Exchange in `step_refresh_instruments`:
   - Include `"BSE"` in `fetch_current_instruments(client, exchanges=("NSE", "NFO", "BFO", "BSE"))` so token `265` (`SENSEX`) parses successfully.

---

## 4. Acceptance Gates (Stage 2 GSD Execution Criteria)

Before merging any GSD implementation PR:
1. **Gate 1 (Accounting Proof)**:
   - A property-based test must enqueue 50,000 synthetic depth snapshots under artificial lock delay and verify `enqueued == persisted + queued + rejected` with 0 unaccounted records.
2. **Gate 2 (Latency Proof)**:
   - WebSocket callback latency P99 must remain $< 5\text{ ms}$.
3. **Gate 3 (State Machine Proof)**:
   - A deterministic unit test verifies that cycling identical interval bars produces `IDLE_UNCHANGED_INTERVAL` at DEBUG level with 0 warning logs, while an out-of-order bar produces `TIME_REGRESSION`.
4. **Gate 4 (Orchestrator Env Proof)**:
   - Test verifies that `GovernedMorningOrchestrator.step_launch_observer` constructs a child environment containing all 6 required MROS variables.
5. **Gate 5 (Instrument Authority Proof)**:
   - Test verifies that `produce_authority` passes with `ws_tokens` containing BSE token 265 when BSE instruments are loaded.
6. **Gate 6 (Zero Order Action / Read-Only Safety)**:
   - All tests run with `read_only=true`, `is_order_action=false`, `broker_api_called=false`. Zero broker calls.
