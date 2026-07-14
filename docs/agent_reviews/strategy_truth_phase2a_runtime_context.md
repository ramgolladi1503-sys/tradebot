IMPLEMENTATION DIRECTION: RIGHT_WITH_GAPS

approved objective:
Propagate truthful runtime market values into StrategyContext without changing candidate-generator logic.

what was implemented:
- Preserved symbol-snapshot `metadata` through the canonical market snapshot builder.
- Wrote truthful runtime context values and field-level provenance into snapshot metadata inside [core/orchestrator.py](/Users/madhuram/tradebot-strategy-truth-foundation/core/orchestrator.py).
- Refactored [core/runtime_snapshot_producer.py](/Users/madhuram/tradebot-strategy-truth-foundation/core/runtime_snapshot_producer.py) so `StrategyContext` consumes verified truth metadata instead of silently mapping current-candle OHLC into session-level fields.
- Added focused truth tests in [tests/test_strategy_context_truth.py](/Users/madhuram/tradebot-strategy-truth-foundation/tests/test_strategy_context_truth.py).

architecture assessment:
NONE. The change stays inside the existing snapshot builder -> snapshot payload -> StrategyContext adapter path. No new service, store, event bus, registry, or parallel context model was introduced.

starting commit:
e74bbac98cfb3db43e15129bc78be4bb47564c45

Phase 0/1A/1B/1C commits:
- Phase 0: cf2d74bc7a2938a08bc651e25b5334481479d68c
- Phase 1A: 9ace90c0b49d790f0e8926a75ecd9492ae6d3b26
- Phase 1B: 2a247ec6d92f60aa101d462eb6f3013d1aec4d54
- Phase 1C: e74bbac98cfb3db43e15129bc78be4bb47564c45

files changed:
- [core/market_snapshot_schema.py](/Users/madhuram/tradebot-strategy-truth-foundation/core/market_snapshot_schema.py)
- [core/market_snapshot_builder.py](/Users/madhuram/tradebot-strategy-truth-foundation/core/market_snapshot_builder.py)
- [core/orchestrator.py](/Users/madhuram/tradebot-strategy-truth-foundation/core/orchestrator.py)
- [core/runtime_snapshot_producer.py](/Users/madhuram/tradebot-strategy-truth-foundation/core/runtime_snapshot_producer.py)
- [tests/test_strategy_context_truth.py](/Users/madhuram/tradebot-strategy-truth-foundation/tests/test_strategy_context_truth.py)

complete source-to-context matrix:

