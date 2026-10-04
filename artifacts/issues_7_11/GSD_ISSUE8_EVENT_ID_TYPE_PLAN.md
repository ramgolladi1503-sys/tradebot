# GSD Plan — Issue 8 Source Event ID Type Validation

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH
**title:** Fail closed on malformed CAS source event IDs
**scope:** offline CAS primitive producer/verifier boundary
**allowed_paths:** `core/cas_primitive_producer.py`, `tests/test_cas_primitive_producer.py`, this plan, Hermes contract, Issue 7–11 evidence artifacts
**forbidden_paths:** broker/order/risk/feed runtime, credentials, strategies, live/paper authority, historical evidence
**expected_tests:** malformed IDs do not raise; capture stays non-captured; verifier rejects; valid event binding remains accepted
**acceptance_proof:** targeted CAS tests plus source dependency validation; Issue 8 historical authority remains `UNKNOWN`

## Execution

1. Add explicit string/non-empty validation before any event-ID suffix operation in both boundaries.
2. Keep failure behavior fail-closed and preserve existing valid ID semantics.
3. Add tests for absent, empty, integer, boolean, and object values in ingestion and persisted verification.
4. Run the focused producer suite and check registered source digests if this source file is pinned.
5. Update the campaign graph and verdict only with observed results; do not promote synthetic tests to historical runtime proof.
