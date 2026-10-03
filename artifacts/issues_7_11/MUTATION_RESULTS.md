# Mutation results

- Issue 9: incomplete cutoff (<60s) returns `SKIPPED_INCOMPLETE`; cross-session cutoff returns `SKIPPED_CROSS_SESSION_CUTOFF`; duplicate identical rows are idempotent; conflicting rows are rejected; replay provenance is not persisted; aborted SQLite insert leaves no row and database integrity remains `ok`.
- Issue 9: two store instances concurrently write the same completed row and produce one `INSERTED` plus one `EXISTS`. This is an adversarial concurrency test, not a process-kill crash test.
- Issue 9 fresh verifier sabotage: mutate only SQLite `ts_epoch` by -60s/+60s while retaining `ts_ist`, OHLCV, provenance, and row hash. Before repair, -60s admitted a 09:15 bar at 09:15:30 and `verify_integrity` passed. After repair, both directions raise `SessionMemoryConflict` on read and `verify_integrity` reports `timestamp_epoch_mismatch`; the regular valid-row reopen test remains green.
- Issue 9 neighbor sabotage: replace `ts_epoch` with nonnumeric text; `get_bars` raises `SessionMemoryConflict` and `verify_integrity` returns `FAIL` with an `invalid_epoch` failure.
- Issue 10: missing file, whitespace-only empty file, directory/read error, populated fallback, partial JSONL, append-during-read, same-size in-place rewrite, whitespace tail, U+2028 within JSON string, and overlong bounded-tail record are covered. Any detected descriptor change during read returns `READ_ERROR` with no accepted rows; a stable partial tail excludes only the raw unterminated fragment; a record with no boundary inside the configured tail is `TRUNCATED`, never `EMPTY`. EOD accepted-row parity remains unverified.
- Issue 11 shared feed classifier/candidate safety: baseline aggregate semantics are retained; no new dependency-scoped shared classifier exception remains. The exact candidate-level isolation claim is therefore open, and missing dependency identity remains UNKNOWN/blocking.
- Issue 11 shadow consumer: actual runtime producer envelope plus matching fresh NIFTY quote creates an `INDEX_SPOT` observation despite unrelated option-only aggregate degradation. Explicit global block, disconnected websocket, unsafe runtime, unknown spot domain, missing quote identity, token mismatch, bool/float/leading-zero/zero/negative token, and malformed wrapped `feed_ok` each remain degraded or produce no snapshot. Legacy direct decision payload behavior is retained. Adapter/replay tests pass; this changes only read-only shadow input normalization.
- Issue 9/11 observer timestamp sabotage: preserve a fresh book `ts_epoch` while moving `last_price_ts_epoch` 60 seconds stale; omit the LTP event timestamp; or move it into the future. The runtime observer test requires stale/unknown health and always `is_executable_quote=false`. A book timestamp cannot upgrade stale last-price evidence.
- Initial tail-cache attack exposed stale classification and was fixed; focused tests pass.
- At the initial baseline, actual code mutation harnesses deleting guards, Issue 7 validator/stager sabotage, Issue 8 source timestamp/parent sabotage, and all six scenario graph mutations had not been performed. See the dated reruns below: 17/17 represented targeted mutants were later killed, while the remaining matrix is still open. The persisted-data sabotage test strengthens Issue 9 defenses but does not close the overall mutation gate.

- Issue 8 targeted source-code mutation harness: `python3 scripts/verify_issues_7_11_issue8_mutations.py` → 6/6 targeted mutants killed. It deletes the expected-token-missing guard, fixed-underlying guard, exact-int checks at capture/persisted-row/event-payload boundaries, and source-event-ID type guard. The harness mutates isolated temporary copies and disables bytecode caching. This closes only these Issue 8 identity/type mutants; Issue 7, Issue 9/10/11 campaign-wide code mutations and scenario graph mutations remain unrun.

## Targeted code mutants — 2026-10-03 continuation

- Issue 7: `python3 scripts/verify_issues_7_11_issue7_mutations.py` — **3/3 killed** (wrong prior trading date, future available evidence, missing required field). Calendar/source staging mutants remain open.
- Issue 8: `python3 scripts/verify_issues_7_11_issue8_mutations.py` — **6/6 killed** (expected-token wildcard, fixed identity, exact token types, source event ID type). Parent/time/provenance mutants remain open.
- Issue 9: `python3 scripts/verify_issues_7_11_issue9_mutations.py` — **2/2 killed** (remove completion cutoff; remove immutable duplicate hash check). Baseline **2 passed**; checkout source/test hashes unchanged. Exact results: `ISSUE9_MUTATION_RESULTS_20261003.md`.
- Issue 10: `python3 scripts/verify_issues_7_11_issue10_mutations.py` — **2/2 killed** (disable in-place mutation detection; split on Unicode line separators). Concurrent writer atomicity remains unverified.
- Issue 11: `python3 scripts/verify_issues_7_11_issue11_loader_origin_mutations.py` — **1/1 killed** (remove canonical loader-origin assignment); the source-recognition mutation also failed two stale/malformed snapshot assertions. Candidate-isolation and full campaign mutations remain open.

These targeted harnesses are not a campaign-wide mutation score. Cross-issue graph mutations, all prompt-listed Issue 8 parent/provenance attacks, Issue 10 multi-process write behavior, and Issue 11 dependency-mapping mutations remain incomplete or UNKNOWN.

## Fresh existing-harness rerun — current worktree — 2026-10-03

At HEAD `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`, all eight present source-mutation harnesses were rerun sequentially; **17/17 targeted mutants were killed**:

