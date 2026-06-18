# Trade Management Laboratory Report

We froze the exact entry signals for `EMA_PULLBACK` and `OPENING_DRIVE` and simulated 8 distinct trade management scenarios.

## Exit Comparison Matrix

### TrendContinuation_EMA_PULLBACK
| Exit Type | Expectancy (R) | Win Rate |
|-----------|----------------|----------|
| Partial_1R | 0.70 | 50.0% |
| Time_30 | 0.53 | 25.0% |
| Time_45 | 0.53 | 25.0% |
| Fixed_2R | 0.21 | 50.0% |
| Fixed_1.5R | -0.04 | 50.0% |
| ATR_Trail | -0.11 | 50.0% |
| Fixed_1R | -0.29 | 50.0% |
| VWAP_Failure | -0.91 | 25.0% |

### TrendContinuation_OPENING_DRIVE
| Exit Type | Expectancy (R) | Win Rate |
|-----------|----------------|----------|
| Fixed_1.5R | -0.21 | 58.1% |
| Fixed_1R | -0.43 | 54.8% |
| Partial_1R | -0.77 | 19.4% |
| Fixed_2R | -0.82 | 29.0% |
| ATR_Trail | -0.84 | 19.4% |
| VWAP_Failure | -1.73 | 0.0% |
| Time_30 | -1.84 | 3.2% |
| Time_45 | -1.84 | 3.2% |

## Stop Loss Postmortem Analysis
Did dynamic exits save us from hitting max stop loss? Let's observe the distribution of exit reasons.
| strategy                        | exit_type    |   STOP_LOSS |   TARGET |   TIME_STOP |   VWAP_FAIL |
|:--------------------------------|:-------------|------------:|---------:|------------:|------------:|
| TrendContinuation_EMA_PULLBACK  | ATR_Trail    |           4 |        0 |           0 |           0 |
| TrendContinuation_EMA_PULLBACK  | Fixed_1.5R   |           2 |        2 |           0 |           0 |
| TrendContinuation_EMA_PULLBACK  | Fixed_1R     |           2 |        2 |           0 |           0 |
| TrendContinuation_EMA_PULLBACK  | Fixed_2R     |           2 |        2 |           0 |           0 |
| TrendContinuation_EMA_PULLBACK  | Partial_1R   |           3 |        1 |           0 |           0 |
| TrendContinuation_EMA_PULLBACK  | Time_30      |           3 |        0 |           1 |           0 |
| TrendContinuation_EMA_PULLBACK  | Time_45      |           3 |        0 |           1 |           0 |
| TrendContinuation_EMA_PULLBACK  | VWAP_Failure |           2 |        0 |           0 |           2 |
| TrendContinuation_OPENING_DRIVE | ATR_Trail    |          31 |        0 |           0 |           0 |
| TrendContinuation_OPENING_DRIVE | Fixed_1.5R   |          13 |       18 |           0 |           0 |
| TrendContinuation_OPENING_DRIVE | Fixed_1R     |          12 |       19 |           0 |           0 |
| TrendContinuation_OPENING_DRIVE | Fixed_2R     |          22 |        9 |           0 |           0 |
| TrendContinuation_OPENING_DRIVE | Partial_1R   |          31 |        0 |           0 |           0 |
| TrendContinuation_OPENING_DRIVE | Time_30      |          27 |        0 |           4 |           0 |
| TrendContinuation_OPENING_DRIVE | Time_45      |          27 |        0 |           4 |           0 |
| TrendContinuation_OPENING_DRIVE | VWAP_Failure |          31 |        0 |           0 |           0 |

## Conclusion
We can clearly see from the expectancy metrics whether target/stop modifications produce a positive net edge without changing entry criteria.
