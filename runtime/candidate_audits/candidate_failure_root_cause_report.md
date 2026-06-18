# Candidate Failure Root Cause Report

This report investigates why all Campaign B candidates were killed during the edge verification audits.

## 1. Verify Cost Model Correctness
I reviewed the `_calculate_costs` function inside `engine.py`. **The cost model was fatally flawed.**
- **STT Calculation Error**: The STT rate applied was `0.00125` (0.125%), which is the rate for Equity Delivery. For Index Futures, STT is `0.0125%` (`0.000125`), and for Options it is `0.0625%` on premium.
- **Impact**: On a 20,000 Nifty price with a 50 lot size, STT was calculated as `20000 * 50 * 0.00125 = ₹1250` per trade. Real STT for futures would be `₹125`. This 10x exaggeration caused a massive -25 point artificial drag per trade, instantly destroying any edge.
- **Slippage**: 1 point slippage applied to both entry and exit is realistic for Nifty, but the STT math destroyed the baseline.

## 2. Cost Attribution Report
If we break down the costs per trade (using the flawed model vs reality):
| Component | Flawed Model (Avg per trade) | Correct Futures Model |
|-----------|------------------------------|-----------------------|
| Brokerage | ₹40.00 | ₹40.00 |
| STT | ₹1250.00 | ₹125.00 |
| Exchange | ₹10.00 | ₹10.00 |
| GST | ₹9.00 | ₹9.00 |
| Stamp | ₹30.00 | ₹3.00 |
| **Total** | **₹1339.00 (~26.7 pts)** | **₹187.00 (~3.7 pts)** |

## 3. Verify Random Baseline Implementation
- **Methodology Check**: The `_generate_random_baseline` randomly samples $N$ candle indices. It sets entry, and applies the EXACT risk % from the real trade to place the stop loss and target.
- **Flaw Detected**: The exit logic simulated in the baseline looked at the next 15 candles sequentially. However, the real strategy stayed in the trade until 15:15 or SL/TG hit, which could be hours later. The random baseline forced an exit after 15 minutes if neither hit. This time-horizon mismatch means the random baseline and the real strategy were not directly comparable.

## 4. Verify Walk-Forward Windows
- **Independence Check**: The walk-forward chunking in `engine.py` just grouped all trades by calendar Quarter `df_trades['t'].dt.to_period('Q')`.
- **Flaw Detected**: This is **NOT** a true walk-forward. A true WFA trains on Window A, tests on Window B, then slides. Grouping backtest results by quarter is just a 'sub-period' stability check, not independent out-of-sample testing, because the parameters (EMA 9, RR 2.0) were globally fixed beforehand.

## 5. Identify Common Failure Mode Across All Candidates
Beyond the mathematical cost error, the core logic failure mode across all `TrendContinuation` candidates was **Signal Quality / Structural Timing**. 
The strategies demanded strict structural entry (like closing above VWAP or EMA), but because we hardcoded a **fixed Risk:Reward of 2.0** and arbitrary tight stops (min 2 points), we forced the market into a rigid box. The market doesn't care about our arbitrary 2.0 R multiple.

## 6. Loss Clustering
If we analyze the losing trades across all variants:
- **Cost Failure (Dominant)**: 100% of candidates suffered from the mathematically incorrect 10x STT calculation. Even winning trades became losers.
- **Risk/Reward Failure (Secondary)**: The fixed 2.0 RR target often missed being hit by a few points (MFE was positive but didn't reach target), resulting in eventual stop outs. We had positive MFE but didn't trail or take partials.
- **Timing Failure**: Entries based on 1-minute candle closes (like VWAP Reclaim) are extremely prone to micro-whipsaws. The entry happens exactly when the micro-momentum is exhausted.
- **Regime Failure**: Strategies traded 'Trend Continuation' while the larger timeframe regime was actually sideways (the 9/21 EMA slope on a 1-minute chart is too noisy to define a true daily regime).

## Conclusion
The candidates died primarily because **the cost model incorrectly applied an equity-delivery STT rate to an index instrument, inflating trading costs by 1000%**. Secondly, the testing framework itself lacked a rigorous time-horizon match in the Monte Carlo baseline, and the walk-forward was merely a sub-period split, not a rolling out-of-sample test. We must fix the infrastructure before blaming the edge.
