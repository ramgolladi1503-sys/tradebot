# Strategy Failure Autopsy Report

## Strategy Classifications
- **TrendContinuation_EMA_PULLBACK**: G. Implementation/gating starvation
  - *Reason*: Only 6 trades generated.
- **TrendContinuation_OPENING_DRIVE**: F. Cost/slippage killed
  - *Reason*: Gross is positive but net is negative.
- **TrendContinuation_VWAP_RECLAIM**: E. Too rare to judge
  - *Reason*: No trades generated.
- **TrendContinuation_PDH_PDL**: G. Implementation/gating starvation
  - *Reason*: Only 4 trades generated.
- **TrendContinuation_BREAK_AND_RETEST**: G. Implementation/gating starvation
  - *Reason*: Only 1 trades generated.
- **ORB_BREAKOUT**: G. Implementation/gating starvation
  - *Reason*: Only 7 trades generated.
- **RangeReversal_SUPPORT**: E. Too rare to judge
  - *Reason*: No trades generated.
- **RangeReversal_RESISTANCE**: E. Too rare to judge
  - *Reason*: No trades generated.
- **MeanReversion_VWAP_PULLBACK**: D. Good signal, wrong regime
  - *Reason*: Signal produces some edge but diluted by regime.

## Cost & Expectancy Overview
| strategy                           |   gross_expectancy |   net_expectancy |   cost_per_trade |   pct_reaching_1.0r |   pct_reaching_2.0r |
|:-----------------------------------|-------------------:|-----------------:|-----------------:|--------------------:|--------------------:|
| TrendContinuation_EMA_PULLBACK     |           0.328102 |        -0.14562  |          200.606 |            0.5      |            0.5      |
| TrendContinuation_OPENING_DRIVE    |           0.422    |        -0.366275 |          200.661 |            0.648649 |            0.567568 |
| TrendContinuation_PDH_PDL          |           1.85933  |         1.29777  |          199.756 |            1        |            1        |
| TrendContinuation_BREAK_AND_RETEST |           1.92565  |         1.62764  |          200.415 |            1        |            1        |
| ORB_BREAKOUT                       |          -0.179938 |        -0.288862 |          250.193 |            0.285714 |            0.285714 |
| MeanReversion_VWAP_PULLBACK        |          -0.303806 |        -0.593747 |          257.565 |            0.533333 |            0.266667 |

## Exit Lab Comparison (Expectancy R)
| strategy                           |   ATR_Trail |   Fixed_1.5R |   Fixed_1R |   Fixed_2R |   Partial_1R |   Time_30 |   Time_45 |   VWAP_Failure |
|:-----------------------------------|------------:|-------------:|-----------:|-----------:|-------------:|----------:|----------:|---------------:|
| MeanReversion_VWAP_PULLBACK        |   -0.821689 |    -0.557193 |  -0.447869 |  -0.593747 |  -0.661702   | -0.882874 | -0.634693 |       -0.51394 |
| ORB_BREAKOUT                       |   -0.134247 |    -0.431698 |  -0.574534 |  -0.288862 |  -0.00579244 | -0.74537  | -0.751314 |       10.4418  |
| TrendContinuation_BREAK_AND_RETEST |    0.782302 |     1.12771  |   0.627784 |   1.62764  |   5.0941     |  6.13626  |  6.13626  |      450.988   |
| TrendContinuation_EMA_PULLBACK     |   -0.630398 |    -0.395583 |  -0.645545 |  -0.14562  |  -0.0907273  |  1.25647  |  0.914605 |       -1.7094  |
| TrendContinuation_OPENING_DRIVE    |   -0.951446 |    -0.505209 |  -0.756734 |  -0.366275 |  -0.0564772  |  5.28524  |  5.28524  |      295.419   |
| TrendContinuation_PDH_PDL          |    1.25043  |     0.797841 |   0.297915 |   1.29777  |   4.73478    | 10.3332   | 12.3604   |       -1.84244 |

