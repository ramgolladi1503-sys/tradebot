# Phase 8: Telemetry and Observability Report

## Enhancements Implemented
The Market Intelligence Platform now integrates safely with standard TradeBot observability patterns via `MIPTelemetry` (`core/intelligence/telemetry.py`).

1. **Structured JSONL Sink**: All intelligence lifecycle events are logged to a unified `logs/mip_telemetry.jsonl` pipeline, allowing downstream systems (e.g., Datadog, Splunk) to ingest the traces.
2. **Explicit Metadata**: Every emitted event automatically injects `timestamp`, `event_name`, and fundamentally enforces `"advisory_only": True`.
3. **Event Granularity**: The telemetry class has strict wrappers:
   - `emit_fetch_event()`: Tracks source health, circuit breaker trips, robots blocks, and fetch latency.
   - `emit_extraction_event()`: Tracks parse success, duplicate hash dropping, and extraction failures.
   - `emit_storage_event()`: Safely registers that the event survived extraction and was successfully persisted.
   - `emit_calibration_event()`: Tracks offline replay outcomes (mostly `INSUFFICIENT_EVIDENCE` dumps).
   - `emit_integration_event()`: Tracks successful candidate metadata injections via `ContextAdapter`.
4. **No Console Noise**: Standardizes the `logger.info()` strings while keeping the heavy JSON parsing to file I/O, ensuring the trading hotpath isn't spammed with long string concatenations.