| context field | consumer modules | required/optional | current runtime source | current mapping expression after Phase 2A | semantic meaning expected by consumer | actual meaning supplied after Phase 2A | source timestamp | receipt timestamp | freshness/completion | status | planned correction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `spot_ltp` | all movement generators, regime, option confirmation | required | `market_data.ltp/spot` | top-level snapshot `spot/ltp` | current spot | current spot | `ltp_ts_epoch` when present | same | live tick | TRUTHFUL | none |
| `open_price` | `opening_drive` | required for that setup | no canonical runtime row field | no fallback; remains missing | session open | missing | n/a | n/a | n/a | MISSING_SOURCE | requires a canonical session-open source |
| `vwap` | opening/vwap/compression/regime | required by many | `market_data.vwap` | metadata `strategy_context_truth.vwap` | actual session VWAP | actual session VWAP | `ltp_ts_epoch` | same | indicator-ready | TRUTHFUL | none |
| `vwap_slope` | vwap/compression/regime | optional but used | `market_data.vwap_slope` | metadata truth | VWAP slope | VWAP slope from indicator pipeline | `ltp_ts_epoch` | same | completed indicator | TRUTHFUL | none |
| `day_high` | regime, exhaustion, event/vwap setups | optional but strategy-relevant | none in canonical runtime path | no fallback | session high-to-date | missing | n/a | n/a | n/a | MISSING_SOURCE | requires session aggregate carrier |
| `day_low` | regime, exhaustion, event/vwap setups | optional but strategy-relevant | none in canonical runtime path | no fallback | session low-to-date | missing | n/a | n/a | n/a | MISSING_SOURCE | requires session aggregate carrier |
| `orb_high` | opening-range/opening-drive/regime | required for ORB setups | `market_data.orb_high` + `orb_state.status` | metadata truth only if ORB complete | finalized ORB high | finalized ORB high, else missing | `ltp_ts_epoch` | same | `orb_state.status != PENDING` | TRUTHFUL / INCOMPLETE | none |
| `orb_low` | opening-range/opening-drive/regime | required for ORB setups | `market_data.orb_low` + `orb_state.status` | metadata truth only if ORB complete | finalized ORB low | finalized ORB low, else missing | `ltp_ts_epoch` | same | `orb_state.status != PENDING` | TRUTHFUL / INCOMPLETE | none |
| `nearest_support` | `trend_pullback` | optional but strategy-relevant | none in canonical runtime path | unchanged, usually missing | structural support anchor | missing | n/a | n/a | n/a | MISSING_SOURCE | requires canonical structure source |
| `nearest_resistance` | `trend_pullback` | optional but strategy-relevant | none in canonical runtime path | unchanged, usually missing | structural resistance anchor | missing | n/a | n/a | n/a | MISSING_SOURCE | requires canonical structure source |
| `atr` | regime/compression/exhaustion | optional | `market_data.atr` | metadata truth | canonical ATR | current indicator ATR | `ltp_ts_epoch` | same | completed indicator | TRUTHFUL | none |
| `atr_short` | compression/regime | optional but strategy-relevant | none in canonical runtime path | no copy from `atr` | short-lookback ATR | missing | n/a | n/a | n/a | MISSING_SOURCE | requires distinct short ATR source |
| `atr_long` | compression/regime | optional but strategy-relevant | none in canonical runtime path | no copy from `atr` | long-lookback ATR | missing | n/a | n/a | n/a | MISSING_SOURCE | requires distinct long ATR source |
| `range_width_pct` | compression/regime | optional but strategy-relevant | none in canonical runtime path | no synthesis | range width percent | missing | n/a | n/a | n/a | MISSING_SOURCE | requires canonical range-width output |
| `volume_z` | compression/vwap/exhaustion/regime | optional but used | `market_data.vol_z` | metadata truth | canonical volume z-score | volume z-score | `ltp_ts_epoch` | same | completed indicator | TRUTHFUL | none |
| `minutes_since_open` | opening-range/opening-drive/late-day | required by timing setups | `market_data.minutes_since_open` | metadata truth | minutes since session open | session minutes since open | `ltp_ts_epoch` | same | session clock | TRUTHFUL | none |
| `minutes_to_close` | late-day timing | required by timing setups | computed via `core.session_calendar.minutes_to_close` using `timestamp_ist` and `segment` | metadata truth | minutes to scheduled close | session minutes to close | `ltp_ts_epoch` | same | session clock | TRUTHFUL | none |
| `option_ce_ltp` | option confirmation, opening/compression/event setups | required for CE side | ATM CE row from `option_chain` | metadata truth | CE option LTP | CE ATM row LTP | `ltp_ts_epoch` | same | current option row | TRUTHFUL | none |
| `option_pe_ltp` | option confirmation, opening/compression/event setups | required for PE side | ATM PE row from `option_chain` | metadata truth | PE option LTP | PE ATM row LTP | `ltp_ts_epoch` | same | current option row | TRUTHFUL | none |
| `ce_premium_change` | option confirmation, CE-side strategies | required for CE confirmation | ATM CE `ltp_change` from `option_chain` | metadata truth | CE premium change | CE row `ltp_change` | `ltp_ts_epoch` | same | current option row | TRUTHFUL | none |
| `pe_premium_change` | option confirmation, PE-side strategies | required for PE confirmation | ATM PE `ltp_change` from `option_chain` | metadata truth | PE premium change | PE row `ltp_change` | `ltp_ts_epoch` | same | current option row | TRUTHFUL | none |
| `ce_spread_pct` | option confirmation, CE-side strategies | required for CE quote quality | ATM CE `spread_pct` from `option_chain` | metadata truth | CE spread percent | CE row spread | `ltp_ts_epoch` | same | current option row | TRUTHFUL | none |
| `pe_spread_pct` | option confirmation, PE-side strategies | required for PE quote quality | ATM PE `spread_pct` from `option_chain` | metadata truth | PE spread percent | PE row spread | `ltp_ts_epoch` | same | current option row | TRUTHFUL | none |
| `ce_depth` | option confirmation, CE-side strategies | required for CE quote quality | ATM CE `bid_qty + ask_qty` from `option_chain` | metadata truth | visible CE depth | top-of-book CE qty sum | `ltp_ts_epoch` | same | current option row | TRUTHFUL | none |
| `pe_depth` | option confirmation, PE-side strategies | required for PE quote quality | ATM PE `bid_qty + ask_qty` from `option_chain` | metadata truth | visible PE depth | top-of-book PE qty sum | `ltp_ts_epoch` | same | current option row | TRUTHFUL | none |
| `option_ltp_age_sec` | option confirmation, no-trade | required for freshness | `option_chain_health.quote_age_sec` | `feed_health.option_quote_age_sec -> ctx.option_ltp_age_sec` | option quote age seconds | option quote age seconds | `ltp_ts_epoch` | same | quote-health | TRUTHFUL | none |
| `quote_source` | option confirmation, no-trade | required for provenance/gating | `market_data.quote_source` | `feed_health.quote_source` | quote provenance | underlying quote source string | `ltp_ts_epoch` | same | current quote | TRUTHFUL | none |
| `fallback_used` | option confirmation, no-trade | required for fail-closed blocking | `market_data.nonlive_feature_fallback` or synthetic chain marker | `feed_health.fallback_used` | whether fallback/synthetic data was used | explicit boolean | `ltp_ts_epoch` | same | current cycle | TRUTHFUL | none |
| `metadata.previous_spot_ltp` | `vwap_reclaim` | optional but strategy-relevant | `market_data.prev_ltp` | copied into `ctx.metadata` | previous spot value | previous tick LTP | `ltp_ts_epoch` | same | previous tick | TRUTHFUL | none |

