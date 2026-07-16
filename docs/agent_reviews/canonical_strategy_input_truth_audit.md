# Canonical Strategy Input Truth Audit

## Audit Metadata
- **Starting SHA:** 4235c012 (fix(feed): harden websocket reconnect freshness and resubscription)
- **Worktree:** /Users/madhuram/.antigravity/worktrees/tradebot/canonical-strategy-input-truth-audit
- **Branch:** ag/canonical-strategy-input-truth-audit
- **Scope:** Complete strategy input timeline (tick to orchestrator invocation)

## Canonical Owner Map
- **Tick Normalization:** `core.feed.tick_utils` (ACTIVE_RUNTIME)
- **Exchange/Receipt Timestamp:** `core.feed.tick_utils.normalized_tick_epoch` (ACTIVE_RUNTIME)
- **Symbol Mapping:** `core.instruments` and `core.instrument_symbols` (ACTIVE_RUNTIME)
- **One-Minute Bar Aggregation:** `core.ohlc_buffer.OhlcBuffer` (ACTIVE_RUNTIME) - Note: `LiveBarBuilder` is explicitly DEAD/LEGACY and not called anywhere in production runtime.
- **Late/Out-of-Order Handling:** `core.feed.tick_utils` and `core.ohlc_buffer.OhlcBuffer` (ACTIVE_RUNTIME)
- **Duplicate Ticks:** `core.ohlc_buffer.OhlcBuffer` (ACTIVE_RUNTIME)
- **Session/Timezone Truth:** `core.session_calendar` (ACTIVE_RUNTIME)
- **History-Window Production:** `core.market_data` (ACTIVE_RUNTIME)
- **Indicator Computation:** `core.indicators_live.compute_indicators` (ACTIVE_RUNTIME)
- **Orchestrator Strategy Invocation:** `core.execution_core_fast.FastExecutionCore` (ACTIVE_RUNTIME)

## Contracts Evaluated

### Timestamp Contract: PROVEN (with caveats)
Timestamps are evaluated by `normalized_tick_epoch`.
- Underlying ticks use the payload (exchange) timestamp.
- Option ticks default to using the receipt timestamp (`use_receipt_time_for_options=True`).
- Delayed payloads (lag > `max_payload_lag_sec`) are explicitly clamped to the receipt timestamp.
- Out-of-order payloads are successfully clamped forward to the `previous_epoch`.
- Result: Timestamp truth is structurally sound but exchange-time is heavily substituted with receipt-time for options and delays, influencing bucketing.

### Bar-Completion Contract (OhlcBuffer): BROKEN
`market_data.py` supplies the raw `ohlc_buffer.get_bars()` directly to the indicator function without excluding the forming bar. This means the incomplete 09:29 bar at 09:29:30 is explicitly passed as historical input to strategies.

### Late-Tick Policy: BROKEN
`OhlcBuffer` buckets bars based solely on `bars[-1]['ts'] == bucket`. If a late tick arrives from an older bucket (e.g. 09:28 arriving after 09:31 exists), it fails the `bars[-1]['ts']` check and is appended to the *end* of the queue, breaking chronological time order and corrupting the buffer.

### Duplicate Tick Invariance / Volume Semantics: UNKNOWN / NOT A DEFECT
The active runtime caller (`market_data.py`) passes `volume=None` to `OhlcBuffer`. The buffer semantics explicitly treat volume as incremental (`bar["volume"] += volume`), but since it receives `None`, volume remains 0. Double-counting volume is not a confirmed active runtime defect because volume is not actively utilized.

### Indicator/Context Contract: FALLBACK
`compute_indicators` generates VWAP, ATR, and ADX. When volume is missing or 0, it falls back to `1`. This is a FALLBACK behavior, not AUTHORITATIVE. Indicators correctly compute against the provided history, but because the forming bar is included, the cutoff is prematurely bleeding into the active minute.

### Missing Minute / Symbol Mixing: CONTRACT_UNDEFINED
`OhlcBuffer` safely isolates symbols into distinct lists. However, missing minutes (e.g., 09:17 absent between 09:16 and 09:18) are not synthetically filled or explicitly classified with gap counts or missing reasons. The contract is UNDEFINED.

### Orchestrator Invocation Contract: BROKEN
Because `market_data.py` passes forming bars, the actual payload given to the orchestrator (and thus strategies) includes the active forming minute. Strategies are receiving incomplete data, breaking the strict causal boundary.

## Tests Added
Created strict adversarial fixtures in `tests/core/test_canonical_strategy_input_truth.py`:
- `test_timestamp_truth_underlying`
- `test_timestamp_truth_option`
- `test_timestamp_truth_delayed`
- `test_timestamp_truth_out_of_order`
- `test_ohlc_buffer_cases` (proves late ticks break time order)
- `test_completed_bar_delivery_market_data` (XFAIL: proves forming bars bleed into strategies)
- `test_missing_minute_and_symbol_mixing`
- `test_indicator_authoritative` (proves fallback volume behavior)
- `test_orchestrator_invocation_proof` (XFAIL: proves strategy invocation payload includes forming bars)

## Confirmed Active-Runtime Defects
1. **Forming Bar Bleed:** `market_data` does not drop the forming bar from `OhlcBuffer`, causing incomplete bars to poison indicators and strategy payloads.
2. **Late Tick Append Corruption:** `OhlcBuffer` appends late historical ticks to the end of the buffer, permanently breaking chronological time order.

## Final Verdict
**CANONICAL_STRATEGY_INPUT_TRUTH_BROKEN**
The actual runtime strategy-input path (via `OhlcBuffer` and `market_data.py`) includes forming bars and corrupts time order upon receiving late ticks.
