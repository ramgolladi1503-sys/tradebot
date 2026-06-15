# RCA: Systemic Backtesting & Profitability Divergence

## Executive Summary
This report analyzes why the backtested strategies in this repository perform phenomenally on historical data ("elite level") but fail or exhibit extreme fragility in live markets. The audit spans the historical data ingestion, the core backtest engines (`core/backtest_engine.py`, `core/replay_engine.py`), the strategy building layer (`strategies/trade_builder.py`), risk management, and the regime classification logic.

The core finding is that **backtests are mathematically compromised by lookahead bias, highly inaccurate execution simulation, and an over-reliance on static thresholds over statistical edge**. The engines are not evaluating how a strategy would behave in a real market; they are evaluating a perfect-foresight puzzle solver.

---

## 1. Lookahead Bias in Backtest Engine (`core/backtest_engine.py`)

**Finding:** The primary dataframe-based backtesting engine uses absolute forward-looking evaluations to simulate stop-loss and take-profit events.

*   **Evidence:** In `core/backtest_engine.py`, the `run()` function slices future dataframe bars to check if a stop loss was hit:
    ```python
    future_bars = self.data.iloc[idx + 1 : idx + 1 + self.horizon]
    # Lookahead: 'any()' checks the entire window at once, unaware of intrabar sequence.
    hit_stop = (eval_slice["low"] <= trade.stop_loss).any()
    ```
*   **Impact:** A live system receives ticks linearly. A backtest that uses `.any()` on future lows and highs cannot know which was hit *first* in the same minute candle. This creates a massive survivorship bias, assuming favorable fills when both stop and target are breached in the same window.

## 2. Disconnected Execution & Slippage Modeling

**Finding:** The repository has a robust live slippage and spread modeling class (`core/slippage_model.py`) that estimates fill probability based on actual depth queue quantity, volume, and latency. **None of this is used in backtesting**.

*   **Evidence:** `core/backtest_engine.py` applies a hardcoded fixed slippage:
    ```python
    def _apply_cost(price, side):
        bps = self.slippage_bps + self.spread_bps # Naively fixed at 5 + 5 bps
        return price * (1 + bps / 10000.0)
    ```
*   **Impact:** Live execution logic (`core/execution_engine.py`) dynamically models probability of a fill given spread and chase limits, explicitly rejecting bad fills. Backtesting assumes 100% fill rate at a static penalty, completely missing the "adverse selection" penalty where bad trades fill instantly and good trades are missed.

## 3. Naive "Replay" Patching (`scripts/run_paper_replay.py`)

**Finding:** The tick-by-tick replay engine attempts to simulate reality, but it monkey-patches the actual strategy builder to inject mock signals instead of evaluating the real model.

*   **Evidence:** In `scripts/run_paper_replay.py`:
    ```python
    def _patch_builder_for_replay():
        # Forces random trade confidence or dummy trade generation to 'exercise' the pipeline
    ```
*   **Impact:** Replay tests the *plumbing*, not the *profitability*. There is no module to accurately backtest the strategy code event-by-event on L2 market data.

## 4. Illusion of Strategy Edge & Weak Regime Classification

**Finding:** Strategies like `sensex_intraday.py` use extremely naive point-in-time checks (e.g., `ltp` vs `vwap`) combined with generic regime profiles. The regime logic itself is highly lagging.

*   **Evidence:** `core/regime.py` classifies a trend using fixed thresholds on lagging indicators:
    ```python
    if abs(vwap_slope) >= self.thresholds.trend_vwap_slope_abs_min and atr_pct >= self.thresholds.trend_atr_pct_min:
        return REGIME_TREND
    ```
*   **Impact:** Trend regimes are identified only *after* the trend has occurred, meaning the strategy often enters right at exhaustion points. Backtests hide this because they evaluate the same lagging indicators using the close price, which is perfectly aligned with the simulated entry.

## 5. Non-Existent Pre-Trade Risk in Backtests

**Finding:** The robust `PreTradeRiskEngine` found in `core/pretrade_risk_engine.py` (which enforces daily max loss, margin buffer limits, and exposure limits) is never invoked in `core/backtest_engine.py`.

*   **Impact:** Strategies can size up infinitely and draw down massively during backtests without hitting margin calls or account bans that would stop a live system in its tracks.

---

## Conclusion & Next Steps
The current "elite" profitability is an artifact of the backtesting environment. To upgrade the repository to a true professional standard:

1.  **Deprecate Vectorized Backtesting:** Eliminate `core/backtest_engine.py` in favor of an event-driven backtester that steps through tick data.
2.  **Unify Execution Models:** The event-driven backtester must use `ExecutionEngine.evaluate()` and `SlippageEstimate` from `core/slippage_model.py` to accept/reject fills.
3.  **Real Strategy Profiling:** Disconnect the monkeypatching in `run_paper_replay.py` and run actual strategies (like `sensex_intraday`) through the historical tick stream.
4.  **Incorporate Risk:** Connect `PreTradeRiskEngine` to the backtester to simulate realistic margin constraints.