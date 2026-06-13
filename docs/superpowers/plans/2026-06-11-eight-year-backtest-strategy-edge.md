# Eight-Year Backtest Strategy Edge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-phase, evidence-first backtesting program for Tradebot that truthfully reports historical data coverage, runs only supported backtest modes, and improves ranking/confidence/sizing before any generator rewrites.

**Architecture:** Use a hybrid architecture with a new `core/backtesting/` package as the canonical contract and orchestration layer, while selectively reusing existing replay, option backtest, slippage, sizing, and ranking modules behind adapters. Phase 1 owns historical data truth and diagnostics only; Phase 2 adds execution and walk-forward; Phase 3 adds diagnostics and evidence-driven remediation.

**Tech Stack:** Python 3, dataclasses, pathlib, csv, sqlite3, optional parquet readers, pytest, existing Tradebot core replay/ranking/risk modules.

---

## File Structure

### New Phase 1 files

- Create: `core/backtesting/__init__.py`
- Create: `core/backtesting/models.py`
- Create: `core/backtesting/data_catalog.py`
- Create: `core/backtesting/data_loader.py`
- Create: `core/backtesting/nse_derivatives_loader.py`
- Create: `core/backtesting/option_data_loader.py`
- Create: `scripts/backtest_data_diagnostics.py`
- Create: `scripts/import_historical_data.py`
- Create: `configs/backtest_8y.example.json`
- Create: `docs/backtesting/eight_year_strategy_validation.md`
- Create: `tests/backtesting/test_data_catalog.py`
- Create: `tests/backtesting/test_data_loader.py`
- Create: `tests/backtesting/test_diagnostics_cli.py`

### Future Phase 2 files

- Create: `core/backtesting/replay_clock.py`
- Create: `core/backtesting/pipeline_adapter.py`
- Create: `core/backtesting/execution_simulator.py`
- Create: `core/backtesting/option_fill_model.py`
- Create: `core/backtesting/slippage_model.py`
- Create: `core/backtesting/walk_forward.py`
- Create: `core/backtesting/metrics.py`
- Create: `core/backtesting/reporting.py`
- Create: `scripts/run_8y_strategy_backtest.py`
- Create: `scripts/run_walk_forward_backtest.py`
- Create: `scripts/compare_backtest_runs.py`
- Create: `tests/backtesting/test_replay_clock.py`
- Create: `tests/backtesting/test_pipeline_adapter.py`
- Create: `tests/backtesting/test_execution_simulator.py`
- Create: `tests/backtesting/test_walk_forward.py`
- Create: `tests/backtesting/test_reporting.py`

### Future Phase 3 files

- Create: `core/backtesting/ranking_diagnostics.py`
- Create: `core/backtesting/strategy_diagnostics.py`
- Create: `tests/backtesting/test_ranking_diagnostics.py`
- Create: `tests/backtesting/test_strategy_diagnostics.py`
- Modify later if evidence supports it: `core/candidate_scoring.py`, `core/candidate_ranking.py`, `core/ranking_orchestrator.py`, `core/opportunity_score.py`, `core/position_sizer.py`
- Modify only if residual evidence proves generator weakness: strategy generator modules under `core/*candidate_generator.py` and related strategy files

## PR Roadmap

### Phase 1 PR 1: `feat(backtesting): add historical data contracts and catalog primitives`

**Goal:** Introduce the canonical Phase 1 model layer and source-type coverage rules.

**Files:**
- Create: `core/backtesting/__init__.py`
- Create: `core/backtesting/models.py`
- Create: `core/backtesting/data_catalog.py`
- Test: `tests/backtesting/test_data_catalog.py`

**Interfaces / functions:**
- `HistoricalSourceType`
- `BacktestMode`
- `DataFormat`
- `CoverageWindow`
- `SymbolCoverage`
- `SourceSchemaRequirement`
- `HistoricalDataSourceRecord`
- `DataCatalog`
- `DataCatalog.from_sources(...)`
- `DataCatalog.mode_feasibility()`
- `DataCatalog.to_payload()`

