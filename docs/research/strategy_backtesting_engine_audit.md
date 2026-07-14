# Tradebot Strategy Backtesting Engine Audit

Date: 2026-07-13
Worktree: `/Users/madhuram/tradebot-strategy-backtesting`
Branch: `research/strategy-backtesting-validation`
Baseline checked: `c6161445685334d201f56348f82b294a38e6c7ea`

## Executive verdict

`BACKTEST_ENGINE_CONDITIONALLY_READY`

The trusted foundation for strategy validation in this checkout is `core/option_backtest/engine.py::OptionBacktestEngine` plus `core/option_backtest/wfa.py::run_option_replay_wfa`. That path is fail-closed on strict replay inputs, enforces causal timing, uses executable-side bid/ask fills, prices costs explicitly, and writes reconcilable trade and decision artifacts.

The broader backtesting surface is not uniformly trustworthy. The legacy backtest paths (`core/backtest_engine.py`, `core/backtest_elite.py`, `core/backtesting/wfa.py`, `core/walk_forward.py`, and scripts that wrap them) remain proxy/research-only. `scripts/run_candidate_strategy_backtest.py` is hardcoded and cannot be used as evidence of strategy performance.

So the engine is conditionally ready for strategy evaluation if, and only if, users stay on the strict option-replay path and treat the legacy engines as non-certifying.

## Engine-by-engine table

| file / module | current trust rank | reason | biggest trust blocker | recommended action |
|---|---|---|---|---|
| `core/option_backtest/engine.py` | `EXECUTION_GRADE_CANDIDATE` | Strict loader, causal entry timing, executable-side bid/ask exits, explicit costs, reconciliation, and fail-closed certification gates are all present and tested. | Strategy-specific coverage is still limited to the option-replay contract; not all strategy lanes have been run end-to-end yet. | Use as the trusted backtesting foundation for strategy validation research. |
| `core/option_backtest/wfa.py` | `EXECUTION_GRADE_CANDIDATE` | Chronological partitions, purge/embargo boundary logic, validation-before-holdout gating, known setup/regime/OOS checks, and repeated-holdout blocking are explicit. | Depends on the strict engine and on correctly populated replay context; it is only as trustworthy as the input artifacts. | Keep as the only WFA path allowed to emit `PASSED_OPTION_REPLAY_CERTIFICATION`. |
| `core/option_backtest/loader.py` | `EXECUTION_GRADE_CANDIDATE` | Fails closed on missing columns, bad OHLC geometry, duplicate timestamps, missing/stale quotes, post-expiry rows, and contract metadata gaps in strict mode. | Only certifies what is present in the file; it cannot invent provenance or fix incomplete source exports. | Keep strict; do not relax loader gates. |
| `core/option_backtest/adapter.py` | `EXECUTION_GRADE_CANDIDATE` | Converts real replay rows into candidate payloads while preserving strict provenance and timing block conditions. | Proxy timing derivation exists when strict provenance is disabled; this must stay clearly separated from certification. | Keep proxy derivation explicit and blocked in strict mode. |
| `core/fill_model.py` | `PROXY_RESEARCH_ONLY` | Deterministic, but it still models fill size/impact from bid/ask, volume, OI, and an optional fallback liquidity proxy. | Liquidity fallback can synthesize executable size in non-strict mode. | Use only behind strict mode. Do not treat fallback-liquidity fills as certification evidence. |
| `core/backtest_engine.py` | `NOT_TRUSTWORTHY` | Deprecated. Uses synthetic option-chain fetches and future-bar simulation with older proxy assumptions. | Not a strict replay engine. | Retire from any certification or strategy-edge claim. |
| `core/backtest_elite.py` | `PROXY_RESEARCH_ONLY` | Vectorized engine is useful for exploratory tests but explicitly refuses `REAL_EXECUTABLE_RESEARCH`. | It cannot claim real option replay or executable truth. | Keep as research-only. Never use for certification claims. |
| `core/backtesting/wfa.py` | `PROXY_RESEARCH_ONLY` | This WFA path wraps the vectorized engine and is optimized for speed, not executable truth. | It cannot consume real option quotes and is not certifiable. | Keep as proxy-only research tooling. |
| `core/walk_forward.py` | `PROXY_RESEARCH_ONLY` | Legacy walk-forward plumbing still routes through deprecated/proxy engines. | No strict replay/certification contract. | Keep for backward compatibility only. Do not use for trustworthy validation. |
| `core/run_backtest.py` | `PROXY_RESEARCH_ONLY` | Thin wrapper around legacy walk-forward logic. | Inherits all legacy-engine limitations. | Treat as compatibility glue only. |
| `scripts/run_candidate_strategy_backtest.py` | `NOT_TRUSTWORTHY` | Hardcoded pass/fail metrics are emitted regardless of actual strategy performance. | Fake metrics and fake success states. | Fence or deprecate for certification use. |
| `scripts/run_walk_forward.py` | `PROXY_RESEARCH_ONLY` | Uses legacy walk-forward entrypoints and synthetic fallback data when input is absent. | Can silently revert to non-truthful data paths if misused. | Keep for experiment convenience only. |
| `scripts/run_walk_forward_elite.py` | `PROXY_RESEARCH_ONLY` | Elite walk-forward is still vectorized/proxy and not executable replay. | Uses proxy research mode and simulated futures logic. | Keep out of certification paths. |
| `scripts/run_wfa.py` | `PROXY_RESEARCH_ONLY` | Synthetic data fallback is built into the standalone script. | Can produce a result without real replay data. | Do not use as proof of real strategy edge. |

