# Pipeline Truth Map

This document traces the data flow of a trade idea from raw signal generation to execution-ready candidate, auditing where truth might be mutated or lost, and proving that fail-closed safety is maintained throughout the pipeline.

## 1. Signal Generation Layer
*   **Input**: Raw `market_data` (LTP, VWAP, ATR, Option Chain, Regime).
*   **Components**: 
    *   `ensemble_signal` (`strategies/ensemble.py`)
    *   `ProStrategyEngine` (`strategies/pro_layer/pro_strategy_engine.py`)
    *   `MeanReversionCandidateGenerator` (`core/mean_reversion_candidate_generator.py`)
*   **Truth State**: Valid signals return strongly-typed objects (`StrategySignal`, `ProSignal`, `CandidateIntent`) containing `direction` (e.g. `BUY_CALL`, `BUY_PUT`), `score`, and `reason`.
*   **Safety Gates**: 
    *   Missing `ltp`, `vwap`, `atr` immediately return `None`.
    *   `NaN` or infinite inputs return `None` or NO_TRADE (fail-closed).
    *   Neutral/No-Trigger setups return `None`.
*   **Audit Result**: SAFE. The logic correctly halts execution upon bad data rather than fabricating an execution direction.

## 2. Candidate Builder & Mapping Layer
*   **Input**: `StrategySignal` and `market_data`.
*   **Component**: `TradeBuilder` (`strategies/trade_builder.py`)
*   **Truth State**: Maps the abstract signal (`BUY_CALL`/`BUY_PUT`) into a specific option contract (`CE`/`PE`), selecting an executable strike and expiry.
*   **Safety Gates**:
    *   If no valid signal is provided, it explicitly blocks execution (returning `None` or generating a non-executable `advisory_only` fallback).
    *   If the required option chain `quote_age_sec` indicates stale data, or the quote is a fallback, the candidate is forced to an `advisory` or `softened` state.
    *   Only candidates with valid, live option chains achieve `executable` status.
*   **Audit Result**: SAFE. Tests prove that `BUY_CALL` exactly maps to `CE`, `BUY_PUT` exactly maps to `PE`, and any hint of missing/stale data removes the `executable` flag.

## 3. Advisory Fallback Layer (Phase-2)
*   **Input**: Weak signal, bad regime, or stale option chain.
*   **Component**: `_build_planning_no_signal_trade` in `TradeBuilder`.
*   **Truth State**: Returns a visual candidate to keep the dashboard UI active, without allowing broker execution.
*   **Safety Gates**: 
    *   Candidate status is explicitly locked to `advisory_only` or `softened`.
    *   This is enforced by Phase-2 strict checks which prevent UI artifacts from bleeding into real signal paths.
*   **Audit Result**: SAFE.

## 4. Execution Gates Layer
*   **Input**: Ranked list of `Trade` candidates.
*   **Component**: `execution_gates.py` and `Phase2` pipeline logic.
*   **Truth State**: Final go/no-go decision before pushing to the broker adapter.
*   **Safety Gates**:
    *   Checks if the candidate is truly `executable`.
    *   Validates block sizes, liquidity, and option Greek ranges.
    *   Ensures that `LIVE` execution is strictly decoupled from `SIM` or `PAPER` runs.
*   **Audit Result**: SAFE.

## Conclusion
The pipeline preserves truth end-to-end. A bad tick or missing data at Stage 1 will propagate as a `None` or `NO_TRADE` all the way down, preventing the system from hallucinating a live trade. Stale or advisory data correctly stops at the execution gate boundary.

## 5. High-Timeframe (HTF) Bypass Layer (GAP FOUND)
*   **Input**: `df_15m`, `df_1m`.
*   **Component**: `core/candidate_audits/htf_strategies.py` via `run_htf_real_paper_monitor.py`.
*   **Truth State**: Raw `Signal` objects are emitted and immediately processed into CSV logs or offline dictionaries.
*   **Safety Gates**: 
    *   There is no integration with `TradeBuilder`.
    *   There is no Phase-2 fallback block.
    *   Missing dataframe rows trigger unhandled `IndexError` instead of safe fail-closed signals.
*   **Audit Result**: IMPLEMENTATION_BUG_FOUND / PIPELINE_MUTATION_FOUND. The HTF execution path is entirely separate from the main repository safety gates, meaning that if it were attached to live broker adapters, it would bypass all `execution_gates.py` checks.
