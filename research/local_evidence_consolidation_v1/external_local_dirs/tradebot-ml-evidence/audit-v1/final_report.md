# ML Strategy Discovery Real-Run Audit v1

verdict: BOTH_CANDIDATES_UNSTABLE
claim_boundary: UNDERLYING_RESEARCH_LABELS_NOT_OPTION_PNL
NO_STRUCTURAL_EDGE_OR_OPTION_PROFITABILITY_PROVEN

## Source Counts
{
  "certified_records": 1512,
  "selected_nifty_records": 510,
  "sides": {
    "LONG": {
      "adapter_records": 510,
      "adapter_source_rows": 191250,
      "dataset_rows": 175888,
      "dataset_sessions": 510,
      "split_rows": {
        "DEVELOPMENT": 105508,
        "HOLDOUT_LOCKED": 35190,
        "VALIDATION": 35190
      }
    },
    "SHORT": {
      "adapter_records": 510,
      "adapter_source_rows": 191250,
      "dataset_rows": 175888,
      "dataset_sessions": 510,
      "split_rows": {
        "DEVELOPMENT": 105508,
        "HOLDOUT_LOCKED": 35190,
        "VALIDATION": 35190
      }
    }
  }
}

## Rule Oracle
{
  "LONG": {
    "all_support_rate": 0.0005514873101064313,
    "all_support_rows": 97,
    "candidate_id": "tree_rule_edb855245d2f",
    "conditions": [
      {
        "feature": "distance_from_opening_high_atr",
        "operator": ">",
        "threshold": -0.8024527728557587
      },
      {
        "feature": "compression_ratio_5_20",
        "operator": "<=",
        "threshold": 0.13630171120166779
      },
      {
        "feature": "distance_from_previous_high_atr",
        "operator": "<=",
        "threshold": 2.4608426094055176
      }
    ],
    "development_rows": 53,
    "development_sessions": 22,
    "extremely_rare": true,
    "imputation_dependent_values": {
      "compression_ratio_5_20": 0,
      "distance_from_opening_high_atr": 0,
      "distance_from_previous_high_atr": 0
    },
    "near_universal": false
  },
  "SHORT": {
    "all_support_rate": 0.00038092422450650414,
    "all_support_rows": 67,
    "candidate_id": "tree_rule_7a6855962eee",
    "conditions": [
      {
        "feature": "distance_from_opening_high_atr",
        "operator": "<=",
        "threshold": -0.7935418784618378
      },
      {
        "feature": "trend_slope_10_atr",
        "operator": "<=",
        "threshold": 0.06959715485572815
      },
      {
        "feature": "distance_from_opening_low_atr",
        "operator": ">",
        "threshold": 26.538219451904297
      },
      {
        "feature": "ret_3",
        "operator": "<=",
        "threshold": -6.273878534557298e-05
      }
    ],
    "development_rows": 59,
    "development_sessions": 6,
    "extremely_rare": true,
    "imputation_dependent_values": {
      "distance_from_opening_high_atr": 0,
      "distance_from_opening_low_atr": 0,
      "ret_3": 0,
      "trend_slope_10_atr": 0
    },
    "near_universal": false
  },
  "agreement": "INDEPENDENT_RULE_ORACLE_REPRODUCED_DEVELOPMENT_SUPPORT"
}

