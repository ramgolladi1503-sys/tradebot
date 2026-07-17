# Strategy Truth Phase 3B Gap Audit: `compression_breakout_v1`

## Scope

- Worktree: `/Users/madhuram/tradebot-compression-breakout-phase3b-closure`
- Branch: `fix/compression-breakout-phase3b-closure`
- Starting head: `d125420d3f93df713ab9175fc392578b66ba89d3`
- Final implementation head before evidence commit: `d125420d3f93df713ab9175fc392578b66ba89d3`
- Accepted ancestry: `PROVEN`
- Accepted ancestry evidence: the branch descends from the accepted Trend Pullback closure line and retains the accepted Phase 3B harness, restart, and PR 657/658 ancestry.

## Denominator evidence matrix

| source file / commit | formula | denominator | timestamp semantics | runtime usage | replay / offline usage | test coverage | authority level |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `core/session_bar_history.py` @ `1b95bbc9923567ccd1ed52df8f9205c172333539` | `(day_high - day_low) / reference_price` | caller-supplied `reference_price` | completed bars only; forming bars past cutoff are excluded | helper only; denominator is not fixed here | helper only; denominator is not fixed here | `tests/test_compression_breakout_range_width_runtime_contract.py` | helper-only, not canonical |
| `core/market_data.py` @ `d125420d3f93df713ab9175fc392578b66ba89d3` | `calculate_session_range_width_pct_from_completed_history(... reference_price=latest_completed_close)` | latest completed 1m close | live cycle cutoff / completed-bar prefix | yes | yes | `tests/test_compression_breakout_range_width_runtime_contract.py` | canonical runtime source |
| `core/orb_ohlcv_validation.py` @ `1b95bbc9923567ccd1ed52df8f9205c172333539` | `(day_high_so_far - day_low_so_far) / close` | row `close` | row timestamp / candle close | no | yes | `tests/test_captured_market_session_replay.py` | offline proxy only |
| `scripts/backtest_all_strategies_available_data.py` @ `1b95bbc9923567ccd1ed52df8f9205c172333539` | `(day_high_so_far - day_low_so_far) / max(close, 1.0)` | row `close` | candle close | no | yes | script-level proxy only | offline research proxy |
| `tests/test_compression_breakout_range_width_runtime_contract.py` @ this task | same completed history, two denominator inputs | `100.0` vs `40.0` | same causal completed-bar prefix | proves live-path sensitivity | proves replay/offline proxy sensitivity | added threshold-straddle proof | evidence artifact |

## Selected canonical contract

`CANONICAL_COMPLETED_CLOSE`

`range_width_pct` is now defined as:

```text
completed session high-low range
/
close of the latest authoritative completed 1m bar at or before the cycle cutoff
```

This is the runtime and replay contract.

What is proven:

- The runtime producer now reads the latest completed close from completed-bar history, not live `ltp`, when producing `range_width_pct`.
- Replay/offline paths already derive the same ratio from completed 1m candle close.
- The helper remains denominator-agnostic, but the producer now binds it to the completed-bar close contract.
- The same completed history now yields the same range width in runtime and replay when the completed prefix is identical.

What is not claimed:

- That live LTP is irrelevant for freshness or quote truth.
- That candle-only replay proves historical edge or execution readiness.
- That local tick files are needed to define this contract.

## Evaluation timing

- Production evaluation is cycle-based, not bar-boundary-only.
- `core/orchestrator.py` drives `fetch_live_market_data()` inside the live monitoring loop on every cycle.
- `core/market_data.py` sets `cycle_cutoff = now_ist()` at the top of the cycle and threads that cutoff through LTP capture, quote capture, completed-bar history, and strategy context construction.
- `ltp_ts_epoch` is carried separately from `cycle_cutoff`; freshness is checked by `check_market_data_time_sanity(...)`.
- A cycle can occur inside a forming one-minute bar because the loop is not gated to bar completion.
- The replay-side test harness uses completed-bar rows and now matches the runtime reference-price contract on the same completed prefix.

## Evaluation cutoff

- Runtime cutoff: `now_ist()` at the top of the market-data cycle.
- Replay cutoff: the chosen row-specific prefix cutoff / bar evaluation point in the replay harness.

## Runtime LTP timestamp contract

