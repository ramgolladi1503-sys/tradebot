# Strategy Deep-Dive Final Report

## 1. Taxonomy Verdicts
| strategy                     | bucket                  | reason                      |
|:-----------------------------|:------------------------|:----------------------------|
| HTF_OPENING_DRIVE_CONT       | A. Dead signal          | 0 signals generated.        |
| HTF_PDH_PDL_HOLD             | E. Too rare to judge    | Only 3 trades.              |
| HTF_15M_TREND_CONT           | A. Dead signal          | 0 signals generated.        |
| HTF_15M_VWAP_PULLBACK        | A. Dead signal          | 0 signals generated.        |
| HTF_FAILED_BREAKOUT_REVERSAL | E. Too rare to judge    | Only 1 trades.              |
| ORB_BREAKOUT                 | F. Cost/slippage killed | Slippage drains gross edge. |

## 2. Scoreboard
| strategy                     |   signal_count |   final_trade_count |   gross_expectancy |   net_expectancy |       pf |   avg_mfe |   avg_mae |   target_reach_prob |   cost_drag |
|:-----------------------------|---------------:|--------------------:|-------------------:|-----------------:|---------:|----------:|----------:|--------------------:|------------:|
| HTF_PDH_PDL_HOLD             |              3 |                   3 |          -1.07039  |        -5.78813  | 0        |  0.208074 |  1.135    |            0        |    4.71775  |
| HTF_FAILED_BREAKOUT_REVERSAL |              1 |                   1 |           1.9      |        -4.81103  | 0        |  3.685    |  0        |            1        |    6.71103  |
| ORB_BREAKOUT                 |             39 |                  39 |           0.604836 |        -0.153408 | 0.764436 |  1.44538  |  0.749468 |            0.538462 |    0.758244 |

## 3. Regime Isolations
| strategy                     |     RANGE |   TREND_DOWN |   TREND_UP |   VOL_EXPANSION |
|:-----------------------------|----------:|-------------:|-----------:|----------------:|
| HTF_FAILED_BREAKOUT_REVERSAL |  -4.81103 |   nan        | nan        |      nan        |
| HTF_PDH_PDL_HOLD             | nan       |    -5.80841  |  -5.77799  |      nan        |
| ORB_BREAKOUT                 | nan       |    -0.765796 |   0.032246 |        0.226912 |
