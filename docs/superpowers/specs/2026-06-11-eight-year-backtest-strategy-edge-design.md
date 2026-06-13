# Eight-Year Backtest Strategy Edge Design

## Goal

Build an honest, offline, evidence-first historical backtesting and strategy-improvement program for Tradebot that can evaluate approximately eight years of NIFTY, BANKNIFTY, and SENSEX behavior without faking expired option intraday realism, weakening live safety gates, or mislabeling proxy results as executable edge.

## Scope

This is a three-phase program:

1. Historical data truth and import layer
2. Multi-mode backtest and walk-forward execution layer
3. Evidence-driven strategy improvement layer

This design explicitly excludes:

- live order placement
- broker API usage during backtests except isolated downloader/import tooling
- permissive changes to live feed, execution, or risk gates
- claiming real option-execution proof when only EOD or proxy data exists

## Current Repo Context

The repository already contains several useful but fragmented building blocks:

- replay and backtest surfaces: `core/backtest_engine.py`, `core/replay_engine.py`, `core/replay_harness.py`, `core/run_backtest.py`, `core/walk_forward.py`, `scripts/run_walk_forward.py`
- option-specific backtest components: `core/option_backtest/*`
- slippage and fill models: `core/slippage_model.py`, `core/option_fill_model.py`, `core/cost_slippage_model.py`
- candidate/ranking/signal path: `core/candidate_*`, `core/candidate_scoring.py`, `core/candidate_ranking.py`, `core/ranking_orchestrator.py`, `core/opportunity_score.py`
- position sizing and risk: `core/position_sizer.py`, `core/risk*.py`, `core/pretrade_risk_engine.py`, `core/portfolio_risk_allocator.py`
- runtime/live evidence: `.runtime`, SQLite-backed logs, `core/runtime_*`, `core/feed_*`, and multiple diagnostics scripts

There is already overlap and some toy-quality historical surfaces in the repo. The design must not duplicate proven logic blindly. It should introduce one clear backtesting spine and reuse existing modules selectively.

## Architecture Decision

Use a hybrid architecture.

Introduce a new `core/backtesting/` package as the primary contract and orchestration layer, while selectively reusing existing modules behind adapter boundaries.

### Why hybrid

- A pure wrapper approach would preserve too much fragmentation and make data truth, mode selection, and reporting inconsistent.
- A pure greenfield rewrite would create migration churn and duplicate useful replay/backtest logic already present in the repo.
- A hybrid spine allows one stable interface for diagnostics, mode selection, walk-forward execution, and reporting while reusing proven internals such as option replay, slippage, and candidate logic.

## Phase Structure

### Phase 1: Data Truth and Historical Import

Purpose:

- Discover what historical data actually exists
- Normalize it into explicit source contracts
- Refuse to overstate realism

Primary outputs:

- a machine-readable `DataCatalog`
- import tooling for local historical data
- an evidence report describing source coverage and feasible backtest modes

### Phase 2: Offline Backtest and Walk-Forward Execution

Purpose:

- Execute current strategy/candidate/ranking logic against historical data
- Support multiple honesty-labeled modes
- Separate training, validation, and out-of-sample results

Primary outputs:

- deterministic backtest runs
- walk-forward fold reports
- regime-segmented metrics
- comparable run artifacts

### Phase 3: Evidence-Driven Improvement

Purpose:

- Identify whether edge is lost in signal generation, ranking, confidence calibration, fallback contamination, or sizing
- Improve ranking/confidence/sizing first
- gate signal-generation changes behind residual proven weakness

Primary outputs:

- ranking diagnostics
- confidence calibration evidence
- strategy/regime weakness reports
- controlled, test-backed remediation recommendations and patches

## New Package Layout

Create a new package:

- `core/backtesting/__init__.py`
- `core/backtesting/models.py`
- `core/backtesting/data_catalog.py`
- `core/backtesting/data_loader.py`
- `core/backtesting/nse_derivatives_loader.py`
- `core/backtesting/option_data_loader.py`
- `core/backtesting/replay_clock.py`
- `core/backtesting/pipeline_adapter.py`
- `core/backtesting/execution_simulator.py`
- `core/backtesting/option_fill_model.py`
- `core/backtesting/slippage_model.py`
- `core/backtesting/walk_forward.py`
- `core/backtesting/metrics.py`
- `core/backtesting/ranking_diagnostics.py`
- `core/backtesting/strategy_diagnostics.py`
- `core/backtesting/reporting.py`