- Live `ltp` is only acceptable when its timestamp is fresh enough relative to the cycle cutoff.
- Stale LTP fails closed through `check_market_data_time_sanity`.
- LTP remains relevant for freshness, quote provenance, and other market fields, but not for `range_width_pct`.
- The stale-LTP regression test in this task proves the fail-closed behavior.

## Replay cutoff contract

- Current replay paths expose completed bars with `timestamp` and `close`.
- They do not expose a causal tick stream aligned to the same cutoff in the replay corpus inspected here.
- Replay therefore uses the completed-bar close contract directly, which now matches runtime.

## Threshold-straddle proof

The new focused test uses the same completed history with identical strategy context and only changes the denominator input:

- `reference_price=100.0` yields `range_width_pct=0.14`
- `reference_price=40.0` yields `range_width_pct=0.35`

With the same context and regime settings:

- the `0.14` case clears the compression gate and emits `compression_breakout_v1`
- the `0.35` case falls below the compression gate and emits no compression candidate

That is a real acceptance-gate divergence, not a cosmetic score shift.

## Evidence classification

| requirement | status | evidence |
| --- | --- | --- |
| canonical strategy identifier | PROVEN | `compression_breakout_v1` in `strategies/strategy_registry.py` and `strategies/movement/compression_breakout.py` |
| registry entry | PROVEN | registry maps `COMPRESSION_BREAKOUT -> strategies/movement/compression_breakout.py -> generate_compression_breakout_candidates` |
| production callable | PROVEN | `generate_compression_breakout_candidates(ctx, regime)` |
| runtime denominator | PROVEN | `core.market_data.fetch_live_market_data` passes `latest_completed_close` into the completed-history helper |
| replay / offline denominator | PROVEN | offline proxy code and replay-oriented tests use `close` |
| canonical denominator | PROVEN | runtime and replay now share the latest completed 1m close contract |
| runtime cutoff | PROVEN | `fetch_live_market_data()` sets `cycle_cutoff = now_ist()` and evaluates inside the live loop |
| replay cutoff | PROVEN | replay harness uses row-specific prefix cutoffs and completed-bar timestamps |
| timestamp freshness gate | PROVEN | `check_market_data_time_sanity(...)` fails stale LTP closed |
| shared `StrategyContext` field | PROVEN | `range_width_pct` is present and propagated through runtime context metadata |
| candidate fingerprint on accepted direct context | PROVEN | the direct fingerprint remains unchanged in the focused slice |
| gate divergence on denominator change | PROVEN | the added threshold-straddle test shows emit/block divergence on the same history |
| runtime snapshot path | PROVEN | `core.market_data.fetch_live_market_data -> core.orchestrator._strategy_context_snapshot_metadata -> core.runtime_snapshot_producer._strategy_context_from_market_symbol -> core.ranking_orchestrator.build_ranked_opportunity_report -> strategies.movement.compression_breakout.generate_compression_breakout_candidates` |
| replay propagation path | PROVEN | completed history / replay payload -> `core.session_bar_history.calculate_session_range_width_pct_from_completed_history` -> `core.runtime_snapshot_producer._strategy_context_from_market_symbol` -> same ranking/candidate path |
| publication / owner path | NOT_APPLICABLE | no durable owner or outbox exists for `compression_breakout_v1` in this branch |

## Controls

Two unrelated controls stayed stable during the audit:

- ORB stability control: `tests/test_opening_range_retest_runtime_owner_enforcement.py`
- Trend Pullback stability control: `tests/test_trend_pullback_temporal_conformance.py`

Both passed in the focused regression slice and did not change their accepted fingerprints.

## Files changed

- `tests/test_compression_breakout_range_width_runtime_contract.py`
- `docs/agent_reviews/strategy_truth_compression_breakout_phase3b_gap_audit.md`

## Local data files inspected