**Tests to add:**
- source detection for CSV metadata records
- date coverage calculation
- symbol coverage calculation
- provenance preservation
- mode feasibility classification
- missing intraday option data returns `INCONCLUSIVE_FOR_REAL_INTRADAY_OPTIONS`

**Commands:**
- `python -m pytest tests/backtesting/test_data_catalog.py -q`

**Acceptance criteria:**
- catalog can represent all source families from the design spec
- feasibility result distinguishes true intraday options versus EOD/proxy/runtime replay
- missing fields and missing sources produce explicit reasons, not booleans only

**Risks:**
- overloading the catalog with loader-specific behavior
- leaking Phase 2 execution concerns into Phase 1

**Rollback plan:**
- remove the new `core/backtesting/` primitives if the interfaces prove incompatible before downstream adoption

### Phase 1 PR 2: `feat(backtesting): add historical loaders and schema validation`

**Goal:** Load local CSV and SQLite historical sources and validate schemas honestly.

**Files:**
- Create: `core/backtesting/data_loader.py`
- Create: `core/backtesting/nse_derivatives_loader.py`
- Create: `core/backtesting/option_data_loader.py`
- Test: `tests/backtesting/test_data_loader.py`

**Interfaces / functions:**
- `load_historical_source(...)`
- `detect_source_format(path)`
- `scan_source_path(...)`
- `validate_underlying_index_schema(...)`
- `validate_option_intraday_schema(...)`
- `validate_option_eod_schema(...)`
- `summarize_source_coverage(...)`
- `load_sqlite_runtime_source(...)`
- `load_nse_contract_report(...)`

**Tests to add:**
- source detection for CSV
- source detection for SQLite/runtime data
- schema validation for index candles
- schema validation for option intraday candles
- schema validation for option EOD data
- missing required fields produce clear errors
- provenance survives the loader path

**Commands:**
- `python -m pytest tests/backtesting/test_data_loader.py -q`

**Acceptance criteria:**
- loaders can scan local files without broker/API access
- schema failures identify exact missing fields
- coverage summaries include symbols, dates, expiries, strikes, granularity, provenance

**Risks:**
- overfitting validation to a single vendor schema
- conflating load-time normalization with import-time persistence

**Rollback plan:**
- keep the model layer, remove individual loaders if a specific source implementation is flawed

### Phase 1 PR 3: `feat(backtesting): add diagnostics CLI, import CLI, config, docs`

**Goal:** Ship a usable Phase 1 surface for users to answer what data exists and which modes are feasible.

**Files:**
- Create: `scripts/backtest_data_diagnostics.py`
- Create: `scripts/import_historical_data.py`
- Create: `configs/backtest_8y.example.json`
- Create: `docs/backtesting/eight_year_strategy_validation.md`
- Test: `tests/backtesting/test_diagnostics_cli.py`

**Interfaces / functions:**
- `build_diagnostics_report(...)`
- `write_diagnostics_report(...)`
- `run_import_catalog_scan(...)`
- CLI entrypoints for diagnostics and import scan

**Tests to add:**
- diagnostics report is generated
- diagnostics output includes feasible/inconclusive mode classification
- config example loads
- CLI exits nonzero on schema-invalid sources

**Commands:**
- `python scripts/backtest_data_diagnostics.py --config configs/backtest_8y.example.json`
- `python -m pytest tests/backtesting/test_diagnostics_cli.py -q`

**Acceptance criteria:**
- Phase 1 answers all eight required questions from the user brief
- docs explain what each mode means and what is not proven
- config is local-data driven and broker-free

**Risks:**
- CLI quietly swallowing invalid inputs
- docs overstating what proxy or EOD coverage can prove

**Rollback plan:**
- revert CLI/doc/config entrypoints without disturbing the lower-level catalog/loaders

### Phase 2 PR 1: `feat(backtesting): add replay clock and pipeline adapter`

**Goal:** Create the execution-safe historical orchestration layer on top of Phase 1 truth.

**Files:**
- Create: `core/backtesting/replay_clock.py`
- Create: `core/backtesting/pipeline_adapter.py`
- Test: `tests/backtesting/test_replay_clock.py`
- Test: `tests/backtesting/test_pipeline_adapter.py`