## Evidence

### Loader and strict replay contract

- `core/option_backtest/loader.py::load_option_symbol_csv`
  - Rejects missing required OHLCV columns.
  - Rejects invalid OHLC geometry, duplicate timestamps, stale quotes, post-expiry rows, and incomplete quote columns.
  - In strict replay mode, requires contract metadata, dataset provenance, quote timestamps, and quote completeness.

### Causal timing and non-cheating entry logic

- `core/option_backtest/adapter.py::build_candidate_from_candle`
  - Derives `feature_cutoff_ts`, `signal_ts`, and `earliest_entry_ts` from real row fields when present.
  - In strict mode, missing timing provenance sets `execution_blocked` with `missing_signal_timing_provenance`.
  - Same-event entry is blocked as `ambiguous_signal_timing`.

- `core/option_backtest/engine.py::_simulate_exit`
  - Enforces entry-after-signal chronology by requiring `entry_index > row_index`.
  - Uses elapsed timestamps, not row counts, for `max_hold_minutes`.

### Executable fill realism and conservative exits

- `core/option_backtest/engine.py::_simulate_entry`
  - Sends entry orders through `core.fill_model.FillModel`.
  - In strict mode, fallback liquidity is disabled.

- `core/option_backtest/engine.py::_simulate_exit_fill`
  - Uses executable-side quote logic.
  - In strict mode, missing bid/ask on the exit row returns `missing_exit_bid_ask` and fails closed.
  - Non-strict mode may fall back to mark pricing, but that is labeled as proxy behavior.

- `core/fill_model.py::FillModel.simulate`
  - Deterministic, no runtime randomness.
  - Uses bid/ask, quantity, volume, and OI.
  - Fallback liquidity is only allowed when the caller explicitly enables it.

### Cost and reconciliation

- `core/option_backtest/engine.py::_compute_side_costs`
  - Explicit cost model with brokerage, exchange fees, taxes, and other per-order fees.

- `core/option_backtest/report.py::summarize_backtest`
  - Reconciles gross P&L, total costs, and net P&L.
  - Tracks ambiguity count, drawdown, profit factor, and after-cost expectancy.

### WFA chronology and certification isolation

- `core/option_backtest/wfa.py::build_wfa_partition_plan`
  - Uses ordered train/validation/holdout partitions.
  - Applies buffer minutes for lookback, purge, and embargo.

- `core/option_backtest/wfa.py::run_option_replay_wfa`
  - Runs validation before holdout.
  - Blocks repeated holdout runs unless explicitly allowed.
  - Requires `CERTIFICATION_CANDIDATE` and known setup/regime/OOS fields for certification gates.
  - Emits `PASSED_OPTION_REPLAY_CERTIFICATION` only when every gate passes.

### Legacy paths that stay non-certifying

- `core/backtest_engine.py::BacktestEngine`
  - Deprecated and explicitly warns users.
  - Uses future-bar simulation with synthetic option-chain retrieval.

- `core/backtest_elite.py::VectorizedBacktestEngine`
  - Explicitly rejects `REAL_EXECUTABLE_RESEARCH`.
  - Is built for speed and proxy research, not executable truth.

- `scripts/run_candidate_strategy_backtest.py`
  - Hardcodes `trade_count`, `gross_pnl`, `net_pnl`, win rate, expectancy, and drawdown when blockers are absent.
  - This is not an evidence-grade backtest.

## Critical blockers

What still prevents treating the whole backtesting surface as fully trustworthy:

