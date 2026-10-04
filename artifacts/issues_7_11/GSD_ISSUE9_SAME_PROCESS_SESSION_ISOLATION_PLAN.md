# GSD Plan — Issue 9 same-process session isolation

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Keep prior-session process-local bars out of current-session memory
**scope:** `docs/agent_reviews/issues_7_11_hermes_issue9_same_process_session_isolation.md`

## Baseline / reproduction

Hermes reproduced `get_completed_bars()` returning 2026-09-07 local bars when `as_of` was 2026-09-08, because the method merged an unfiltered local buffer with a session-scoped store result. The exact deterministic fixture must first fail on current behavior.

## Execution

- Add a runtime bridge regression with the explicit bridge installed, trusted deterministic ticks across two IST dates, and exact returned timestamps. Assert prior-session bars remain available from the store when queried by their explicit session date.
- Extend the fresh-store-reopen assertion to verify supported 5-minute bars derive exactly from persisted 1-minute rows; keep 1-minute storage canonical.
- Filter the local and durable source rows to `as_of`’s IST date before merging; retain sorting and existing store errors. Do not clear the buffer.
- Add a temporary-copy mutation that removes the local date filter; require failure at the exact returned timestamp-set assertion.
- Update the graph, attack/repair ledgers, invariant matrix, independent verification, and final verdict with the bounded result and limitations.

## Forbidden changes

No bar semantics, persistence schema, current feed freshness, strategy/CAS thresholds, ranking, token universe, calendar, configuration, risk, execution, broker/order, or live paths.

## Acceptance

The RED test must reproduce cross-date carryover. The fixed path must return exactly the current-date completed bars, retain explicit prior-date store access, pass runtime bridge/store tests, and kill the specific date-filter removal mutant. Broad tests establish offline repository regression only; managed service and captured/live parity remain separate UNKNOWN gates.

## Safety and rollout

Read-only memory-view change. No config keys, migration, runtime authority, broker/order calls, or live rollout. No rollout is authorized from this offline evidence.

## Execution record

The date-leak regression failed before repair with three prior-session rows in the D+1 view and passed after. The local-filter-only mutation was killed at the exact timestamp-set assertion with unchanged source/test hashes. IST-aware UTC and naive-as-IST helper cases pass. Fresh reopen derives exact 5-minute bars from persisted 1-minute history. Current Issue 9 bridge/store suite: 33 passed, 1 warning. Fresh independent read-only review found no P1/P2 issue and its P3 coverage note was resolved. Exact-source broad offline regression passed 8736 tests (9 skipped, 29 deselected); final test-only additions were separately covered in the focused suite. Updated Feed Smoke passed 18 tests (5 deselected) with isolated /tmp paths. Actual service/captured-live parity remain UNKNOWN.