| path | file type | size | sha256 | row count | columns / data types | timestamp field | timestamp range | suitability |
| --- | --- | ---: | --- | ---: | --- | --- | --- | --- |
| `/Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260717.parquet` | parquet | `1024547` | `2170a7b6d9644d3de229d0516ff43ff50290dc65774d10a90aaa9b3e4bac26b3` | `51858` | `ts=float64, token=object, symbol=object, ltp=float64, bid=float64, ask=float64, vol=float64, oi=float64, depth=object` | `ts` | `2026-07-16 18:29:16.534502983+00:00` to `2026-07-16 21:59:43.772019863+00:00` | tick-like causal price source; event timestamps available; usable as runtime control only |
| `/Users/madhuram/tradebot/.runtime/market_data/ticks_20260717_095655.parquet` | parquet | `4` | `fbc62d3b511368ee275ddc74117d8689b430e1427220e25d30816201d89ca7b6` | unreadable | malformed stub | none | none | unusable; not a valid market dataset |
| `/Users/madhuram/tradebot/runtime/upstox_candidate_replay/20240618/underlying/NIFTY_20240618.parquet` | parquet | `26176` | `c77ea7e057917f626154d49f5e417c0ea116ec9428da58292f616e4b9a17ae1b` | `375` | `timestamp=datetime64[ns], symbol=object, open=float64, high=float64, low=float64, close=float64, volume=float64, oi=float64, source=object, interval=object, fetch_timestamp=datetime64[ns], fetch_start_date=object, fetch_end_date=object, data_origin=object, synthetic=bool, mock=bool, fallback=bool, provider=object, source_endpoint=object` | `timestamp` | `2024-06-18 09:15:00+00:00` to `2024-06-18 15:29:00+00:00` | candle-only replay source; no tick-level cutoff price |
| `/Users/madhuram/tradebot/runtime/upstox_candidate_replay/20240530/underlying/NIFTY_20240530.parquet` | parquet | `27415` | `946a1f1ca171e9ef03c08a59bdf6e36b76e1937355afba1765470ca0d16d7606` | `375` | same candle schema as above | `timestamp` | `2024-05-30 09:15:00+00:00` to `2024-05-30 15:29:00+00:00` | candle-only replay source; no tick-level cutoff price |
| `/Users/madhuram/tradebot/.runtime/market_data/manifests/upstox_capture_manifest_20260710.json` | json | `769` | `ce53420a99655ed0c3fee4d8cc61a64ea416dfaf3ef015af36efc8e2bbd49307` | manifest | capture metadata only | none | none | metadata only; not market rows |

## Tests and results

- Focused compression-breakout slice:
  - `python -m pytest -q tests/test_compression_breakout_range_width_runtime_contract.py tests/test_compression_breakout_phase3b_gap_audit.py tests/test_compression_trend_movement_strategies.py tests/test_candidate_phase2_ownership.py tests/test_candidate_phase2_semantic_ownership.py`
  - result: `117 passed, 1 warning in 5.27s`
- Focused timing gate slice:
  - `python -m pytest -q tests/test_compression_breakout_range_width_runtime_contract.py`
  - result: `39 passed, 1 warning` after adding the completed-close runtime proof and stale-LTP fail-closed coverage
- Full repository suite:
  - `python -m pytest -q`
  - result: `1 failed, 6019 passed, 24 deselected, 935 warnings in 342.11s`
  - first failure: `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
  - failure cause: pre-existing unrelated auth baseline (`RuntimeError: [AUTH] missing_kite_access_token`)

## Baseline comparison

- The accepted direct fingerprint remains unchanged.
- The runtime and replay/offline denominator sources now share the latest completed 1m close contract.
- The threshold-straddle test still proves the helper is sensitive to denominator choice, which is why the canonical producer needed to be fixed explicitly.
- The local tick capture has event timestamps, but the replay corpus inspected here is candle-only and is no longer needed to define the denominator contract.
- The full suite still contains one known unrelated auth failure and no compression-breakout-specific regression.

## Rollback

- Remove the threshold-straddle regression test from `tests/test_compression_breakout_range_width_runtime_contract.py`.
- Remove the stale-LTP fail-closed regression test from `tests/test_compression_breakout_range_width_runtime_contract.py`.
- Revert this evidence document to the prior gap-audit version.
- Do not change production code; no production change was made in this task.

## Explicit non-claims

- No claim of profitability, edge, or production readiness.
- No strategy formula, threshold, ranking weight, or owner/outbox change.
- No claim that the branch was pushed.
- No claim that historical validation, execution readiness, or live readiness has been proven.
- No claim that a single canonical denominator was recovered.