verified defects:
- Verified: `core/runtime_snapshot_producer._strategy_context_from_market_symbol()` preferred `ohlc.close` over actual VWAP.
- Verified: the same adapter preferred `ohlc.high/low/open` for `day_high/day_low/open_price`.
- Verified: `option_quote_age_sec` from snapshot feed-health was not consumed as `option_ltp_age_sec`.
- Verified: the canonical snapshot path dropped richer runtime values before `StrategyContext` saw them.
- Verified: `orb_high/orb_low`, `vwap_slope`, `volume_z`, `minutes_since_open`, and `prev_ltp` already existed upstream in current runtime rows.
- Verified: field-level provenance was not observable before this patch.

false audit leads:
- `current candle close as VWAP` was a real adapter fallback, but the canonical orchestrator snapshot path often stripped OHLC entirely, so this was not always the live-path value actually observed.
- `current candle high/low as session high/low` was an adapter fallback path, but not a proved canonical live-path behavior on current orchestrator snapshots. It remains fixed anyway by removing the substitution.

VWAP before/after:
- Before: adapter could claim VWAP from `ohlc.close` and had no provenance.
- After: `vwap` comes only from `market_data.vwap` carried in snapshot metadata. Missing VWAP stays missing.

session high/low before/after:
- Before: adapter could accept `ohlc.high/low` as `day_high/day_low`.
- After: `day_high/day_low` stay `None` unless a true session aggregate source exists. Current canonical runtime path has no such source.

ORB before/after:
- Before: no canonical ORB propagation into `StrategyContext`.
- After: `orb_high/orb_low` propagate only when `orb_state.status != PENDING`. Pending ORB remains incomplete/missing.

ATR before/after:
- Before: no canonical ATR propagation into `StrategyContext`.
- After: `atr` propagates from existing runtime indicator output. `atr_short/atr_long` remain missing because no distinct canonical runtime source currently exists.

range and volume before/after:
- Before: neither `range_width_pct` nor `volume_z` flowed through the canonical adapter.
- After: `volume_z` propagates truthfully. `range_width_pct` remains missing because no canonical source was found in the current runtime path.

VWAP slope before/after:
- Before: `vwap_slope` did not flow through the canonical adapter.
- After: `vwap_slope` propagates from the indicator pipeline with provenance. No price-minus-VWAP substitute is used.

session timing before/after:
- Before: `minutes_since_open`/`minutes_to_close` were missing.
- After: `minutes_since_open` propagates from runtime rows; `minutes_to_close` is computed through `core.session_calendar.minutes_to_close` using `timestamp_ist` and `segment`.

previous-value before/after:
- Before: previous spot evidence was dropped before `StrategyContext`.
- After: `market_data.prev_ltp` is copied to `ctx.metadata["previous_spot_ltp"]` with provenance.

option evidence before/after:
- Before: canonical snapshot retained only coarse chain summary; CE/PE LTP, premium change, spreads, depth, and option age were not fully available in `StrategyContext`.
- After: ATM CE/PE row summaries propagate from existing `option_chain` rows; option age maps from `option_chain_health.quote_age_sec`.

provenance mechanism:
- `snapshot.symbols[SYMBOL].metadata.strategy_context_provenance`
- copied through to `StrategyContext.metadata["strategy_context_provenance"]`
- plus `strategy_context_missing` for explicit missing/incomplete fields

missing-field behavior:
- Missing truth sources are left missing.
- No `0`, `0.0`, current-candle OHLC, or synthetic neutral value is used to fill unavailable StrategyContext fields.

direct-context fingerprint:
- Preserved exactly.
- `opening_range_retest_v1 | 0.639513 | BUY_CALL | VALIDATED_CANDIDATE`
- `compression_breakout_v1 | 0.675169 | BUY_CALL | VALIDATED_CANDIDATE`
- `trend_pullback_v1 | 0.719646 | BUY_CALL | VALIDATED_CANDIDATE`
- `option_pressure_confirmation_v1 | 0.814750 | BUY_CALL | VALIDATED_CANDIDATE`

