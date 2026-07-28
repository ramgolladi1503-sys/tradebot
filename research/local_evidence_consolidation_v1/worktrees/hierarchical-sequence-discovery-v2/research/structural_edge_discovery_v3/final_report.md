# Structural Edge Discovery V3 Final Report

Branch: research/structural-edge-discovery-v3
Base commit: ebf0c59dcc8fa8d9bb57572c5331282dd89e473b
Sources inventoried: 1966
Sessions used: 100
Rows used: 37500
Event families: compression_expansion_down, compression_expansion_up, long_lower_wick, long_upper_wick, opening_range_high_break, opening_range_low_break, session_high_sweep_reject, session_low_sweep_reclaim, vwap_reclaim, vwap_rejection
Feature count: 21
Candidates generated/replayed: 30
Walk-forward status: COMPLETE
Holdout status: OPENED_AFTER_FREEZE
Independent audit pass: True
Determinism artifact hash: a92b5fbf6350c370728325d719c86c602ba2e93cb5f10d251ce98b582002fe76
Final verdict: FAILED_ROBUSTNESS
Best candidate: {'candidate_id': 'SEDV3_1c0b38601852', 'trade_count': 84, 'gross_pnl': 2288.75, 'net_pnl': 2162.75, 'charges': 126.0, 'slippage_sensitivity': {'cost_points_per_trade': 1.5, 'net_at_2x_cost': 2036.75}, 'win_rate': 0.6309523809523809, 'average_win': 92.13584905660399, 'average_loss': -87.7564516129036, 'net_expectancy': 25.74702380952381, 'profit_factor': 1.7949971512065985, 'max_drawdown': -588.1000000000276, 'recovery_factor': 3.677520829790679, 'mfe_mean': 114.00535714285668, 'mae_mean': 77.13690476190546, 'target_count': 53, 'timeout_count': 31, 'month_breakdown': {'2024-07': 1761.5500000000102, '2024-08': 401.1999999999898}, 'top5_trade_contribution': 0.5211189457866122, 'top10_trade_contribution': 0.9265980811466848}

This is research-only. No production registration, broker access, live execution, risk, feed, dashboard, or deployment code was changed.