- Issue 7: 3/3 (wrong prior trading date, future evidence, missing required field).
- Issue 8: 6/6 (expected-token wildcard, NIFTY identity, exact-token types at capture/persisted/event payload, source-event ID type).
- Issue 9: 2/2 (completion cutoff, immutable duplicate hash guard).
- Issue 10: 2/2 reader mutations and 1/1 shared-writer lock mutation.
- Issue 11: 1/1 loader-origin, 1/1 transport, 1/1 required NIFTY spot gate.

All eight runners returned exit code 0; harnesses that report checkout SHA checks confirmed unchanged checkout files. Separately, a temporary-copy removal of `is_order_action` from the shared CAS authority tuple was killed by the PASS-path test and by the stale-PENDING test. Each test failure was the expected missing-key assertion, and both checkout source/test byte comparisons remained unchanged.

This remains targeted partial mutation evidence. It does not execute the prompt's complete mutation matrix: Issue 7 exchange-calendar/holiday and staged-source attacks; Issue 8 competing/corrupt/future parents and timestamp/provenance attacks; Issue 9 all interval/session/crash/replay mutations; Issue 10 all mirror/path/duplicate/external-writer variants; Issue 11 candidate-dependency mapping, candidate-builder suppression, and latch recovery variants; or all six cross-issue scenario mutations. Overall campaign-wide mutation closure remains open.


## Abrupt process termination — 2026-10-03

The Issue 9 store test module now includes `test_process_death_before_store_context_commit_rolls_back_insert`. The child asserts the target row is present inside the uncommitted transaction before abrupt exit; the parent reopens the database and proves no row survived and SQLite integrity is `ok`. Command: `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/core/test_market_session_store.py::test_process_death_before_store_context_commit_rolls_back_insert tests/core/test_market_session_store.py` → **19 passed, 1 warning**. This addresses one transaction interruption point only; it is not an OS/power-loss, actual service restart, or campaign-wide mutation result.


## Crash-boundary mutation re-attack — 2026-10-03

Extended `scripts/verify_issues_7_11_issue9_mutations.py` with `commit_completed_bar_before_context_exit`, which inserts `conn.commit()` immediately after the real bar INSERT in an isolated source copy. The abrupt-process test fails when that mutant is applied because the row survives restart. The harness also reran the completion-cutoff and immutable-duplicate mutants: **3/3 killed**, with checked-out production/test hashes unchanged. Exact rerun: `PATH=/tmp/tradebot-test-python-bin:$PATH python3 scripts/verify_issues_7_11_issue9_mutations.py`; store tests: **19 passed, 1 warning**. The mutation covers one SQLite transaction boundary only; Issue 9 actual service restart and captured/live parity remain open.


Issue 7 explicit calendar edges — 2026-10-03

Added Monday-after-weekend and Wednesday-after-NSE-holiday predecessor cases against the existing explicit eligible-session resolver. A temporary mutant replacing latest eligible date selection with target-minus-one-calendar-day was killed independently by both edge cases. `PATH=/tmp/tradebot-test-python-bin:$PATH python3 scripts/verify_issues_7_11_issue7_mutations.py` → **5/5 killed** (three existing assembler mutants plus two calendar mutants); harness verifies both checked-out source and test hashes are unchanged. Full heritage graph test file: **69 passed, 1 warning**. These cases verify resolver behavior only; external calendar completeness and T-1 futures source authority remain UNKNOWN.

## Issue 11 registry identity coverage — 2026-10-03

`PATH=/tmp/tradebot-test-python-bin:$PATH python3 scripts/verify_issues_7_11_issue11_registry_identity_mutation.py` → **2/2 killed**. Separate isolated mutants remove `REGISTRY_REQUIRED_DOMAIN_IDENTITY_COVERAGE_MISMATCH` from validation or remove the matching-coverage guard from `execution_eligible`; each must hit its named assertion sentinel, so unrelated test failures cannot be counted as killed mutants. Added empty, whitespace-only, and padded identity cases. Focused suite: **61 passed**. Checked-out source SHA-256 `07de4dafa4e79d40b269d479ec806154ae9d8cef2072bac579bb490d64e23014`; test SHA-256 `4bdef3f55db6ff7f949670d90bca894bc21b57ada6a13fb4812a18e28b092799`; both unchanged by the temporary-copy mutants. This proves malformed registry identity declarations only, not runtime identity health or full Issue 11 isolation.


## Current-source reattack addendum — 2026-10-03

All currently available Issues 7–11 targeted mutation harnesses were rerun sequentially: **23/23 killed**, comprising Issue 7 5/5, Issue 8 6/6, Issue 9 3/3, Issue 10 reader 2/2, shared writer lock 1/1, external-append rollback 1/1, Issue 11 CAS 1/1, loader 1/1, registry identity 2/2, and transport 1/1. The new Issue 10 mutation removes the conditional rollback and is killed by the injected uncoordinated append regression. This remains bounded targeted coverage, not the prompt-wide matrix. External-writer atomicity, captured/live parity, and full campaign acceptance remain open.

## PR-scoped current-source rerun — 2026-10-04

All 15 checked-in `scripts/verify_issues_7_11*.py` harnesses ran sequentially in the clean PR worktree and exited zero. They killed 27 targeted mutants: Issue 7 5/5, Issue 8 6/6, Issue 9 5/5 (MEG date boundary, crash commit, completion cutoff, immutable duplicate hash, same-process rollover), Issue 10 4/4 (read snapshot mutation, Unicode splitting, writer lock, external-append rollback), and Issue 11 7/7 (CAS dependency, loader origin, mixed-symbol scope, registry coverage 2, forced healthy symbol, transport OR).

This is the checked-in targeted mutation set, not the complete prompt attack matrix. It does not resolve external source authority, actual service/capture parity, Issue 11 dynamic candidate dependency identity, campaign-wide scenario mutations, hosted CI, or the still-open final campaign verdict.
