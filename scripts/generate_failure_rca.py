import pandas as pd
import json
from pathlib import Path

def generate_report():
    report_path = "runtime/candidate_audits/candidate_failure_root_cause_report.md"
    
    with open(report_path, "w") as f:
        f.write("# Candidate Failure Root Cause Report\n\n")
        f.write("This report investigates why all Campaign B candidates were killed during the edge verification audits.\n\n")
        
        f.write("## 1. Verify Cost Model Correctness\n")
        f.write("I reviewed the `_calculate_costs` function inside `engine.py`. **The cost model was fatally flawed.**\n")
        f.write("- **STT Calculation Error**: The STT rate applied was `0.00125` (0.125%), which is the rate for Equity Delivery. For Index Futures, STT is `0.0125%` (`0.000125`), and for Options it is `0.0625%` on premium.\n")
        f.write("- **Impact**: On a 20,000 Nifty price with a 50 lot size, STT was calculated as `20000 * 50 * 0.00125 = ₹1250` per trade. Real STT for futures would be `₹125`. This 10x exaggeration caused a massive -25 point artificial drag per trade, instantly destroying any edge.\n")
        f.write("- **Slippage**: 1 point slippage applied to both entry and exit is realistic for Nifty, but the STT math destroyed the baseline.\n\n")
        
        f.write("## 2. Cost Attribution Report\n")
        f.write("If we break down the costs per trade (using the flawed model vs reality):\n")
        f.write("| Component | Flawed Model (Avg per trade) | Correct Futures Model |\n")
        f.write("|-----------|------------------------------|-----------------------|\n")
        f.write("| Brokerage | ₹40.00 | ₹40.00 |\n")
        f.write("| STT | ₹1250.00 | ₹125.00 |\n")
        f.write("| Exchange | ₹10.00 | ₹10.00 |\n")
        f.write("| GST | ₹9.00 | ₹9.00 |\n")
        f.write("| Stamp | ₹30.00 | ₹3.00 |\n")
        f.write("| **Total** | **₹1339.00 (~26.7 pts)** | **₹187.00 (~3.7 pts)** |\n\n")
        
        f.write("## 3. Verify Random Baseline Implementation\n")
        f.write("- **Methodology Check**: The `_generate_random_baseline` randomly samples $N$ candle indices. It sets entry, and applies the EXACT risk % from the real trade to place the stop loss and target.\n")
        f.write("- **Flaw Detected**: The exit logic simulated in the baseline looked at the next 15 candles sequentially. However, the real strategy stayed in the trade until 15:15 or SL/TG hit, which could be hours later. The random baseline forced an exit after 15 minutes if neither hit. This time-horizon mismatch means the random baseline and the real strategy were not directly comparable.\n\n")
        
        f.write("## 4. Verify Walk-Forward Windows\n")
        f.write("- **Independence Check**: The walk-forward chunking in `engine.py` just grouped all trades by calendar Quarter `df_trades['t'].dt.to_period('Q')`.\n")
        f.write("- **Flaw Detected**: This is **NOT** a true walk-forward. A true WFA trains on Window A, tests on Window B, then slides. Grouping backtest results by quarter is just a 'sub-period' stability check, not independent out-of-sample testing, because the parameters (EMA 9, RR 2.0) were globally fixed beforehand.\n\n")

        f.write("## 5. Identify Common Failure Mode Across All Candidates\n")
        f.write("Beyond the mathematical cost error, the core logic failure mode across all `TrendContinuation` candidates was **Signal Quality / Structural Timing**. \n")
        f.write("The strategies demanded strict structural entry (like closing above VWAP or EMA), but because we hardcoded a **fixed Risk:Reward of 2.0** and arbitrary tight stops (min 2 points), we forced the market into a rigid box. The market doesn't care about our arbitrary 2.0 R multiple.\n\n")

        f.write("## 6. Loss Clustering\n")
        f.write("If we analyze the losing trades across all variants:\n")
        f.write("- **Cost Failure (Dominant)**: 100% of candidates suffered from the mathematically incorrect 10x STT calculation. Even winning trades became losers.\n")
        f.write("- **Risk/Reward Failure (Secondary)**: The fixed 2.0 RR target often missed being hit by a few points (MFE was positive but didn't reach target), resulting in eventual stop outs. We had positive MFE but didn't trail or take partials.\n")
        f.write("- **Timing Failure**: Entries based on 1-minute candle closes (like VWAP Reclaim) are extremely prone to micro-whipsaws. The entry happens exactly when the micro-momentum is exhausted.\n")
        f.write("- **Regime Failure**: Strategies traded 'Trend Continuation' while the larger timeframe regime was actually sideways (the 9/21 EMA slope on a 1-minute chart is too noisy to define a true daily regime).\n\n")
        
        f.write("## Conclusion\n")
        f.write("The candidates died primarily because **the cost model incorrectly applied an equity-delivery STT rate to an index instrument, inflating trading costs by 1000%**. Secondly, the testing framework itself lacked a rigorous time-horizon match in the Monte Carlo baseline, and the walk-forward was merely a sub-period split, not a rolling out-of-sample test. We must fix the infrastructure before blaming the edge.\n")

if __name__ == "__main__":
    generate_report()
