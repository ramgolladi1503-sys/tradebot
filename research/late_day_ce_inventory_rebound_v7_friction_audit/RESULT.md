# Late-Day CE Inventory Rebound V7 Friction Audit

Principal verdict: `FAIL_LATE_DAY_CE_REBOUND_TWO_PERCENT_TOTAL_FRICTION_GATE`

Required total friction: `2.0%` of premium return.

Maximum tested passing friction: `1.0%`.

Next tested failing friction: `1.5%`.

Required scenario: `{"combined_gate": false, "control_gate": true, "holdout_delayed": {"largest_winner_share": 0.4997624699034249, "mean_return_pct": 1.9613381827284426, "median_return_pct": 3.1263932419353826, "net_return_pct_sum": 23.53605819274131, "positive_folds": 1, "profit_factor": 1.5999310290486293, "remove_top_two_profit_factor": 0.6097472556578067, "total_folds": 1, "trades": 12, "win_rate": 0.6666666666666666}, "holdout_gate": false, "holdout_mirror": {"largest_winner_share": 0.5889404335328795, "mean_return_pct": -7.504849914356707, "median_return_pct": -3.955501443454885, "net_return_pct_sum": -90.05819897228048, "positive_folds": 0, "profit_factor": 0.3094284093388119, "remove_top_two_profit_factor": 0.031055639287641726, "total_folds": 1, "trades": 12, "win_rate": 0.25}, "holdout_primary": {"largest_winner_share": 0.40545601947327103, "mean_return_pct": 2.3993493888865363, "median_return_pct": 1.4612341772151884, "net_return_pct_sum": 28.792192666638435, "positive_folds": 1, "profit_factor": 1.9325055704491636, "remove_top_two_profit_factor": 0.7055699579318796, "total_folds": 1, "trades": 12, "win_rate": 0.6666666666666666}, "oof": {"largest_winner_share": 0.13763785882786816, "mean_return_pct": 0.8468247782352452, "median_return_pct": 1.0094465390613034, "net_return_pct_sum": 33.872991129409805, "positive_folds": 3, "profit_factor": 1.3367642661846646, "remove_top_two_profit_factor": 1.0362530370282905, "total_folds": 4, "trades": 40, "win_rate": 0.525}, "oof_gate": true, "total_friction_pct": 2.0}`

This is a descriptive sensitivity deduction, not an observed bid/ask or slippage model. No paper or live trading is authorized.