**Interfaces / functions:**
- `ReplayClock`
- `ReplayTick`
- `PipelineAdapter`
- `PipelineAdapter.evaluate_snapshot(...)`
- `PipelineEvaluation`

**Tests to add:**
- deterministic time ordering
- no future leakage
- adapter preserves fallback/synthetic/stale/non-executable truth
- adapter never calls broker or live execution paths

**Commands:**
- `python -m pytest tests/backtesting/test_replay_clock.py tests/backtesting/test_pipeline_adapter.py -q`

**Acceptance criteria:**
- Phase 2 can feed historical states into current decision logic without altering live gates

**Risks:**
- historical adapter bypassing current truth guards

**Rollback plan:**
- revert adapter layer while keeping Phase 1 intact

### Phase 2 PR 2: `feat(backtesting): add execution simulator and backtest runners`

**Goal:** Execute supported historical backtest modes conservatively.

**Files:**
- Create: `core/backtesting/execution_simulator.py`
- Create: `core/backtesting/option_fill_model.py`
- Create: `core/backtesting/slippage_model.py`
- Create: `scripts/run_8y_strategy_backtest.py`
- Test: `tests/backtesting/test_execution_simulator.py`

**Interfaces / functions:**
- `ExecutionSimulator`
- `SimulationFill`
- `SimulationTrade`
- `simulate_mode_run(...)`

**Tests to add:**
- bid/ask-aware fills when available
- OHLC-only degraded realism warnings
- proxy mode labeling
- EOD mode cannot claim intraday fill realism

**Commands:**
- `python -m pytest tests/backtesting/test_execution_simulator.py -q`

**Acceptance criteria:**
- simulator produces honest fill assumptions by mode

**Risks:**
- fake fills hidden behind convenience defaults

**Rollback plan:**
- remove the simulator runner and preserve Phase 1 plus adapter

### Phase 2 PR 3: `feat(backtesting): add walk-forward metrics and reporting`

**Goal:** Add train/validation/test splits and comparable backtest artifacts.

**Files:**
- Create: `core/backtesting/walk_forward.py`
- Create: `core/backtesting/metrics.py`
- Create: `core/backtesting/reporting.py`
- Create: `scripts/run_walk_forward_backtest.py`
- Create: `scripts/compare_backtest_runs.py`
- Test: `tests/backtesting/test_walk_forward.py`
- Test: `tests/backtesting/test_reporting.py`

**Interfaces / functions:**
- `WalkForwardPlan`
- `WalkForwardFold`
- `BacktestMetrics`
- `render_backtest_report(...)`
- `compare_backtest_runs(...)`

**Tests to add:**
- fold boundaries
- no leakage
- aggregate metrics
- proxy and real modes never merged without labels

**Commands:**
- `python -m pytest tests/backtesting/test_walk_forward.py tests/backtesting/test_reporting.py -q`

**Acceptance criteria:**
- out-of-sample performance is isolated and reported clearly

**Risks:**
- accidental train/test blending

**Rollback plan:**
- revert reporting/fold orchestration while preserving Phase 1 and Phase 2 runner inputs

### Phase 3 PR 1: `feat(backtesting): add ranking and confidence diagnostics`

**Goal:** Diagnose whether edge loss is in ranking, confidence calibration, fallback contamination, or selection.

**Files:**
- Create: `core/backtesting/ranking_diagnostics.py`
- Test: `tests/backtesting/test_ranking_diagnostics.py`
- Modify later if needed: `core/candidate_scoring.py`, `core/candidate_ranking.py`, `core/ranking_orchestrator.py`, `core/opportunity_score.py`

**Interfaces / functions:**
- `analyze_ranking_quality(...)`
- `analyze_confidence_calibration(...)`
- `analyze_directional_bias(...)`

**Tests to add:**
- fallback/recovered/synthetic candidates cannot be ranked executable
- confidence bucket reports match input evidence
- BUY-only or side bias is surfaced explicitly

