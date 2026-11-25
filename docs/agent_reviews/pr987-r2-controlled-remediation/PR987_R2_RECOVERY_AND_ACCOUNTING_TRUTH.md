# PR987 Round 2 — Recovery and Accounting Truth

## Position quantity and PnL semantics

The scoped repository contains no authoritative broker execution/fill source used by `ActivePositionManager`. Consequently, spot or bar target touches cannot establish that an order filled or that any contracts were sold. The manager now records a distinct `runner_target_reached` projection state. It preserves the existing runner stop/trailing mechanics, but does not set `half_booked`, decrement `remaining_lots` or `remaining_quantity`, write tranche fill prices/timestamps, calculate tranche realized PnL, or represent the current option mark as an execution. `actual_quantity_status` is `UNKNOWN_NO_FILL_SOURCE`; option PnL values are explicitly marked as `MARK_PROJECTION`.

Legacy WAL payloads that contain `half_booked=True` are migrated to the advisory target-reached state. Legacy tranche prices, tranche PnL, and computed remaining quantities are discarded because no fill evidence supports them. Planned `lots` and `total_quantity` remain available as plan metadata; they must not be interpreted as current confirmed inventory.

Partial-fill event tests are `NOT_APPLICABLE`: an authoritative read-only fill source was not found, and this remediation does not create one. Duplicate target touches and repeated advisory liquidation are tested. No exchange-side exactly-once execution guarantee is made.

## WAL durability and uncertainty

APM WAL persistence now serializes writers within one manager instance using an `RLock`, writes a unique temp file, flushes it, fsyncs the file, atomically replaces the prior path, and fsyncs the parent directory for `force_sync=True`. Forced write, flush, file fsync, replace-before, and post-replace directory fsync failures are surfaced; the in-memory manager becomes `RECOVERY_BLOCKED`. A post-replace directory fsync error means the new directory entry's durability remains uncertain even though replacement occurred.

`force_sync=False` retains a one-second best-effort debounce. Calls inside that interval can be skipped; they are not durable checkpoints. The implementation does not support multiple process writers to one APM WAL. In-process serialization is not a cross-process lock. Existing OR reconciliation ledger locking/fsync is separate and confers no guarantees on the APM WAL.

On restart, active, armed, exit-pending, malformed, corrupt, or inconsistent WAL evidence is not converted to normal `STANDBY`, and any readable position is preserved in `RECOVERY_BLOCKED`. Entry admission rejects this state. The code does not auto-liquidate an uncertain recovered position because a target/mark is not a verified fill or broker position snapshot.

## Opening-range provenance

`seed_opening_range_evidence` always stamps synthetic provenance, irrespective of caller-supplied labels or coverage. Live validation requires a process-local trusted proof marker set only after the existing normalized 30-candle validator and durable completion-proof path succeed or a persisted proof is revalidated on restore. Reset/rollover invalidates that marker. The live decision still uses the existing exact session coverage and OHLC validation; strategy levels and equations are unchanged.

## Streaming reconciliation

The post-opening spot update and five-minute bar close enqueue immutable request context into a capacity-one nonblocking queue. A worker performs the existing retry/ledger/HTTP work outside the stream lock. Response application checks session, request identity, captured generation, and shutdown state. Same-session duplicate enqueue attempts are suppressed. The existing durable retry reservation and cap remain in place. Worker shutdown invalidates in-flight work; late responses are discarded. The separate regression report's old claim that HTTP already ran outside the streaming lock was contradicted by the prior exact-source reproduction; the new event-driven tests exercise both live entry routes.

## Raw and eligible market history

`bars_5m_history` stores raw validated-timestamp observations for chart/audit use. `bars_5m_strategy_history` stores only bars that pass ground-truth and OR validation; pattern and range inputs read this eligible history. Session reset clears both. Rejected earlier observations are not backfilled into strategy history when OR evidence later becomes valid. A late-OR test verifies that only subsequent qualified bars enter strategy history.
