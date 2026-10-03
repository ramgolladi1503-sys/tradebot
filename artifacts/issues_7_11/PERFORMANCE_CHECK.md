# Performance and resource check

- Issue 10 advisory source-state work remains on bounded snapshot reads; no market tick or broker path is involved.
- Issue 9 persistence/restoration was inspected at its actual caller: `record_live_source_shadow_tick` runs from `kite_depth_ws`'s `on_ticks` callback. SQLite reads/writes were removed from that callback. Startup restores bars before `lifecycle.start`; the observer completed-bar read path persists them. A regression asserts the DB is empty after callback-only updates and populated after the completed-bar observer read.
- Bounded local temp-DB measurement (100 immutable 1m rows): write total 37.493 ms; startup restore 3.829 ms; 100 repeated completed-bar reads 15.642 ms total / 0.1564 ms per call. This is a local microbenchmark, not production latency evidence.
- Runtime buffer is bounded by `OHLC_BUFFER_MAX_BARS` (default 500); persistence database is stored under the governed session-date parent and keyed by session date, symbol, interval, and epoch. Same-date history bounds the per-symbol restore result.
- No live profiling or multi-process production contention measurement was performed. The database uses SQLite WAL, FULL synchronous mode, and a 30-second busy timeout; storage contention still fails closed and must be measured in deployment evidence before any live-readiness claim.

## 2026-10-04 Issue 11 homogeneous score-scope check

`core.ranking_orchestrator._homogeneous_scoring_symbol` performs one linear pass over an existing score tuple before the normal ranking call; it adds no I/O, locks, feed subscription work, or mutable cache. Local `timeit` microbenchmark (1,000 calls/sample, 5 repeats; median total divided by calls, current Python 3.14 runtime): 1 row 0.305 µs/call, 123 rows 16.320 µs/call, 1,000 rows 126.817 µs/call, 10,000 rows 1,257.971 µs/call. This demonstrates linear local helper cost and is not a whole-pipeline or production latency measurement.