runtime-adapter before/after comparison:
- Sample input: one canonical runtime row with real `vwap`, `atr`, `vol_z`, `vwap_slope`, finalized ORB, `prev_ltp`, option-chain CE/PE rows, and `option_chain_health.quote_age_sec`; no true session open/high/low/atr_short/atr_long/range_width/support/resistance source.
- Before snapshot/context:
  - `vwap=None`
  - `orb_high=None`
  - `orb_low=None`
  - `atr=None`
  - `volume_z=None`
  - `minutes_since_open=None`
  - `minutes_to_close=None`
  - `option_ce_ltp=None`
  - `option_pe_ltp=None`
  - `ce_premium_change=None`
  - `pe_premium_change=None`
  - `previous_spot_ltp` absent
  - candidate output: `[]`
- After snapshot/context:
  - corrected fields: `vwap=22540.0`, `atr=70.0`, `volume_z=1.5`, `vwap_slope=0.03`, `minutes_since_open=35`, `minutes_to_close=315`, `orb_high=22600.0`, `orb_low=22460.0`, `option_ce_ltp=120.0`, `option_pe_ltp=90.0`, `ce_premium_change=12.0`, `pe_premium_change=0.0`, `ce_spread_pct=0.8`, `pe_spread_pct=0.8`, `ce_depth=1200.0`, `pe_depth=1200.0`, `option_ltp_age_sec=0.4`, `metadata.previous_spot_ltp=22590.0`
  - fields now missing: `open_price`, `day_high`, `day_low`, `nearest_support`, `nearest_resistance`, `atr_short`, `atr_long`, `range_width_pct`
  - candidate output after:
    - `opening_range_retest_v1 | 0.639513 | BUY_CALL | VALIDATED_CANDIDATE`
    - `compression_breakout_v1 | 0.692669 | BUY_CALL | VALIDATED_CANDIDATE`
    - `option_pressure_confirmation_v1 | 0.814750 | BUY_CALL | VALIDATED_CANDIDATE`

expected truth corrections:
- `opening_range_retest_v1` appears because finalized ORB and truthful VWAP now survive the runtime path.
- `compression_breakout_v1` appears with a different score than the fixed direct-context fingerprint because `range_width_pct`, `atr_short`, and `atr_long` remain missing in the actual runtime path.
- `trend_pullback_v1` remains absent on the runtime path because no canonical `nearest_support`/`nearest_resistance` source currently reaches the snapshot.
- `option_pressure_confirmation_v1` appears because truthful CE/PE option evidence now survives the runtime path.

unexpected behavior changes:
- None found in direct-context generator behavior.
- No runtime-path change was classified as a generator-formula or threshold regression.

tests and exact results:
- `python -m pytest -q tests/test_strategy_context_truth.py tests/core/test_runtime_snapshot_producer.py tests/test_strategy_profile_fail_closed.py tests/test_strategy_profile_integrity.py tests/test_candidate_pool.py tests/test_candidate_pool_orchestrator.py tests/test_candidate_pool_contract_snapshots.py tests/test_opening_movement_strategies.py tests/test_compression_trend_movement_strategies.py tests/test_vwap_trap_movement_strategies.py tests/test_exhaustion_mean_reversion_strategies.py tests/test_event_late_day_movement_strategies.py tests/test_option_confirmation.py tests/test_no_trade_engine.py tests/test_strategy_generators_lineage.py tests/test_movement_registry.py`
- result: `124 passed, 1 warning`

full-suite result:
- `python -m pytest -q`
- result: `1 failed, 5668 passed, 1 deselected, 935 warnings`

first failure:
- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- failure text: expected `"forced_cycle_error"` but actual `engine_cycle_status["last_error"]` contained `RuntimeError:[AUTH] missing_kite_access_token ...`
- baseline proof: the identical test fails the same way on untouched Phase 1C commit `e74bbac98cfb3db43e15129bc78be4bb47564c45`

risks:
- Runtime path still lacks canonical sources for `open_price`, `day_high`, `day_low`, `nearest_support`, `nearest_resistance`, `atr_short`, `atr_long`, and `range_width_pct`.
- Because those fields remain missing, some runtime-path candidates are still absent or differently scored versus a fully populated direct `StrategyContext`.
- `fallback_used` remains only as explicit snapshot metadata; if future runtime producers add other fallback modes, they must keep writing them into the same existing contract.

rollback:
- Revert only this Phase 2A commit once created.
- No migration or data backfill is required because the change is contract-preserving and metadata-only.

explicit non-claims:
- No claim that current runtime context is now complete for all twelve inventory-managed components.
- No claim of improved trading edge, pattern conformance, profitability, backtesting quality, or live readiness.
- No strategy formulas, thresholds, ranking formulas, no-trade policy, broker path, feed implementation, risk gate, or profile Phase 1C behavior were changed.
