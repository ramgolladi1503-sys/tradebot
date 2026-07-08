# Regime Pass Independence Audit

## 1. Exact Changed Files
Running `git diff --check` and `git diff` confirms that no production logic changed in the core files (`core/regime_monitor.py` and `core/market_context.py`). The only modifications were the injection of the telemetry `jsonl` loggers around the `_append_log` and `derive_market_context` functions. These strictly append telemetry and do not weaken any gates or change any classification logic.

## 2. Prove Source Selection
The generator used `ohlc_csv` because `auto` prioritized it over `tick_jsonl`.
- **Selected Source Path**: `data/live_intraday/NIFTY_intraday.parquet`
- **Source Type**: `ohlc_csv`
- **Reason Selected**: It was the first matched `USABLE_OHLC` in the inventory.
- **Timestamp Column**: `timestamp`
- **OHLC Columns**: `open`, `high`, `low`, `close`
- **Row Count**: 375 bars
- **Date Range**: 2026-07-06 03:45:00 to 09:59:00 UTC

## 3. Check Auto Priority
The `.runtime/market_data/ticks_20260706.jsonl` was NOT considered because the `auto` rule iterated over `USABLE_OHLC` classifications first. Since a valid `USABLE_OHLC` parquet was found for that date, it immediately selected it, skipping the `USABLE_TICK_LTP` jsonl fallback entirely.

## 4. Prove Reference Independence
**Verdict: REFERENCE_INDEPENDENCE_TAUTOLOGICAL_SAME_CODE**

The audit is entirely broken and tautological. The `scripts/audit_regime_strategy_switching.py` does not contain any independent reference classification logic. Instead, it checks if the data files exist, and if they do, it hardcodes `regime_match_rate = 1.0` (line 150). The reference regime is neither built nor compared against the TradeBot output.

## 5. Negative Control Test
I ran a local test perturbing the `reference_ohlc_2026-07-06.parquet` close prices by 10%.
- **Original run match**: 100%
- **Perturbed run match**: 100%

Because the audit script ignores the data and hardcodes the match rate, perturbing the input had zero effect. This confirms the audit is fundamentally broken.

## 6. Time-Window Alignment
The timelines cover completely disjoint windows:
- **First timestamp Reference**: `2026-07-06 03:45:00+00:00`
- **Last timestamp Reference**: `2026-07-06 09:59:00+00:00`
- **First timestamp TradeBot**: `1783365763` (~`2026-07-06 19:22:43 UTC`)
- **Last timestamp TradeBot**: `1783365763`

The TradeBot regime telemetry relies on `time.time()` injected during replay generation, ignoring the simulation time entirely. There is no intersection.

## 7. Strategy Matching Sanity
**Verdict: STRATEGY_MATCH_TAUTOLOGICAL**

The `strategy_match_rate` is hardcoded to `1.0` if `strategy_switching_found` is true (line 152). While there is a `get_expected_strategy_family` dictionary that acts as a deterministic mapping from regime to strategy, it is never even called to evaluate the metrics.

## 8. Final Verdict
**Verdict: REGIME_AUDIT_BROKEN**

The verification pass was entirely fabricated by the audit script logic, which returns `1.0` manually if the required files are simply present on disk. No independent verification actually took place.
