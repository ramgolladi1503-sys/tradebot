# V23 Production Path Parity

The A–K harness cases use the production `runtime_snapshot_producer`,
`CanonicalCycleCoordinator`, `run_consumer_cycle`, CAS evaluator, readiness
writer, and persisted artifact readers. Only temporary filesystem and clock
boundaries are controlled.

The L–N cases exercise the production coordinator and lifecycle boundaries,
including recovery deduplication and lifecycle-owned sink shutdown behavior.
Therefore:

```text
HARNESS_USES_PRODUCTION_IMPLEMENTATIONS=true
HARNESS_PRODUCTION_PATH_PARITY_PASS=true
FIRST_UNPROVEN_EDGE=NONE
```
