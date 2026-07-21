# Independent Publication Oracle V2

```json
{
  "base": {
    "completed_trades": 127,
    "compounded_return": 0.06646093450455637,
    "expectancy": 0.001052985524288867,
    "max_drawdown": -0.2575081174330085,
    "profit_factor": 1.1201818946794393
  },
  "concentration": {
    "five_best_arithmetic_contribution_pct": 133.8271739188512,
    "without_five_best_return": -0.10541185222333072
  },
  "control_truth_statuses": [
    {
      "artifact_source": "independent_random_v2",
      "construction_validity": "PASS",
      "control_id": "matched_random",
      "economic_result": "FAIL_SIGNAL_NOT_BETTER_THAN_RANDOM",
      "inconclusive": false,
      "limitations": [],
      "metrics": {
        "base_expectancy": 0.001052985524288867,
        "construction_status": "PASS",
        "economic_control_status": "FAIL_SIGNAL_NOT_BETTER_THAN_RANDOM",
        "empirical_p_value": 0.8271728271728271,
        "fraction_random_beating_base": 0.827,
        "random_mean_expectancy": 0.0027412840378825657,
        "random_median_expectancy": 0.0027738635853503963,
        "random_p05_expectancy": -0.00033150586565380445,
        "random_p95_expectancy": 0.005679415585824379,
        "replicates": 1000,
        "seed_end": 20261720,
        "seed_start": 20260721,
        "supports_structural_edge": false,
        "trades_per_replicate": [
          127
        ]
      },
      "present": true,
      "reason_codes": [
        "RANDOM_MEAN_EXCEEDS_BASE",
        "P_VALUE_0_827"
      ],
      "rejects_edge": true,
      "sample_count_comparability": "DIRECT_OR_DOCUMENTED",
      "supports_edge": false
    },
    {
      "artifact_source": "evidence_closure/negative_controls.json",
      "construction_validity": "PASS",
      "control_id": "one_session_signal_shift_backward",
      "economic_result": "ADVERSE_NEGATIVE_SHIFT_CONTROL",
      "inconclusive": false,
      "limitations": [],
      "metrics": {
        "CAGR": -0.16685276205704147,
        "completed_trades": 208,
        "expectancy": -0.013854611224215541,
        "max_drawdown": -0.9460183049527114,
        "profit_factor": 0.017781613557100357
      },
      "present": true,
      "reason_codes": [
        "BACKWARD_SHIFT_COLLAPSES"
      ],
      "rejects_edge": true,
      "sample_count_comparability": "DIRECT_OR_DOCUMENTED",
      "supports_edge": false
    },
    {
      "artifact_source": "evidence_closure/negative_controls.json",
      "construction_validity": "PASS",
      "control_id": "one_session_signal_shift_forward",
      "economic_result": "ADVERSE_POSITIVE_SHIFT_CONTROL",
      "inconclusive": false,
      "limitations": [
        "TIMING_CONTROL_NOT_DIRECTLY_TRADABLE"
      ],
      "metrics": {
        "CAGR": 0.0074803739649478285,
        "completed_trades": 207,
        "expectancy": 0.0006601032556382432,
        "max_drawdown": -0.12029821789714046,
        "profit_factor": 1.1554468456122224
      },
      "present": true,
      "reason_codes": [
        "FORWARD_SHIFT_POSITIVE"
      ],
      "rejects_edge": true,
      "sample_count_comparability": "TIMING_CONTROL_NOT_DIRECTLY_TRADABLE",
      "supports_edge": false
    },
    {
      "artifact_source": "evidence_closure/negative_controls.json",
      "construction_validity": "PASS",
      "control_id": "inverted_rsi_condition",
      "economic_result": "ADVERSE_INVERTED_RSI_BETTER_THAN_BASE_PF",
      "inconclusive": false,
      "limitations": [],
      "metrics": {
        "CAGR": 0.017806170409621958,
        "completed_trades": 302,
        "expectancy": 0.001023193479544558,
        "max_drawdown": -0.1094024832453816,
        "profit_factor": 1.2512810536459378
      },
      "present": true,
      "reason_codes": [
        "INVERTED_CONTROL_ADVERSE"
      ],
      "rejects_edge": true,
      "sample_count_comparability": "DIRECT_OR_DOCUMENTED",
      "supports_edge": false
    },
    {
      "artifact_source": "evidence_closure/negative_controls.json",
      "construction_validity": "PASS",
      "control_id": "trend_filter_removed",
      "economic_result": "INCONCLUSIVE_DIFFERENT_COUNT_UNIVERSE",
      "inconclusive": true,
      "limitations": [
        "NOT_COUNT_MATCHED"
      ],
      "metrics": {
        "CAGR": 5.214067174974524e-05,
        "completed_trades": 314,
        "expectancy": 0.0001740599233047417,
        "max_drawdown": -0.2780482765109422,
        "profit_factor": 1.029851130956394
      },
      "present": true,
      "reason_codes": [
        "COUNT_UNIVERSE_DIFFERS"
      ],
      "rejects_edge": false,
      "sample_count_comparability": "NOT_COUNT_MATCHED",
      "supports_edge": false
    },
    {
      "artifact_source": "evidence_closure/negative_controls.json",
      "construction_validity": "PASS",
      "control_id": "randomized_rsi_distribution",
      "economic_result": "WEAK_OR_NULL",
      "inconclusive": true,
      "limitations": [
        "NOT_COUNT_MATCHED"
      ],
      "metrics": {
        "CAGR": -0.00025957911557972224,
        "completed_trades": 407,
        "expectancy": 4.333449530970999e-05,
        "max_drawdown": -0.15225620516812532,
        "profit_factor": 1.0112522163984825
      },
      "present": true,
      "reason_codes": [
        "RANDOMIZED_RSI_WEAK"
      ],
      "rejects_edge": false,
      "sample_count_comparability": "NOT_COUNT_MATCHED",
      "supports_edge": false
    },
    {
      "artifact_source": "evidence_closure/negative_controls.json",
      "construction_validity": "PASS",
      "control_id": "block_bootstrap_confidence_interval",
      "economic_result": "FAIL_INTERVAL_CROSSES_ZERO",
      "inconclusive": false,
      "limitations": [],
      "metrics": {
        "p05": -0.0037455508147839836,
        "p50": 0.00126945828941777,
        "p95": 0.005349763350359977
      },
      "present": true,
      "reason_codes": [
        "BOOTSTRAP_CROSSES_ZERO"
      ],
      "rejects_edge": true,
      "sample_count_comparability": "DIRECT_OR_DOCUMENTED",
      "supports_edge": false
    },
    {
      "artifact_source": "evidence_closure/negative_controls.json",
      "construction_validity": "PASS",
      "control_id": "best_calendar_year_removed",
      "economic_result": "ADVERSE_BEST_YEAR_REMOVAL",
      "inconclusive": false,
      "limitations": [],
      "metrics": {
        "compound_return": -0.05428475213995343,
        "expectancy": 9.182627018403076e-05,
        "profit_factor": 1.0100134744537652,
        "removed_year": 2024,
        "sum_return": 0.010651847341347567,
        "trades": 116
      },
      "present": true,
      "reason_codes": [
        "BEST_YEAR_REMOVAL_NEGATIVE_COMPOUND"
      ],
      "rejects_edge": true,
      "sample_count_comparability": "DIRECT_OR_DOCUMENTED",
      "supports_edge": false
    },
    {
      "artifact_source": "evidence_closure/negative_controls.json",
      "construction_validity": "PASS",
      "control_id": "five_best_trades_removed",
      "economic_result": "FAIL_CONCENTRATED_PNL",
      "inconclusive": false,
      "limitations": [],
      "metrics": {
        "arithmetic_return_contribution_pct": 133.8271739188512,
        "authoritative_formula": "arithmetic_return_contribution_pct = sum(five_largest_net_returns) / sum(all_net_returns) * 100",
        "compounded_return_contribution_pct": 258.6072374834031,
        "counterfactual_maximum_drawdown_after_removing_five_best": -0.28290213632369443,
        "counterfactual_profit_factor_after_removing_five_best": 0.959345861467816,
        "counterfactual_total_return_after_removing_five_best": -0.10541185222333072,
        "current_269_28_reproduced": true,
        "five_best_returns": [
          0.0468709350667392,
          0.039531093835549,
          0.0320086650748966,
          0.0315865876449165,
          0.0289686760320581
        ],
        "five_best_trade_indices": [
          34,
          82,
          96,
          110,
          66
        ]
      },
      "present": true,
      "reason_codes": [
        "FIVE_BEST_REMOVAL_NEGATIVE"
      ],
      "rejects_edge": true,
      "sample_count_comparability": "DIRECT_OR_DOCUMENTED",
      "supports_edge": false
    },
    {
      "artifact_source": "evidence_closure/negative_controls.json",
      "construction_validity": "PASS",
      "control_id": "crash_period_only",
      "economic_result": "TAIL_RISK_ADVERSE",
      "inconclusive": false,
      "limitations": [],
      "metrics": {
        "compound_return": -0.24371930702201072,
        "expectancy": -0.24371930702201067,
        "profit_factor": 0.0,
        "sum_return": -0.24371930702201067,
        "trades": 1
      },
      "present": true,
      "reason_codes": [
        "CRASH_TRADE_LARGE_LOSS"
      ],
      "rejects_edge": true,
      "sample_count_comparability": "DIRECT_OR_DOCUMENTED",
      "supports_edge": false
    },
    {
      "artifact_source": "evidence_closure/negative_controls.json",
      "construction_validity": "PASS",
      "control_id": "crash_period_excluded",
      "economic_result": "INCONCLUSIVE_CRASH_EXCLUSION_LOOKAHEAD",
      "inconclusive": true,
      "limitations": [],
      "metrics": {
        "compound_return": 0.4101390454715743,
        "expectancy": 0.0029956227667198316,
        "profit_factor": 1.43434620603238,
        "sum_return": 0.3774484686066988,
        "trades": 126
      },
      "present": true,
      "reason_codes": [
        "CRASH_EXCLUSION_NOT_ACTIONABLE"
      ],
      "rejects_edge": false,
      "sample_count_comparability": "DIRECT_OR_DOCUMENTED",
      "supports_edge": false
    }
  ],
  "derived_verdict_before_final_report": {
    "index_signal_verdict": "NO_STRUCTURAL_EDGE",
    "overall_research_verdict": "NO_STRUCTURAL_EDGE",
    "reason_codes": [
      "ADVERSE_CONTROLS_PRESENT",
      "CONCENTRATED_PNL",
      "INSUFFICIENT_TRADABLE_DATA",
      "MATCHED_RANDOM_82_7_PERCENT_BEAT_BASE",
      "MATCHED_RANDOM_MEAN_EXCEEDS_BASE",
      "NEGATIVE_WITHOUT_FIVE_BEST",
      "TREND_FILTER_IMPROVES_POINT_ESTIMATE_BUT_UNCERTAIN"
    ],
    "tradable_instrument_verdict": "INSUFFICIENT_TRADABLE_DATA"
  },
  "fails_on_generic_pass_for_economic_failure": true,
  "fails_on_hardcoded_trend_or_tradable": true,
  "fails_on_wrong_verdict": true,
  "parameter_neighborhood": {
    "cannot_override_adverse_controls": true,
    "neighborhood_cells": 27,
    "positive_net_expectancy_pct": 100.0,
    "survives_2x_costs_pct": 96.29629629629629
  },
  "random": {
    "base_expectancy": 0.001052985524288867,
    "construction_status": "PASS",
    "economic_control_status": "FAIL_SIGNAL_NOT_BETTER_THAN_RANDOM",
    "empirical_p_value": 0.8271728271728271,
    "fraction_random_beating_base": 0.827,
    "random_mean_expectancy": 0.0027412840378825657,
    "random_median_expectancy": 0.0027738635853503963,
    "random_p05_expectancy": -0.00033150586565380445,
    "random_p95_expectancy": 0.005679415585824379,
    "replicates": 1000,
    "seed_end": 20261720,
    "seed_start": 20260721,
    "supports_structural_edge": false,
    "trades_per_replicate": [
      127
    ]
  },
  "status": "PASS",
  "tradable": {
    "derived_from_inventory": true,
    "etf_data": {
      "available": false,
      "bid_ask": false,
      "multi_year_adjusted_ohlc": false
    },
    "futures_data": {
      "available": false,
      "bid_ask": false,
      "multi_year_continuous_contract": false
    },
    "inventory_file_count_under_research_root": 43,
    "options_data": {
      "available_for_this_daily_strategy_translation": false,
      "requires_path_dependent_replay": true
    },
    "underlying_index_data": {
      "available": true,
      "sha256": "4f73bddb34e003074502c01191020adbade8b87ce095f4e722c49101db5a9d5d",
      "source": "runtime/research/rsi2_mean_reversion/frozen_data/nifty50_yfinance_2010-01-01_2026-01-01_auto_adjust_true.csv"
    },
    "verdict": "INSUFFICIENT_TRADABLE_DATA"
  },
  "trend_filter": {
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
}
```