Supporting scripts:

- `scripts/backtest_data_diagnostics.py`
- `scripts/import_historical_data.py`
- `scripts/run_8y_strategy_backtest.py`
- `scripts/run_walk_forward_backtest.py`
- `scripts/compare_backtest_runs.py`

Supporting config and docs:

- `configs/backtest_8y.example.json`
- `docs/backtesting/eight_year_strategy_validation.md`

## Ownership Boundaries

The new `core/backtesting/` package owns:

- historical data source contracts
- data availability diagnostics
- mode feasibility decisions
- canonical backtest run configuration
- walk-forward orchestration
- execution simulation orchestration
- regime tagging for historical studies
- metrics and reporting
- research-only diagnostics around ranking/confidence/sizing

Existing modules continue to own:

- production candidate generation and strategy logic
- production ranking and opportunity scoring
- production risk and sizing logic where already proven
- feed truth and execution truth for live behavior
- existing option backtest internals where adaptable

This keeps research code from silently mutating live decision paths.

## Data Contracts

The `DataCatalog` must support explicit source types:

1. `UNDERLYING_INDEX_CANDLES`
2. `FUTURES_CANDLES`
3. `OPTION_CONTRACT_CANDLES_INTRADAY`
4. `OPTION_CONTRACT_EOD`
5. `OPTION_CHAIN_SNAPSHOT`
6. `RUNTIME_CAPTURED_LIVE_DATA`

Each source record must capture:

- source type
- source path
- file format
- schema mapping used
- symbol set
- date coverage
- expiry coverage where applicable
- strike coverage where applicable
- interval granularity
- timezone normalization result
- provenance label such as `vendor`, `nse_report`, `repo_runtime`, `user_csv`, `user_parquet`, `user_sqlite`
- quality warnings

The catalog must distinguish:

- present and valid
- present but partial
- present but schema-invalid
- missing

## Data Import Rules

Supported input forms:

- CSV
- Parquet when dependency exists
- SQLite from existing repo/runtime stores
- NSE-style bhavcopy or contract-wise reports when present
- user-provided directories

Configurable default roots:

- `data/historical/index/`
- `data/historical/futures/`
- `data/historical/options_intraday/`
- `data/historical/options_eod/`
- `data/historical/option_chain/`
- `data/historical/nse_reports/`

The importer must not assume any paid vendor schema. Instead it should:

- detect schema profiles
- allow explicit field mapping in config
- emit precise insufficiency reasons

## Honest Backtest Modes

The system must support and label these modes:

### Mode A: `TRUE_OPTIONS_INTRADAY`

Use only real historical intraday option candles or ticks.

This is the only mode that can support strong claims about intraday option execution realism.

### Mode B: `OPTIONS_EOD`

Use real option contract EOD data.

Valid for swing and coarse holding logic, not valid proof for intraday fills or sub-day stop/target realism.

### Mode C: `UNDERLYING_SIGNAL_WITH_OPTION_PROXY`

Use underlying or futures historical data for signal generation and a clearly labeled proxy model for option behavior.

This mode is research-only and must always be marked as proxy.

### Mode D: `LIVE_CAPTURE_REPLAY`

Replay existing runtime DB, logs, and captured truth artifacts.

Valid for pipeline validation and decision-path auditing, not sufficient for eight-year edge claims.

### Mode E: `HYBRID`

Combine full-coverage underlying and futures data with whatever real options data exists for overlapping periods.

Useful when real option coverage is partial.

### Default fallback behavior

If real intraday option history is unavailable, the system must not fail silently. It must mark the run as:

- `INCONCLUSIVE_FOR_REAL_INTRADAY_OPTIONS`

and continue only with lower-confidence modes that are actually supported.

## Pipeline Adapter Design

`core/backtesting/pipeline_adapter.py` is the main safety boundary.

It must:

- feed historical market state into current strategy/candidate/ranking logic
- disable broker and live-only calls
- preserve existing safety classifications such as fallback, stale, synthetic, recovered, and blocked
- ensure fallback or synthetic quotes are never treated as executable by default