**Commands:**
- `python -m pytest tests/backtesting/test_ranking_diagnostics.py -q`

**Acceptance criteria:**
- Phase 3 can prove whether ranking and confidence are weak before touching generators

**Risks:**
- diagnostics code mutating production decision outputs

**Rollback plan:**
- revert diagnostics-only wiring and keep Phase 2 evidence artifacts

### Phase 3 PR 2: `feat(backtesting): add sizing diagnostics and remediation hooks`

**Goal:** Audit capital allocation, position sizing, and filter quality before generator changes.

**Files:**
- Create or extend diagnostics around `core/position_sizer.py`
- Create: `core/backtesting/strategy_diagnostics.py`
- Test: `tests/backtesting/test_strategy_diagnostics.py`

**Interfaces / functions:**
- `analyze_position_sizing(...)`
- `analyze_filter_drag(...)`
- `analyze_strategy_family_residuals(...)`

**Tests to add:**
- sizing evidence does not weaken production risk truth
- filter diagnostics preserve drop reasons

**Commands:**
- `python -m pytest tests/backtesting/test_strategy_diagnostics.py -q`

**Acceptance criteria:**
- residual weakness can be attributed to ranking, sizing, filters, or strategy family

**Risks:**
- silently introducing more permissive sizing behavior

**Rollback plan:**
- revert remediation hooks; keep diagnostics artifacts only

### Phase 3 PR 3: `feat(backtesting): targeted evidence-driven strategy remediation`

**Goal:** Allow narrow generator changes only when Phase 3 evidence proves generator-level weakness remains after ranking/sizing cleanup.

**Files:**
- Modify only specific strategy generator files proven weak
- Add targeted tests alongside existing strategy tests

**Interfaces / functions:**
- generator-specific changes only, no broad framework rewrite

**Tests to add:**
- out-of-sample improvement tests
- no regression in other regimes

**Commands:**
- strategy-specific pytest targets plus relevant Phase 2 comparison runs

**Acceptance criteria:**
- generator change improves validation/test, not just train

**Risks:**
- overfitting or attribution loss

**Rollback plan:**
- revert only the narrow generator patch and retain diagnostic infrastructure

## Phase 1 Immediate Execution Scope

Implement now:

- `core/backtesting/__init__.py`
- `core/backtesting/models.py`
- `core/backtesting/data_catalog.py`
- `core/backtesting/data_loader.py`
- `core/backtesting/nse_derivatives_loader.py`
- `core/backtesting/option_data_loader.py`
- `scripts/backtest_data_diagnostics.py`
- `scripts/import_historical_data.py`
- `configs/backtest_8y.example.json`
- `docs/backtesting/eight_year_strategy_validation.md`
- Phase 1 tests only

Do not implement now:

- replay clock
- pipeline adapter
- execution simulator
- walk-forward
- metrics/reporting beyond diagnostics
- ranking/confidence/sizing remediation
- strategy-generator changes

## Phase 1 Commands

- `python -m pytest tests -q -k "backtesting or historical or data_catalog or data_loader"`
- `python scripts/backtest_data_diagnostics.py --config configs/backtest_8y.example.json`
- `python scripts/import_historical_data.py --config configs/backtest_8y.example.json --dry-run`
- `python scripts/run_unified_ce_gates.py`

## Phase 1 Acceptance Criteria

- answers what historical data exists
- reports symbols, dates, expiries, strikes, granularity, provenance
- states whether true intraday option data exists
- distinguishes EOD, proxy, and runtime replay fallback modes
- reports exact missing fields and insufficiency reasons
- emits `INCONCLUSIVE_FOR_REAL_INTRADAY_OPTIONS` when real intraday option coverage is absent
- performs no broker calls and no live-gate changes

## Spec Coverage Check

- Phase 1 covers data truth, import contracts, diagnostics CLI, config, docs, and tests
- Phase 2 covers replay/backtest/walk-forward/simulator/reporting only after Phase 1 exists
- Phase 3 covers ranking/confidence/sizing diagnostics and only later evidence-driven remediation
- Generator changes are explicitly gated behind residual proven weakness after ranking/sizing cleanup
