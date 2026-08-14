# Final architecture repair root-cause groups

## Group 1: runtime canonical fixture contract drift

Affected tests: the three `tests/test_runtime_health_snapshot_authority.py` failures.

The candidate correctly routes runtime health through `load_current_feed_runtime()`. The test payloads omit required session, writer, schema, epoch, produced-at, and lineage fields, so they are rejected before the assertions. Restoring raw fallback would violate M9. The minimal repair is to update the test fixtures in a separately scoped test-contract change; no source repair is justified here.

## Group 2: Phase 2 canonical-currentness fixture drift

Affected tests: the 32 `tests/test_engine_phase2_adapter.py` failures listed in the classification CSV.

The candidate rejects Phase 2 inputs when no current canonical feed artifact exists. These tests construct candidate mappings without a canonical runtime fixture and expect pre-M9 behavior. The minimal repair is a governed offline fixture/adapter setup that supplies a valid canonical artifact, without bypassing validation. No test-specific source bypass is safe.

Candidate-caused source root causes reproduced: none. The failures are contract-test fixture drift, not evidence that raw currentness should be restored.
