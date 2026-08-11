# Strategy Module Taxonomy

This table maps each `strategies/*` module to its contract owner and audit boundary.
It is intentionally read-only documentation. It does not change runtime behavior,
freshness logic, feed logic, broker wiring, or execution gates.

| Module | Contract owner | Family / role | Audit boundary |
|---|---|---|---|
| `strategies/ensemble.py` | `core/strategy_spec.py` | `ENSEMBLE` meta-strategy | Contract-backed directional meta-signal; rank via standard candidate pipeline |
| `strategies/vwap_orb.py` | `core/strategy_spec.py` | `VWAP_ORB` directional intraday | Directional candidate path; freshness before executable ranking |
| `strategies/nifty_intraday.py` | `core/strategy_spec.py` | `VWAP` directional intraday | Regime-aware directional path; undeclared regime fails closed before scoring |
| `strategies/banknifty_intraday.py` | `core/strategy_spec.py` | `VWAP` directional intraday | Regime-aware directional path; undeclared regime fails closed before scoring |
| `strategies/sensex_intraday.py` | `core/strategy_spec.py` | `VWAP` directional intraday | Regime-aware directional path; undeclared regime fails closed before scoring |
| `strategies/zero_hero.py` | `core/strategy_spec.py` | `EXPIRY` special-case | Expiry-specialized path; not a generic intraday strategy |
| `strategies/pairs_arbitrage.py` | `core/strategy_spec.py` | `PAIR_ARBITRAGE` relative-value | Pair-specific spread contract; two-leg identity/freshness sensitive |
| `strategies/volatility_trend.py` | `core/strategy_spec.py` | `EVENT` / volatility-trend directional | Volatility-scaled trend family; contract-backed and freshness-sensitive |
| `strategies/pro_layer/pro_strategy_engine.py` | `core/strategy_spec.py` | `PRO_STRATEGY` meta-layer | Aggregates orthogonal pro signals; inherits child-family checks |
| `strategies/pro_layer/pro_decision_adapter.py` | no strategy contract owner | Support utility | Pro-layer adapter only; not a strategy family |
| `strategies/movement/opening_drive.py` | `core/strategy_spec.py` | `MOVEMENT` breakout subtype | Movement contract; candidate boundary before Phase-2 truth |
| `strategies/movement/opening_range_breakout.py` | `core/strategy_spec.py` | `MOVEMENT` opening-range retest subtype | Movement contract; candidate boundary before Phase-2 truth |
| `strategies/movement/compression_breakout.py` | `core/strategy_spec.py` | `MOVEMENT` breakout subtype | Movement contract; candidate boundary before Phase-2 truth |
| `strategies/movement/trend_pullback.py` | `core/strategy_spec.py` | `MOVEMENT` pullback subtype | Movement contract; candidate boundary before Phase-2 truth |
| `strategies/movement/vwap_reclaim.py` | `core/strategy_spec.py` | `MOVEMENT` reclaim subtype | Movement contract; candidate boundary before Phase-2 truth |
| `strategies/movement/failed_breakout_trap.py` | `core/strategy_spec.py` | `MOVEMENT` trap subtype | Movement contract; candidate boundary before Phase-2 truth |
| `strategies/movement/exhaustion_reversal.py` | `core/strategy_spec.py` | `MOVEMENT` reversal subtype | Movement contract; candidate boundary before Phase-2 truth |
| `strategies/movement/market_event_graph_reversal.py` | `core/strategy_spec.py` | `MOVEMENT` breadth-event reversal subtype | Shadow/advisory-only movement contract; completed breadth history and freshness required before candidate emission |
| `strategies/movement/mean_reversion_extension.py` | `core/strategy_spec.py` | `MEAN_REVERSION` extension subtype | Movement/mean-reversion contract; candidate freshness before ranking |
| `strategies/movement/event_volatility_expansion.py` | `core/strategy_spec.py` | `EVENT` volatility subtype | Event/volatility contract; freshness-sensitive and fragile to stale data |
| `strategies/movement/option_pressure.py` | `core/strategy_spec.py` | `MOVEMENT` option-pressure subtype | Order-flow/option-pressure contract; quote freshness and depth sensitive |
| `strategies/movement/late_day_momentum.py` | `core/strategy_spec.py` | `MOVEMENT` momentum subtype | Session-specialized movement contract |
| `strategies/movement/no_trade_chop.py` | `core/strategy_spec.py` | `EVENT` / no-trade guard | Defensive no-trade family; should remain read-only and non-executable |
| `strategies/simple_orb.py` | `core/strategy_spec.py` | `MOVEMENT` opening-drive helper | Movement family entrypoint; candidate boundary before ranking |
| `strategies/soft_signal.py` | no strategy contract owner | Support utility | Not a strategy family; signal wrapper only |
| `strategies/movement/_utils.py` | no strategy contract owner | Support utility | Movement helper functions only |
| `strategies/movement/_temporal_evidence.py` | no strategy contract owner | Support utility | Temporal-evidence helper only; not an independent alpha or execution strategy |
| `strategies/position_sizer.py` | no strategy contract owner | Support utility | Not a strategy family; sizing support only |
| `strategies/risk_manager.py` | no strategy contract owner | Support utility | Risk support only; not a strategy family |
| `strategies/trade_builder.py` | no strategy contract owner | Support utility | Orchestration/support module; not a standalone strategy family |
| `strategies/shadow/h1_trapped_push_snapback.py` | H1 frozen shadow contract | `SHADOW` measurement-only strategy adapter | Frozen H1 predicate emits unrouteable BUY_PUT shadow intents only; broker/order/paper/live authority remain false |

## Boundary Notes

- Directional families must not bypass contract eligibility, candidate classification, scoring, or ranking.
- Relative-value and pair-arbitrage families need separate freshness and identity discipline because both legs matter.
- Movement families must stay in the movement contract boundary before any Phase-2 ownership checks.
- Meta-layers such as `PRO_STRATEGY` must inherit the child-family audit boundary, not replace it.
- Support modules are intentionally excluded from the strategy registry because they are not trading families.
