# GSD MAP → SPEC → PLAN — Issue 9

## Re-attack addendum — timestamp identity

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE
**requested_paths:** `core/market_session_store.py`, `tests/core/test_market_session_store.py`, `core/candidate_feed_dependencies.py`
**allowed_paths:** the requested paths plus Issue 7–11 evidence artifacts
**forbidden_paths:** broker/order/risk/feed runtime, strategy thresholds, credentials, token-universe configuration
**expected_tests:** valid timestamp round-trip; epoch shifted earlier causes read rejection before as-of filtering and integrity failure; epoch shifted later causes read rejection and integrity failure
**acceptance_proof:** the forged row cannot enter `get_bars` or `build_context`, `verify_integrity` is FAIL, valid rows still pass, source digest pin matches exact store bytes.

1. In `_load`, recompute timestamp/row hash and compare stored `ts_epoch` with normalized epoch before returning or caching any row.
2. In `verify_integrity`, independently compare timestamp-derived epoch with stored epoch and report a specific mismatch.
3. Add temporary-SQLite tamper tests for earlier and later epoch shifts with unchanged `row_hash`.
4. Refresh the candidate dependency digest only after implementation is final, then run the focused store/bridge/advisory integration tests and source-registry gate.

### Neighbor attack plan — malformed epoch column value

1. Treat conversion of `ts_epoch` as untrusted persisted input in `_load`; translate conversion failure to `SessionMemoryConflict` with a stable reason.
2. Move epoch conversion inside `verify_integrity`'s row guard so nonnumeric values produce `invalid_row` and overall `FAIL` rather than escaping the verifier.
3. Add a temporary SQLite sabotage test that writes TEXT into the epoch column without changing the remaining row and asserts both paths fail closed.
4. Refresh the exact source digest; rerun store, MEG, registry and symbol-safety suites.

## MAP

The live MEG observer owns a `shadow_ohlc_buffer` separate from the strategy/execution OHLC buffer. It currently loses all bars at process exit. `MarketSessionStore` already has immutable keyed SQLite rows and as-of reads, but currently coerces unknown volume to zero and does not hydrate the MEG buffer.

## SPEC

Persist only finalized same-session 1m live bars in a session-date database under the governed date root. Persist before mutating the in-memory buffer on the first tick in a later minute. Restore only when `bar_start + 60s <= source_event_time` and session date equals requested session. Preserve unknown volume as null. Restored provenance is marked as recovered evidence and cannot satisfy current feed-session/epoch subscription proof. Replay fixtures and non-live fallback bars are excluded. A conflict/corrupt store is explicit and fail closed for restoration.

## PLAN

1. Extend store schema to nullable volume with safe migration and tests; update the pinned source digest without changing any candidate execution eligibility.
2. Add session-specific configuration and store restoration/persistence helpers to the isolated shadow-buffer module; leave generic strategy OHLC global buffer memory-only.
3. Configure it from observer session identity before lifecycle feed start, using `output_root.parent` only after same-device/contained-storage validation.
4. Require `completed_as_of` at the store boundary and reject writes before `bar_start + 60s <= completed_as_of`.
5. Add adversarial restart, current-bar exclusion, duplicate/concurrent retry, conflict, corruption, aborted-write, identity-reset and replay-exclusion tests.
6. Re-run Issue 9 + Issue 10 focused suites, the C1/C2 memory certification, source-hash registry tests, and inspect the diff for forbidden surface changes.

## Acceptance and blocked edges

This does not establish Issue 8 CAS reconstruction. It does not make restored bars eligible for current feed/MEG bridge provenance. Concurrent identical writes are idempotent; conflicts and incomplete bars fail closed. If store identity cannot be safely tied to trading date or storage authority, do not enable writes; report blocked.
