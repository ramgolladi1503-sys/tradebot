# GSD Plan — Issue 9 MEG shadow-buffer session boundary

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Bound MEG shadow completed-bar reads to the requested IST session date
**scope:** `docs/agent_reviews/issues_7_11_hermes_issue9_meg_session_boundary.md`

## Baseline / reproduction

The MEG completion helper rejects persistence if its requested cutoff date differs from configured `_SESSION_DATE`, then returns all completed bars from the process-local shadow buffer. Reproduce two prior-date bars leaking into a D+1 observer view before changing production code.

## Execution

- Add a deterministic D-to-D+1 test against the real `shadow_ohlc_buffer` with session storage disabled; assert only current-date completed rows are returned and the local buffer retains its contents.
- Normalize `as_of` and each bar timestamp to IST in the completed-bar read helper and filter returned rows by the local date.
- Add a temporary-copy mutation that removes only this output filter and requires the exact timestamp assertion to fail.
- Update Issue 9 graph, ledgers, invariant matrix, independent verification, and final verdict.

## Forbidden changes

No subscription/feed state, data acquisition, OHLC construction, persistence, strategy, CAS, ranking, risk, execution, broker/order, or live behavior changes.

## Acceptance

RED reproduction; bounded read fix; local buffer not mutated; targeted MEG runtime tests and root-cause-specific mutation pass. This closes only an offline observer session-boundary gap, not deployment/live parity.

## Execution record

The actual pre-fix D-to-D+1 observer test failed with two prior-date bars; after filtering, it returns only the current completed bar and preserves the original shadow buffer. The focused MEG buffer/runtime bridge suite passed 45 tests; the output-filter-only mutant was killed at the exact timestamp-set assertion with unchanged hashes. Independent review found no P1/P2 issue and verified persistence ordering and IST conversion. Exact-source broad offline regression passed 8740 tests (9 skipped, 29 deselected). Updated Feed Smoke passed 18 tests (5 deselected). Managed-service and captured/live parity remain UNKNOWN.