1. Legacy backtest and WFA scripts still exist and can mislead users if they are treated as certifying.
2. The vectorized engine is intentionally proxy-only and not executable-replay capable.
3. The hardcoded candidate-strategy script must not be used as evidence of real strategy performance.
4. Strategy-specific end-to-end validation still needs per-strategy runs on the strict option-replay path.

## Minimal trustworthiness roadmap

Only the strict option-replay path should be considered the foundation. The roadmap is narrow:

1. Keep `core/option_backtest/loader.py` fail-closed.
2. Keep `core/option_backtest/adapter.py` strict on timing provenance and replay metadata.
3. Keep `core/option_backtest/engine.py` on executable-side fills and elapsed-time holds.
4. Keep `core/option_backtest/wfa.py` as the only certifying WFA.
5. Fence the legacy backtest and vectorized paths as proxy-only in docs and tests.
6. Run each strategy through the strict replay validation matrix below before any edge claim.

## Acceptance criteria for trustworthy strategy evaluation

A strategy can be treated as validated only if all of the following are true:

- It runs through `core/option_backtest/engine.py` in `REAL_EXECUTABLE_RESEARCH` mode.
- Loader rejects incomplete or stale replay data rather than inventing values.
- Entry timing is strictly causal and does not allow same-candle cheating.
- Exits use executable-side bid/ask, with strict fail-closed behavior when book quantities are missing.
- Costs, gross P&L, and net P&L reconcile.
- WFA partitions are chronological, buffered, and non-overlapping.
- Result labels are not proxy labels.
- Certification gates pass only on known setup/regime/OOS data.

## Strategy validation plan for the 12 movement strategies

The registry currently exposes these 12 movement strategies:

1. `MEAN_REVERSION_EXTENSION`
2. `COMPRESSION_BREAKOUT`
3. `TREND_PULLBACK`
4. `VWAP_RECLAIM`
5. `OPENING_DRIVE`
6. `FAILED_BREAKOUT_TRAP`
7. `EXHAUSTION_REVERSAL`
8. `EVENT_VOLATILITY_EXPANSION`
9. `LATE_DAY_MOMENTUM`
10. `OPTION_PRESSURE`
11. `OPENING_RANGE_BREAKOUT`
12. `NO_TRADE_CHOP`

Test each strategy with the same matrix, in this order:

1. Data eligibility
   - Confirm the strategy can produce real option-replay input fields without missing metadata.
   - Reject strategies that depend on synthetic or derived values in strict mode.

2. Signal replay
   - Verify the strategy emits a real candidate or a documented rejection reason on frozen replay data.
   - Confirm the candidate path is causal and deterministic.

3. Friction modelling
   - Validate executable fills under real spread/slippage and explicit cost model assumptions.
   - Confirm that higher costs never improve net P&L.

4. In-sample vs out-of-sample split
   - Run WFA partitions and ensure the validation window is evaluated before holdout.
   - Require known setup/regime/OOS metadata for certification-style claims.

5. Walk-forward stability
   - Measure whether performance survives multiple contiguous windows, not only one window.

6. Regime segmentation
   - Compare results across regime labels and reject a strategy that only survives one regime by accident.

7. Parameter perturbation
   - Perturb the strategy’s tunable inputs and confirm the result is not brittle to tiny changes.

8. Negative controls
   - Test shuffled timestamps, randomized labels, or deliberately corrupted timing fields to prove the edge disappears when causality is broken.

9. Certification gate check
   - Only allow a `CERTIFICATION_CANDIDATE` or `PASSED_OPTION_REPLAY_CERTIFICATION` verdict when the strict engine, strict WFA, and reconciliation checks all pass.

10. Final strategy verdict
   - `SUPPORTED_BY_STRICT_OPTION_REPLAY`
   - `CONDITIONALLY_SUPPORTED`
   - `NO_STRUCTURAL_EDGE`
   - `INVALID_DUE_TO_LEAKAGE`
   - `INVALID_DUE_TO_DATA`

## Tests run

Focused tests passed:

- `tests/option_backtest/test_loader.py`
- `tests/option_backtest/test_exporter.py`
- `tests/option_backtest/test_engine.py`
- `tests/option_backtest/test_wfa.py`
- `tests/test_walk_forward_framework.py`
- `tests/test_walk_forward_optimizer.py`
- `tests/test_strategy_registry.py`

Result: `54 passed`

## Final recommendation

Use `core/option_backtest/engine.py` plus `core/option_backtest/wfa.py` as the trusted evaluation path.

Do not use the deprecated proxy engines or the hardcoded candidate backtest script for any claim about strategy edge or certification.
