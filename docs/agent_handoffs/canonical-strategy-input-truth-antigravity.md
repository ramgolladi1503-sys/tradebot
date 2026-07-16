# Canonical Strategy Input Truth Handoff

## Handback Payload

```text
IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

EVIDENCE STATUS:
BROKEN

OVERALL VERDICT:
CANONICAL_STRATEGY_INPUT_TRUTH_BROKEN
```

## Branch Information
- **worktree:** /Users/madhuram/.antigravity/worktrees/tradebot/canonical-strategy-input-truth-audit
- **branch:** ag/canonical-strategy-input-truth-audit
- **base SHA:** 4235c012
- **final SHA:** (pending commit)
- **remote SHA:** 4235c012
- **local/remote match:** false
- **clean status:** dirty
- **PR opened:** false
- **merged:** false

## Layer Matrix

| Layer | Actual Active Owner | Runtime/Replay/Legacy | Test Name | Test Result | Verdict | Confirmed Defect |
|---|---|---|---|---|---|---|
| Tick Normalization | `core.feed.tick_utils` | ACTIVE_RUNTIME | `test_timestamp_truth_out_of_order` | PASSED | PROVEN | None |
| Timestamp Substitutions | `core.feed.tick_utils` | ACTIVE_RUNTIME | `test_timestamp_truth_option`, `test_timestamp_truth_delayed` | PASSED | PROVEN | None (but relies heavily on receipt substitutions) |
| Symbol Mapping | `core.ohlc_buffer` | ACTIVE_RUNTIME | `test_missing_minute_and_symbol_mixing` | PASSED | PROVEN | None |
| Completed-Bar Construction | `core.ohlc_buffer` & `core.market_data` | ACTIVE_RUNTIME | `test_completed_bar_delivery_market_data` | XFAIL | BROKEN | `market_data` passes the active forming bar directly to indicators and downstream strategies |
| Late-Tick Handling | `core.ohlc_buffer` | ACTIVE_RUNTIME | `test_ohlc_buffer_cases` | PASSED (asserts defect) | BROKEN | Late ticks arriving for an older bucket are appended to the end of the buffer, permanently breaking time-order |
| Duplicate Ticks | `core.ohlc_buffer` | ACTIVE_RUNTIME | `test_ohlc_buffer_cases` | PASSED | UNKNOWN | Volume is passed as `None` from the live feed, so double-counting does not manifest. |
| Missing Minute Classification | `core.ohlc_buffer` | ACTIVE_RUNTIME | `test_missing_minute_and_symbol_mixing` | PASSED | UNDEFINED | No explicit classification or gap count is maintained |
| Indicator Causality | `core.indicators_live` | ACTIVE_RUNTIME | `test_indicator_authoritative` | PASSED | PROVEN | Zero volume correctly triggers fallback to 1 to prevent division errors, but is completely a FALLBACK behavior |
| Strategy Invocation Causality | `core.execution_core_fast` & `core.market_data` | ACTIVE_RUNTIME | `test_orchestrator_invocation_proof` | XFAIL | BROKEN | Active forming minute bleeds directly into the strategy payload via `OhlcBuffer` |

## Corrected Findings vs Previous Audit
- **LiveBarBuilder** was discovered to be completely DEAD code (no callers in production or replay). Its supposed defects (duplicate volume counting) were discarded as not applicable to the runtime.
- **OhlcBuffer** was identified as the active runtime bar producer. Testing revealed it safely handles duplicate ticks when `volume=None`, but severely corrupts time order if a tick arrives late for a previous bucket.
- **Forming Bar Bleed** was identified as the most critical defect: `market_data.py` does not filter out the actively forming bar from `OhlcBuffer`, meaning strategies receive incomplete, non-causal data for the current minute.

## Recommended Next Actions
- Truncate the final forming bar dynamically inside `market_data.fetch_live_market_data()` before it reaches `compute_indicators()`.
- Add a strict chronological lock inside `OhlcBuffer` to reject or explicitly handle late ticks rather than blind-appending them.
