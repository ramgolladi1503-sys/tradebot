# Hermes Stage 1 — Issue 9 same-process session isolation

**source_agent:** hermes
**action:** DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS
**title:** Prevent process-local completed bars from crossing session dates
**scope:** `core/market_session_memory_contract.py` and focused Issue 9 runtime bridge tests only. Repository SHA `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`.

## Reproduction and root cause

With the persistence bridge installed, feed two trusted completed bars on 2026-09-07 and then a tick on 2026-09-08 into the same `OhlcBuffer`. Calling `get_completed_bars(..., as_of=2026-09-08 09:16 IST)` returns the two prior-session bars plus the current-session bar. `MarketSessionStore.get_bars()` already queries only the `as_of` date; the leak comes from merging the unfiltered process-local `original_completed()` result into that date-scoped durable result.

This is a repository-reproducible Issue 9 defect: a long-lived process can carry a previous session’s tail into the next session’s strategy memory. It is independent of whether the historical capture has sufficient source authority.

## Contract

For the durable-bridge `get_completed_bars` path, return only completed bars whose timestamp, converted to the runtime’s IST timezone, has the same local date as `as_of`. Apply this to both local-buffer and durable-store rows before merging. Do not mutate or clear the underlying OHLC buffer; the change bounds the returned causal view only. Preserve completion cutoff, ordering, provenance, store-error fail-closed behavior, freshness gates, and all strategy semantics.

No store schema, config, bar construction, volume logic, market calendar, token universe, feed state, strategy threshold, candidate policy, risk, execution, broker, or order behavior may change. Historical inspection remains available through the existing explicit store date APIs; this runtime bridge method is the current-session strategy view.

## Acceptance gates

1. Reproduce RED using the real bridge installation and actual `OhlcBuffer` with two completed bars on day D and a completed bar on D+1.
2. After repair, D+1 returns only D+1 bars; D history remains readable through an explicit store query.
3. Same-date local and durable rows continue to merge without duplication and remain ordered.
4. A boundary mutation that removes local session-date filtering fails at the exact day-isolation assertion.
5. Verify supported 5-minute history after fresh store reopen is derived from canonical persisted 1-minute rows; do not introduce a competing 5-minute persistence authority.
6. Run the full `tests/core/test_market_session_runtime_bridge.py` and `tests/core/test_market_session_store.py`, then exact-source broad offline regression. Do not infer managed-service or captured/live parity.

## Authority

Read-only history only. `broker_write_authority=false`, `order_authority=false`, `paper_authorized=false`, `live_authorized=false`. No orders, broker APIs, or live session are part of this proof.

## Rollback

Revert the session-date filter and its tests/evidence only. Do not reset, clean, or rewrite unrelated pre-existing worktree changes.

## Independent review follow-up

Fresh read-only review found no P1/P2 correctness issue and confirmed the filter matches the existing buffer’s IST handling. It identified a P3 coverage gap for aware non-IST and naive timestamps; direct assertions now cover UTC-to-IST same/next-date conversion and naive-as-IST. The sabotage was narrowed to removal of only the local-row filter, and that mutant is killed at the exact date-set assertion. Exact-source broad regression remains in progress.
