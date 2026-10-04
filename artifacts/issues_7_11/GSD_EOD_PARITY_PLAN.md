# GSD Plan — Issue 10 EOD Decision-Ledger Parity

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Verify observer decision-ledger parity through advisory and EOD telemetry
**scope:** deterministic offline test only
**requested_paths:** `tests/analytics/test_issues_7_11_eod_row_parity.py`
**allowed_paths:** requested test path and the Hermes/GSD evidence artifacts
**forbidden_paths:** runtime wiring, broker/order/risk/feed code, strategy semantics, token universe, credentials, live configuration
**expected_tests:** focused integration and full analytics test suite
**acceptance_proof:** exact advisory IDs, exact EOD source path/hash/count, zero malformed records, zero trade-intent events

## Execution

1. Create one session-local `candidate_decisions.jsonl` with two valid advisory-only rows.
2. Point the advisory producer at that exact ledger and verify the converted row IDs.
3. Build a session-scoped daily report from the same directory.
4. Verify the EOD diagnostic source path, SHA-256, row count, and malformed count against the ledger bytes.
5. Verify the decision rows do not become trade-intent events.
6. Run `pytest -q tests/analytics` as required by the analytics guardrails, then `git diff --check`.

No production implementation is changed because the existing diagnostic reader already exposes the necessary source provenance. A failed test must be treated as a real contract gap and returned to Hermes for design before runtime changes.
