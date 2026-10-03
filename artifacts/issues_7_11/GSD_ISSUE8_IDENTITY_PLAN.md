# GSD Plan — Issue 8 Persisted CAS Identity Validation

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH
**title:** Reject non-NIFTY persisted CAS primitives
**scope:** offline CAS primitive verifier boundary
**allowed_paths:** `core/cas_primitive_producer.py`, `tests/test_cas_primitive_producer.py`, this plan, Hermes contract, Issue 7–11 evidence artifacts
**forbidden_paths:** broker/order/risk/feed runtime, credentials, strategy logic, token universe, live/paper authority
**expected_tests:** baseline NIFTY row accepted; wrong-symbol row rejected even after every content hash and ID suffix is recomputed
**acceptance_proof:** reproduced prior acceptance, exact identity rejection, complete focused CAS suite green

## Execution

1. Add the fixed NIFTY symbol check to persisted primitive verification.
2. Keep event payload, token, timestamp, source hash, and source-ID binding checks intact.
3. Add a self-consistent wrong-symbol mutation test to prevent a hash-only false sense of identity.
4. Run the CAS producer tests and record the exact result.
5. Keep historical Issue 8 source-event/restart authority `UNKNOWN`.