The adapter should reuse current modules rather than reimplementing them:

- candidate generation from current `core/candidate_*` and strategy generators
- ranking from current ranking/orchestrator modules
- sizing from current `core/position_sizer.py` and risk modules where valid offline

The adapter must expose:

- raw candidate set
- post-filter candidate set
- ranked opportunities
- executable candidates
- decision reasons
- confidence fields
- fallback/synthetic/stale truth annotations

This is necessary to diagnose whether weakness is in signal creation, filtering, ranking, or execution gating.

## Execution Simulator Design

`core/backtesting/execution_simulator.py` must simulate execution conservatively.

Requirements:

- offline only
- no broker imports on execution path
- explicit fill model provenance
- side-aware slippage
- spread-aware entry/exit modeling where bid/ask exists
- degraded realism warnings when only OHLC is available

The simulator will delegate to:

- existing `core/slippage_model.py`
- existing `core/option_fill_model.py`
- optional wrappers in `core/backtesting/slippage_model.py` and `core/backtesting/option_fill_model.py` to normalize interfaces

It must never:

- invent option marks without labeling them proxy or estimated
- assume fills at impossible prints
- claim intraday stop/target behavior from daily-only data

## Regime and Session Tagging

Phase 2 reports must tag historical context across:

- trending up
- trending down
- range-bound
- high volatility
- low volatility
- expiry day
- non-expiry day
- gap-up day
- gap-down day
- crash or shock sessions
- low-liquidity sessions where detectable

This tagging should reuse existing regime logic where available and add a backtest-safe normalization layer instead of creating a second conflicting regime classifier.

## Walk-Forward Validation

Backtesting must not optimize and report on the same sample.

The walk-forward layer must support:

- fixed split mode
- rolling split mode

Default fixed guidance:

- years 1 to 5: train or development
- year 6: validation
- years 7 to 8: out-of-sample test

Required outputs:

- per-fold metrics
- aggregate metrics
- train versus validation versus test degradation
- improvement rejection when gains are only in-sample

The walk-forward interface should reuse logic from the current `core/walk_forward.py` and `scripts/run_walk_forward.py` where useful, but the new backtesting package must own the contract and reporting shape.

## Metrics

`core/backtesting/metrics.py` must produce strategy- and portfolio-level metrics including:

- trade count
- win rate
- average win
- average loss
- expectancy
- profit factor
- max drawdown
- Sharpe-like or volatility-normalized score if inputs permit
- regime-segmented expectancy
- symbol-segmented expectancy
- setup-family expectancy
- long versus short asymmetry
- capital utilization
- concentration risk
- filter drop reasons
- ranking uplift versus unranked baseline
- confidence bucket calibration

Proxy and non-proxy metrics must never be merged without labeling.

## Phase 3 Improvement Policy

Phase 3 starts conservatively.

The first remediation targets are:

- ranking quality
- `confidence_raw` predictiveness and calibration
- fallback contamination of executable decisions
- directional bias such as all-BUY behavior
- capital allocation and sizing logic
- filters that hide rather than improve weak signals

Phase 3 must not start by rewriting generators.

Generator changes are allowed only if diagnostics show:

- a specific family is persistently weak out-of-sample
- the weakness survives ranking and sizing cleanup
- the weakness clusters by regime, side, or setup in a repeatable way

This prevents destroying attribution.

## Existing Module Reuse Strategy

Prefer reuse as follows:

- `core/option_backtest/*`: option-symbol replay and fill evaluation concepts
- `core/backtest_dataset_contract.py`: strict historical snapshot contract ideas
- `core/walk_forward.py`: fold structure concepts
- `core/slippage_model.py`, `core/option_fill_model.py`: simulation internals
- `core/position_sizer.py`, `core/risk*.py`: offline-safe sizing and risk checks
- `core/candidate_*`, `core/candidate_scoring.py`, `core/candidate_ranking.py`, `core/ranking_orchestrator.py`, `core/opportunity_score.py`: real candidate and ranking path
- `core/expectancy/*`: ranking and regime expectancy diagnostics inputs

Deprecation is not immediate. Legacy entrypoints can remain, but new research work should converge on `core/backtesting/`.

## Configuration Design

Add `configs/backtest_8y.example.json` with explicit keys for:

- data roots by source type
- schema mappings per source family
- source enable or disable flags
- date range
- symbols
- mode selection and allowed fallbacks
- proxy policy
- walk-forward split settings
- fill and slippage assumptions
- output directories
- ranking and sizing diagnostic toggles

Also add runtime config flags only where necessary. Avoid polluting `config/config.py` with research-only defaults when a JSON config file is sufficient.

## Output Artifacts

Each run should write a structured artifact set:

- `catalog.json`
- `diagnostics.json`
- `mode_feasibility.json`
- `run_config_snapshot.json`
- `fold_metrics.json`
- `aggregate_metrics.json`
- `candidate_diagnostics.json`
- `ranking_diagnostics.json`
- `strategy_diagnostics.json`
- human-readable markdown summary

All artifacts must be read-only evidence and clearly identify whether results are:

- real intraday options
- EOD options
- proxy
- runtime replay
- hybrid

## Testing Strategy

Every phase requires tests.

### Phase 1 tests

- source detection for CSV, optional Parquet, SQLite
- schema validation per source type
- coverage calculations
- insufficiency reason reporting
- mode feasibility classification
- provenance preservation

### Phase 2 tests

- deterministic replay clock behavior
- adapter fail-closed behavior when data truth is synthetic, stale, fallback, or incomplete
- simulator behavior under bid/ask present and OHLC-only cases
- walk-forward split correctness
- no leakage between train and test windows
- mode labels propagated into reports

### Phase 3 tests

- confidence calibration reports do not mutate production decisions unless explicitly wired
- fallback candidates never become executable by default in research or live-like modes
- ranking diagnostics preserve existing contract fields
- sizing diagnostics do not silently increase live permissiveness
- generator changes, when eventually allowed, are tested against out-of-sample evidence

## Rollout Plan

### Rollout 1

Ship Phase 1 only:

- catalog
- importers
- diagnostics CLI
- config example
- docs

Acceptance bar:

- system can say exactly what historical data is available and what is not
- no backtest run claims unsupported realism

### Rollout 2

Ship Phase 2:

- multi-mode backtest runner
- walk-forward runner
- comparison tooling
- regime tagging
- metrics and reports

Acceptance bar:

- current strategies can be evaluated across supported modes without broker calls
- outputs clearly separate real, hybrid, EOD, proxy, and runtime-replay evidence

### Rollout 3

Ship Phase 3:

- ranking diagnostics
- confidence calibration diagnostics
- sizing audits
- evidence-driven remediation work

Acceptance bar:

- improvements can be justified with validation and out-of-sample evidence
- no production safety regression

## Risks

### Risk: historical option intraday coverage is insufficient

Mitigation:

- make insufficiency explicit
- run lower-confidence modes without overstating them

### Risk: legacy backtest code mixes toy assumptions with production logic

Mitigation:

- isolate reuse behind adapters
- keep canonical contracts inside `core/backtesting/`

### Risk: research code contaminates live code paths

Mitigation:

- maintain strict package boundaries
- no silent production wiring
- add contract tests for no broker and no live-order behavior

### Risk: overfitting on eight years

Mitigation:

- walk-forward only
- separate train, validation, and test
- reject in-sample-only gains

### Risk: attribution loss during optimization

Mitigation:

- ranking/confidence/sizing before generator rewrites
- one evidence-backed remediation class at a time

## Migration Notes

- Existing scripts like `scripts/backtest_historical.py`, `scripts/backtest_tb*.py`, `scripts/run_walk_forward.py`, and `core/option_backtest/*` should not be deleted immediately.
- New documentation should steer future work toward the new `core/backtesting/` interfaces.
- Legacy runners can be re-pointed later to call the new spine once contracts are stable.

## Success Criteria

The program succeeds when the repository can answer, with evidence:

- what historical data truly exists
- whether true eight-year intraday option backtesting is possible
- which strategies have edge, in which regimes, and with what realism level
- whether ranking and confidence improve selection quality
- whether fallback or synthetic paths contaminate executable outcomes
- whether capital sizing is robust across regimes
- whether any claimed improvement survives out-of-sample testing

The program fails if it produces attractive reports while hiding data insufficiency, proxy assumptions, fallback contamination, or in-sample overfitting.
