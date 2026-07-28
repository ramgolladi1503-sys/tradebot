# Late-Day CE Inventory Rebound V6 — Final Research Verdict

Principal verdict: `STRUCTURAL_EDGE_FOUND_LATE_DAY_CE_INVENTORY_REBOUND_5M_CANDLE_PROXY_RESEARCH_GATE`

Structural edge found: `True`

OOF metrics: `{"bootstrap_mean_ci_high": 4.975099918218806, "bootstrap_mean_ci_low": 0.19701594973537814, "largest_winner_share": 0.11390874445690796, "mean_return_pct": 2.7468247782352453, "median_return_pct": 2.909446539061303, "net_return_pct_sum": 109.87299112940981, "positive_folds": 4, "profit_factor": 2.5860799310710134, "remove_top_two_profit_factor": 2.0948874085520206, "stress_profit_factor": 1.8918994726398533, "total_folds": 4, "trades": 40, "win_rate": 0.65}`

Untouched holdout metrics: `{"bootstrap_mean_ci_high": 10.116293607519726, "bootstrap_mean_ci_low": -1.1893963780294237, "largest_winner_share": 0.34851698910539075, "mean_return_pct": 4.299349388886537, "median_return_pct": 3.3612341772151884, "net_return_pct_sum": 51.59219266663844, "positive_folds": 1, "profit_factor": 3.2165249408162953, "remove_top_two_profit_factor": 1.425720126304276, "stress_profit_factor": 2.5177834285047695, "total_folds": 1, "trades": 12, "win_rate": 0.6666666666666666}`

Mirror PE control: `{"bootstrap_mean_ci_high": 4.6132768123485635, "bootstrap_mean_ci_low": -17.599935295608244, "largest_winner_share": 0.5558810734619724, "mean_return_pct": -5.604849914356708, "median_return_pct": -2.055501443454885, "net_return_pct_sum": -67.2581989722805, "positive_folds": 0, "profit_factor": 0.407045629320422, "remove_top_two_profit_factor": 0.05349484646046058, "stress_profit_factor": 0.35707525388490036, "total_folds": 1, "trades": 12, "win_rate": 0.3333333333333333}`

Five-minute delayed CE control: `{"bootstrap_mean_ci_high": 10.891106270014266, "bootstrap_mean_ci_low": -2.218868936745152, "largest_winner_share": 0.4267012347720283, "mean_return_pct": 3.8613381827284434, "median_return_pct": 5.0263932419353825, "net_return_pct_sum": 46.33605819274132, "positive_folds": 1, "profit_factor": 2.464881216687709, "remove_top_two_profit_factor": 1.1166531574451832, "stress_profit_factor": 2.0086509743219563, "total_folds": 1, "trades": 12, "win_rate": 0.6666666666666666}`

Signal oracle: `PASS_INDEPENDENT_SIGNAL_MEMBERSHIP_ORACLE` with `52` exact identities.

Claim boundary: historical OHLCV candle-proxy research edge only. The holdout has 12 trades and its bootstrap mean CI crosses zero. No bid/ask execution certification, paper authorization, or live authorization is claimed.
