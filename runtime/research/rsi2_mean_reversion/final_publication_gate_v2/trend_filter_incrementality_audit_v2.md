# Trend Filter Incrementality Audit V2

```json
{
  "audit": {
    "base_trades": 127,
    "candidate_universe": "different",
    "costs": "same index proxy diagnostic base costs",
    "execution_timing": "same next-open model",
    "removed_filter_trades": 314,
    "trade_count_comparable": false
  },
  "base": {
    "completed_trades": 127,
    "compounded_return": 0.06646093450455637,
    "expectancy": 0.001052985524288867,
    "max_drawdown": -0.2575081174330085,
    "profit_factor": 1.1201818946794393
  },
  "does_not_salvage_rsi2_edge": true,
  "trend_filter_removed": {
    "CAGR": 5.214067174974524e-05,
    "completed_trades": 314,
    "expectancy": 0.0001740599233047417,
    "max_drawdown": -0.2780482765109422,
    "profit_factor": 1.029851130956394
  },
  "verdict": "TREND_FILTER_IMPROVES_POINT_ESTIMATE_BUT_UNCERTAIN"
}
```
