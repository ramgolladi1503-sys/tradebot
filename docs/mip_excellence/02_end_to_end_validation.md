# Phase 17: End-to-End Validation Report

Tracing the exact data lineage from network edge to core advisory context.

1. **Storage & Telemetry**: Initialized temporary SQLite WAL DB and structured JSONL sink.
2. **Source & Fetch**: Simulated HTTP fetch. Registered in DB run_id: `1`. Emitted `fetch_succeeded` telemetry.
3. **Extraction**: SEBIExtractor parsed title: `F&O Margin Rules` with parser version `1.0.0`.
4. **Validation & Persistence**: Document and Event safely persisted to SQLite. `advisory_only=1` explicitly enforced.
5. **Replay Engine**: Evaluated event against historic `tick_store`. Correctly returned: `INSUFFICIENT_EVIDENCE`.
6. **Advisory Context**: ContextAdapter injected intelligence. Final candidate `execution_ok` status remains: `False`. System absolutely isolated.

**Telemetry traces captured during loop**: 5
