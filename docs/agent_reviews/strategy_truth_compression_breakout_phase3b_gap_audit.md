# Strategy Truth Phase 3B Gap Audit: `compression_breakout_v1`

## Scope

- Worktree: `/Users/madhuram/tradebot-compression-breakout-phase3b-closure`
- Branch: `fix/compression-breakout-phase3b-closure`
- Starting head: `1b95bbc9923567ccd1ed52df8f9205c172333539`
- Final implementation head before evidence commit: `1b95bbc9923567ccd1ed52df8f9205c172333539`
- Accepted ancestry: `PROVEN`
- Accepted ancestry evidence: the branch descends from the accepted Trend Pullback closure line and retains the accepted Phase 3B harness, restart, and PR 657/658 ancestry.

## Denominator evidence matrix

| source file / commit | formula | denominator | timestamp semantics | runtime usage | replay / offline usage | test coverage | authority level |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `core/session_bar_history.py` @ `1b95bbc9923567ccd1ed52df8f9205c172333539` | `(day_high - day_low) / reference_price` | caller-supplied `reference_price` | completed bars only; forming bars past cutoff are excluded | helper only; denominator is not fixed here | helper only; denominator is not fixed here | `tests/test_compression_breakout_range_width_runtime_contract.py` | helper-only, not canonical |
| `core/market_data.py` @ `1b95bbc9923567ccd1ed52df8f9205c172333539` | `calculate_session_range_width_pct_from_completed_history(... reference_price=ltp)` | live `ltp` | live cycle cutoff / current snapshot | yes | no | `tests/test_compression_breakout_range_width_runtime_contract.py` | live-runtime source only |
| `core/orb_ohlcv_validation.py` @ `1b95bbc9923567ccd1ed52df8f9205c172333539` | `(day_high_so_far - day_low_so_far) / close` | row `close` | row timestamp / candle close | no | yes | `tests/test_captured_market_session_replay.py` | offline proxy only |
| `scripts/backtest_all_strategies_available_data.py` @ `1b95bbc9923567ccd1ed52df8f9205c172333539` | `(day_high_so_far - day_low_so_far) / max(close, 1.0)` | row `close` | candle close | no | yes | script-level proxy only | offline research proxy |
| `tests/test_compression_breakout_range_width_runtime_contract.py` @ this task | same completed history, two denominator inputs | `100.0` vs `40.0` | same causal completed-bar prefix | proves live-path sensitivity | proves replay/offline proxy sensitivity | added threshold-straddle proof | evidence artifact |

## Contract result

`DENOMINATOR_CONTRACT_AMBIGUOUS`

The repository does not prove a single canonical denominator for `range_width_pct`.

What is proven:

- The runtime producer currently passes live `ltp` as the denominator input.
- Replay/offline proxies currently derive the same ratio from `close`.
- The helper is denominator-agnostic and does not resolve the contract by itself.
- The same completed history can produce a candidate on one denominator and fail the compression gate on another.

What is not proven:

- That live `ltp` and final candle `close` are always equal at evaluation cutoff.
- That the two denominator choices are equivalent across live and replay paths.
- That one denominator is canonical for both runtime and replay without additional contract evidence.

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
| runtime denominator | PROVEN | `core.market_data.fetch_live_market_data` passes `ltp` into the completed-history helper |
| replay / offline denominator | PROVEN | offline proxy code and replay-oriented tests use `close` |
| canonical denominator | NOT PROVEN | no repository evidence shows live `ltp` and offline `close` are guaranteed equivalent at the strategy cutoff |
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

## Tests and results

- Focused compression-breakout slice:
  - `python -m pytest -q tests/test_compression_breakout_range_width_runtime_contract.py tests/test_compression_breakout_phase3b_gap_audit.py tests/test_compression_trend_movement_strategies.py tests/test_candidate_phase2_ownership.py tests/test_candidate_phase2_semantic_ownership.py`
  - result: `36 passed, 1 warning in 12.45s`
- Full repository suite:
  - `python -m pytest -q`
  - result: `1 failed, 6015 passed, 24 deselected, 935 warnings in 426.02s`
  - first failure: `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
  - failure cause: pre-existing unrelated auth baseline (`RuntimeError: [AUTH] missing_kite_access_token`)

## Baseline comparison

- The accepted direct fingerprint remains unchanged.
- The runtime and replay/offline denominator sources remain split.
- The new threshold-straddle test proves the split can change candidate acceptance on the same completed history.
- The full suite still contains one known unrelated auth failure and no compression-breakout-specific regression.

## Rollback

- Remove the threshold-straddle regression test from `tests/test_compression_breakout_range_width_runtime_contract.py`.
- Revert this evidence document to the prior gap-audit version.
- Do not change production code; no production change was made in this task.

## Explicit non-claims

- No claim of profitability, edge, or production readiness.
- No strategy formula, threshold, ranking weight, or owner/outbox change.
- No claim that the branch was pushed.
- No claim that historical validation, execution readiness, or live readiness has been proven.
- No claim that a single canonical denominator was recovered.
