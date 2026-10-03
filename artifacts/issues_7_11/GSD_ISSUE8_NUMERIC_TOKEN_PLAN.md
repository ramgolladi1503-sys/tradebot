# GSD Plan — Issue 8 Strict Numeric Token Identity

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH
**title:** Reject non-integer and non-positive CAS instrument tokens
**scope:** offline CAS producer/verifier boundaries
**allowed_paths:** `core/cas_primitive_producer.py`, `tests/test_cas_primitive_producer.py`, `tests/paper_shadow/test_issue11_scenarios_cd.py`, `scripts/verify_issues_7_11_issue8_mutations.py`, this plan, Hermes contract, and campaign evidence artifacts
**forbidden_paths:** broker/order/risk/feed runtime, credentials, strategy logic, token-universe configuration, live/paper enablement
**expected_tests:** malformed token types, non-positive values, and missing expected token reject without exception; valid integer token remains accepted; read-only producer metadata is asserted
**acceptance_proof:** reproduced bool/int equality bypass is killed by the verifier test and focused CAS/Scenario C-D tests pass

## Execution

1. Require exact positive integers at expected-token, input-tick, event-payload, and persisted-row boundaries; `None` is not a wildcard.
2. Preserve exact source hash and event identity checks.
3. Parameterize adversarial boolean/float/string/zero/negative tokens for capture and persisted verification.
4. Assert the actual feed-health producer's read-only, non-order, non-append metadata in Scenario C/D tests.
5. Keep a repeatable isolated temporary-copy mutation harness and require each mutant to fail at its targeted test.
6. Run focused suites and leave historical source authority UNKNOWN.