## LONG Metrics
{
  "average_bars_to_event": 2.7142857142857144,
  "barrier_outcome_counts": {
    "STOP_FIRST": 11,
    "TARGET_FIRST": 10
  },
  "by_expiry_context": {
    "nan": {
      "expectancy_r": 0.25714285714285723,
      "rows": 21,
      "sessions": 12,
      "total_r": 5.400000000000001
    }
  },
  "by_month": {
    "2025-09": {
      "expectancy_r": 1.2,
      "rows": 1,
      "sessions": 1,
      "total_r": 1.2
    },
    "2025-10": {
      "expectancy_r": 0.17142857142857146,
      "rows": 7,
      "sessions": 4,
      "total_r": 1.2000000000000002
    },
    "2025-11": {
      "expectancy_r": 0.42857142857142855,
      "rows": 7,
      "sessions": 3,
      "total_r": 3.0
    },
    "2025-12": {
      "expectancy_r": 0.6,
      "rows": 3,
      "sessions": 2,
      "total_r": 1.7999999999999998
    },
    "2026-01": {
      "expectancy_r": -0.6,
      "rows": 1,
      "sessions": 1,
      "total_r": -0.6
    },
    "2026-02": {
      "expectancy_r": -0.6,
      "rows": 2,
      "sessions": 1,
      "total_r": -1.2
    }
  },
  "by_regime": {
    "-1.0": {
      "expectancy_r": 1.2,
      "rows": 1,
      "sessions": 1,
      "total_r": 1.2
    },
    "0.0": {
      "expectancy_r": 0.3,
      "rows": 8,
      "sessions": 6,
      "total_r": 2.4
    },
    "1.0": {
      "expectancy_r": 0.6,
      "rows": 6,
      "sessions": 5,
      "total_r": 3.5999999999999996
    },
    "nan": {
      "expectancy_r": -0.3,
      "rows": 6,
      "sessions": 5,
      "total_r": -1.7999999999999998
    }
  },
  "by_time_bucket": {
    "0.0": {
      "expectancy_r": 0.09230769230769229,
      "rows": 13,
      "sessions": 9,
      "total_r": 1.1999999999999997
    },
    "1.0": {
      "expectancy_r": 0.3,
      "rows": 6,
      "sessions": 2,
      "total_r": 1.7999999999999998
    },
    "2.0": {
      "expectancy_r": 1.2,
      "rows": 2,
      "sessions": 1,
      "total_r": 2.4
    }
  },
  "by_year": {
    "2025": {
      "expectancy_r": 0.4,
      "rows": 18,
      "sessions": 10,
      "total_r": 7.2
    },
    "2026": {
      "expectancy_r": -0.6,
      "rows": 3,
      "sessions": 2,
      "total_r": -1.7999999999999998
    }
  },
  "gross_negative_r": 6.599999999999999,
  "gross_positive_r": 11.999999999999998,
  "label_expectancy_r": 0.25714285714285723,
  "label_profit_factor": 1.8181818181818183,
  "mae_atr_mean": -3.2601072496432937,
  "maximum_drawdown_r": -1.7999999999999998,
  "mean_label_return_r": 0.25714285714285723,
  "median_bars_to_event": 2.0,
  "median_label_return_r": -0.6,
  "metric_name": "underlying research-label metrics",
  "mfe_atr_mean": 3.5386090962653456,
  "row_support_rate": 0.0005967604433077579,
  "rows": 21,
  "session_support_rate": 0.11764705882352941,
  "sessions": 12,
  "total_label_r": 5.400000000000001,
  "win_rate": 0.47619047619047616
}

## SHORT Metrics
{
  "average_bars_to_event": 2.125,
  "barrier_outcome_counts": {
    "STOP_FIRST": 8
  },
  "by_expiry_context": {
    "nan": {
      "expectancy_r": -0.6,
      "rows": 8,
      "sessions": 1,
      "total_r": -4.8
    }
  },
  "by_month": {
    "2026-02": {
      "expectancy_r": -0.6,
      "rows": 8,
      "sessions": 1,
      "total_r": -4.8
    }
  },
  "by_regime": {
    "-1.0": {
      "expectancy_r": -0.6,
      "rows": 1,
      "sessions": 1,
      "total_r": -0.6
    },
    "0.0": {
      "expectancy_r": -0.6,
      "rows": 4,
      "sessions": 1,
      "total_r": -2.4
    },
    "nan": {
      "expectancy_r": -0.6,
      "rows": 3,
      "sessions": 1,
      "total_r": -1.7999999999999998
    }
  },
  "by_time_bucket": {
    "2.0": {
      "expectancy_r": -0.6,
      "rows": 8,
      "sessions": 1,
      "total_r": -4.8
    }
  },
  "by_year": {
    "2026": {
      "expectancy_r": -0.6,
      "rows": 8,
      "sessions": 1,
      "total_r": -4.8
    }
  },
  "gross_negative_r": 4.8,
  "gross_positive_r": 0.0,
  "label_expectancy_r": -0.6,
  "label_profit_factor": 0.0,
  "mae_atr_mean": -7.108054592926946,
  "maximum_drawdown_r": -4.2,
  "mean_label_return_r": -0.6,
  "median_bars_to_event": 2.0,
  "median_label_return_r": -0.6,
  "metric_name": "underlying research-label metrics",
  "mfe_atr_mean": 0.9970367820173107,
  "row_support_rate": 0.00022733731173628873,
  "rows": 8,
  "session_support_rate": 0.00980392156862745,
  "sessions": 1,
  "total_label_r": -4.8,
  "win_rate": 0.0
}

## Holdout Isolation
{
  "acknowledgement_token_imported": false,
  "forbidden_outcome_columns": [
    "barrier_outcome",
    "bars_to_event",
    "future_close_return_atr",
    "label_entry_price",
    "label_entry_timestamp",
    "label_return_r",
    "label_terminal_timestamp",
    "mae_atr",
    "mfe_atr"
  ],
  "holdout_performance_metrics_emitted": false,
  "isolation_status": "HOLDOUT_OUTCOMES_NOT_CONSUMED_BY_METRIC_OR_CONTROL_FUNCTIONS",
  "long_holdout_rows": 35190,
  "long_holdout_sessions": 102,
  "short_holdout_rows": 35190,
  "short_holdout_sessions": 102
}
