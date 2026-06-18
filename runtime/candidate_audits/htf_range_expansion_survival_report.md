# HTF_RANGE_EXPANSION Survival Report

We subjected the candidate to extreme friction and temporal slicing.

## Overall Stress Matrix (Net R)
|   net_baseline |   net_cost_125 |   net_cost_150 |   net_slip_2x |   net_slip_3x |
|---------------:|---------------:|---------------:|--------------:|--------------:|
|     -0.0638245 |      -0.105726 |      -0.147627 |     -0.132402 |      -0.20098 |

## Year-by-Year Expectancy
|   year |   trades |   net_baseline |
|-------:|---------:|---------------:|
|   2022 |     1144 |     -0.138687  |
|   2023 |     2091 |     -0.086285  |
|   2024 |     1161 |      0.0503942 |

## Quarter-by-Quarter Expectancy
| quarter   |   trades |   net_baseline |
|:----------|---------:|---------------:|
| 2022-Q3   |      597 |     -0.129503  |
| 2022-Q4   |      547 |     -0.148711  |
| 2023-Q1   |      566 |     -0.105469  |
| 2023-Q2   |      474 |     -0.0755517 |
| 2023-Q3   |      563 |     -0.0706129 |
| 2023-Q4   |      488 |     -0.0925412 |
| 2024-Q1   |      598 |      0.0901458 |
| 2024-Q2   |      563 |      0.0081714 |

## Regime Expectancy
| regime        |   trades |   net_baseline |
|:--------------|---------:|---------------:|
| CHOP          |     1212 |      -0.143939 |
| RANGE         |      474 |      -0.135367 |
| TREND_DOWN    |      722 |      -0.363289 |
| TREND_UP      |     1261 |      -0.116294 |
| VOL_EXPANSION |      727 |       0.504796 |

## Walk-Forward Assessment
✅ Candidate demonstrates structurally sound stability across timeframes.

## Friction Survivability
❌ Strategy edge evaporates entirely under a 50% cost escalation model.
❌ Strategy edge evaporates entirely under a 3x slippage decay model. Candidate cannot survive real-world execution variance.

## Conclusion
This diagnostic ruthlessly tests the viability of the candidate. Any negative flip in the core stress vectors immediately invalidates the strategy for live production.
