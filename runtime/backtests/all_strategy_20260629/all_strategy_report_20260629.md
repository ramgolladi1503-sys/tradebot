# All-Strategy Available-Data Backtest 2026-06-29

Final verdict: **DIRECTIONAL_PROXY_ONLY, NOT_EXECUTABLE_OPTION_BACKTEST**

## What Was Actually Tested

- Data columns: `date, open, high, low, close, volume, instrument`
- Instruments: `BANKNIFTY, INDIAVIX, NIFTY, SENSEX`
- Timestamp range: `2026-06-29T09:15:00` to `2026-06-29T15:29:00`
- Volume quality: `ZERO_VOLUME`
- Entry rule: `current_candle_close`
- Entry timing note: Signals are evaluated with information available through the current 1-minute candle close. Proxy entry uses that same close, so this is an optimistic directional research proxy, not an executable fill model.
- Exit horizons: `5, 10, 15, 30` minutes
- Costs: `0.0, 2.0, 5.0, 10.0` bps
- PnL metric: underlying index directional proxy only.
- This report does not prove option PnL, option executability, fill quality, spread cost, depth, OI, Greeks, or IV edge.

## What Was Skipped And Why

| strategy | missing_inputs | reason |
| --- | --- | --- |
| vwap_orb_strategy | option_ltp\|bid_ask_spread\|zero_volume | emits option trade shape but available data has no option truth |
| volatility_scaled_trend_strategy | option_ltp | option premium is derived from index price |
| zero_hero_strategy | option_ltp | manual option-premium advisory without option LTP |
| pro.VolatilityExpansionStrategy | bid_ask_spread\|zero_volume | requires option executable data not present in parquet |
| pro.LiquidityImbalanceStrategy | option_ltp\|bid_ask_spread\|market_depth | requires option executable data not present in parquet |
| pro.VWAPMeanReversionStrategy | bid_ask_spread | requires option executable data not present in parquet |
| pro.OptionsFlowStrategy | option_ltp\|open_interest\|implied_volatility | requires option executable data not present in parquet |
| core.zero_hero_candidate_generator.build_zero_hero_candidate_intents | option_ltp\|zero_volume | requires option premium truth and expiry option context |
| core.candidate_generator.generate_candidates | option_ltp\|open_interest\|implied_volatility\|greeks | runtime candidate generator requires option chain/contracts absent from parquet |
| movement.option_pressure_confirmation_v1 | option_ltp\|bid_ask_spread\|market_depth\|zero_volume | requires option executable data not present in parquet |

## Proxy-Positive Strategies

- core.mean_reversion_candidate_generator.build_mean_reversion_candidate_intents
- ensemble.mean_reversion_signal

## Proxy-Negative Strategies

- banknifty_intraday.generate_signal
- core.breakout_candidate_generator.build_breakout_candidate_intents
- core.vwap_candidate_generator.build_vwap_candidate_intents
- ensemble.ensemble_signal
- ensemble.event_breakout_signal
- ensemble.micro_pattern_signal
- ensemble.orb_breakout_signal
- ensemble.trend_vwap_signal
- nifty_intraday.generate_signal
- pro.TimeWindowStrategy
- sensex_intraday.generate_signal

## Unsupported Due To Missing Option Data

- vwap_orb_strategy
- volatility_scaled_trend_strategy
- zero_hero_strategy
- pro.VolatilityExpansionStrategy
- pro.LiquidityImbalanceStrategy
- pro.VWAPMeanReversionStrategy
- pro.OptionsFlowStrategy
- core.zero_hero_candidate_generator.build_zero_hero_candidate_intents
- core.candidate_generator.generate_candidates
- movement.option_pressure_confirmation_v1

## Signal Spam

- banknifty_intraday.generate_signal
- core.breakout_candidate_generator.build_breakout_candidate_intents
- core.mean_reversion_candidate_generator.build_mean_reversion_candidate_intents
- core.vwap_candidate_generator.build_vwap_candidate_intents
- ensemble.ensemble_signal
- ensemble.event_breakout_signal
- ensemble.mean_reversion_signal
- ensemble.micro_pattern_signal
- ensemble.orb_breakout_signal
- ensemble.trend_vwap_signal
- nifty_intraday.generate_signal
- pro.TimeWindowStrategy
- sensex_intraday.generate_signal

## Invalid Volume / VWAP Assumptions

- nifty_intraday.generate_signal
- banknifty_intraday.generate_signal
- sensex_intraday.generate_signal
- ensemble.trend_vwap_signal
- ensemble.mean_reversion_signal
- ensemble.orb_breakout_signal
- ensemble.ensemble_signal
- core.breakout_candidate_generator.build_breakout_candidate_intents
- core.vwap_candidate_generator.build_vwap_candidate_intents
- core.mean_reversion_candidate_generator.build_mean_reversion_candidate_intents
- movement.opening_drive_v1
- movement.opening_range_retest_v1
- movement.compression_breakout_v1
- movement.trend_pullback_v1
- movement.vwap_reclaim_rejection_v1
- movement.failed_breakout_trap_v1
- movement.exhaustion_reversal_v1
- movement.mean_reversion_extension_v1
- movement.event_volatility_expansion_v1
- movement.late_day_momentum_v1

## Top Proxy Rows At 15m / 2bps

| strategy | exit_horizon_min | cost_bps | trade_count | win_rate | avg_gross_bps | avg_net_bps | total_net_points | expectancy | max_drawdown_proxy | profit_factor_proxy | median_return_bps | p25_return_bps | p75_return_bps | long_count | short_count | instrument_breakdown | time_of_day_breakdown | spam_flags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ensemble.mean_reversion_signal | 15 | 2.0 | 123 | 0.634146 | 3.582504 | 1.582504 | 1151.673998 | 9.363203 | -273.273802 | 2.169588 | 1.805287 | -1.819928 | 4.885381 | 123 | 0 | {"BANKNIFTY": 44, "NIFTY": 42, "SENSEX": 37} | {"late_1400_close": 1, "midday_1200_1359": 122} | SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION_WITHOUT_COOLDOWN |
| core.mean_reversion_candidate_generator.build_mean_reversion_candidate_intents | 15 | 2.0 | 86 | 0.546512 | 2.943449 | 0.943449 | 599.706036 | 6.973326 | -346.508738 | 1.728418 | 0.849459 | -3.89373 | 4.121225 | 86 | 0 | {"BANKNIFTY": 35, "NIFTY": 26, "SENSEX": 25} | {"midday_1200_1359": 86} | SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION_WITHOUT_COOLDOWN |
| banknifty_intraday.generate_signal | 15 | 2.0 | 530 | 0.428302 | 1.618126 | -0.381874 | -1420.88555 | -2.680916 | -4005.39241 | 0.871009 | -1.624458 | -6.641379 | 5.267094 | 16 | 514 | {"BANKNIFTY": 154, "NIFTY": 190, "SENSEX": 186} | {"late_1400_close": 120, "mid_morning_1000_1159": 54, "midday_1200_1359": 356} | SIGNAL_SPAM_RISK:MORE_THAN_100_TRADES_PER_DAY_PER_INSTRUMENT\|SIGNAL_SPAM_RISK:MORE_THAN_50_PERCENT_CANDLES\|SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION_WITHOUT_COOLDOWN |
| nifty_intraday.generate_signal | 15 | 2.0 | 530 | 0.428302 | 1.618126 | -0.381874 | -1420.88555 | -2.680916 | -4005.39241 | 0.871009 | -1.624458 | -6.641379 | 5.267094 | 16 | 514 | {"BANKNIFTY": 154, "NIFTY": 190, "SENSEX": 186} | {"late_1400_close": 120, "mid_morning_1000_1159": 54, "midday_1200_1359": 356} | SIGNAL_SPAM_RISK:MORE_THAN_100_TRADES_PER_DAY_PER_INSTRUMENT\|SIGNAL_SPAM_RISK:MORE_THAN_50_PERCENT_CANDLES\|SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION_WITHOUT_COOLDOWN |
| sensex_intraday.generate_signal | 15 | 2.0 | 530 | 0.428302 | 1.618126 | -0.381874 | -1420.88555 | -2.680916 | -4005.39241 | 0.871009 | -1.624458 | -6.641379 | 5.267094 | 16 | 514 | {"BANKNIFTY": 154, "NIFTY": 190, "SENSEX": 186} | {"late_1400_close": 120, "mid_morning_1000_1159": 54, "midday_1200_1359": 356} | SIGNAL_SPAM_RISK:MORE_THAN_100_TRADES_PER_DAY_PER_INSTRUMENT\|SIGNAL_SPAM_RISK:MORE_THAN_50_PERCENT_CANDLES\|SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION_WITHOUT_COOLDOWN |
| ensemble.orb_breakout_signal | 15 | 2.0 | 264 | 0.378788 | 0.989948 | -1.010052 | -1446.901344 | -5.480687 | -2546.65212 | 0.77327 | -3.041764 | -7.717081 | 5.336493 | 0 | 264 | {"BANKNIFTY": 77, "NIFTY": 100, "SENSEX": 87} | {"late_1400_close": 76, "mid_morning_1000_1159": 3, "midday_1200_1359": 185} | SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION_WITHOUT_COOLDOWN |
| core.breakout_candidate_generator.build_breakout_candidate_intents | 15 | 2.0 | 205 | 0.331707 | 0.229107 | -1.770893 | -1928.065894 | -9.405199 | -2530.068794 | 0.634809 | -4.357792 | -8.083477 | 3.906194 | 0 | 205 | {"BANKNIFTY": 59, "NIFTY": 83, "SENSEX": 63} | {"late_1400_close": 52, "midday_1200_1359": 153} | SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION_WITHOUT_COOLDOWN |
| core.vwap_candidate_generator.build_vwap_candidate_intents | 15 | 2.0 | 605 | 0.441322 | 1.515083 | -0.484917 | -2076.694472 | -3.432553 | -4862.890086 | 0.846248 | -1.500581 | -6.843009 | 5.719076 | 44 | 561 | {"BANKNIFTY": 183, "NIFTY": 206, "SENSEX": 216} | {"late_1400_close": 134, "mid_morning_1000_1159": 111, "midday_1200_1359": 360} | SIGNAL_SPAM_RISK:MORE_THAN_100_TRADES_PER_DAY_PER_INSTRUMENT\|SIGNAL_SPAM_RISK:MORE_THAN_50_PERCENT_CANDLES\|SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION_WITHOUT_COOLDOWN |
| ensemble.trend_vwap_signal | 15 | 2.0 | 605 | 0.441322 | 1.515083 | -0.484917 | -2076.694472 | -3.432553 | -4862.890086 | 0.846248 | -1.500581 | -6.843009 | 5.719076 | 44 | 561 | {"BANKNIFTY": 183, "NIFTY": 206, "SENSEX": 216} | {"late_1400_close": 134, "mid_morning_1000_1159": 111, "midday_1200_1359": 360} | SIGNAL_SPAM_RISK:MORE_THAN_100_TRADES_PER_DAY_PER_INSTRUMENT\|SIGNAL_SPAM_RISK:MORE_THAN_50_PERCENT_CANDLES\|SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION_WITHOUT_COOLDOWN |
| pro.TimeWindowStrategy | 15 | 2.0 | 183 | 0.295082 | -0.762559 | -2.762559 | -2527.209066 | -13.809886 | -2518.242076 | 0.485383 | -2.8972 | -7.562224 | 1.156186 | 82 | 101 | {"BANKNIFTY": 61, "NIFTY": 61, "SENSEX": 61} | {"late_1400_close": 135, "mid_morning_1000_1159": 3, "open_0915_0959": 45} | SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION_WITHOUT_COOLDOWN |
| ensemble.ensemble_signal | 15 | 2.0 | 635 | 0.44252 | 1.414393 | -0.585607 | -2659.623374 | -4.188383 | -4992.342784 | 0.829714 | -1.352928 | -6.838108 | 5.843536 | 68 | 567 | {"BANKNIFTY": 211, "NIFTY": 197, "SENSEX": 227} | {"late_1400_close": 143, "mid_morning_1000_1159": 123, "midday_1200_1359": 359, "open_0915_0959": 10} | SIGNAL_SPAM_RISK:MORE_THAN_100_TRADES_PER_DAY_PER_INSTRUMENT\|SIGNAL_SPAM_RISK:MORE_THAN_50_PERCENT_CANDLES\|SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION_WITHOUT_COOLDOWN |
| ensemble.micro_pattern_signal | 15 | 2.0 | 225 | 0.466667 | -0.105756 | -2.105756 | -3028.712242 | -13.460943 | -3066.188842 | 0.64319 | -0.899927 | -10.332075 | 5.468414 | 107 | 118 | {"BANKNIFTY": 101, "NIFTY": 22, "SENSEX": 102} | {"late_1400_close": 46, "mid_morning_1000_1159": 77, "midday_1200_1359": 92, "open_0915_0959": 10} | SIGNAL_SPAM_RISK:MORE_THAN_100_TRADES_PER_DAY_PER_INSTRUMENT\|SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION_WITHOUT_COOLDOWN |
| ensemble.event_breakout_signal | 15 | 2.0 | 943 | 0.431601 | -0.089691 | -2.089691 | -10045.883962 | -10.653111 | -10036.916972 | 0.632477 | -1.88133 | -8.427896 | 4.846923 | 419 | 524 | {"BANKNIFTY": 314, "NIFTY": 315, "SENSEX": 314} | {"late_1400_close": 179, "mid_morning_1000_1159": 359, "midday_1200_1359": 360, "open_0915_0959": 45} | SIGNAL_SPAM_RISK:MORE_THAN_100_TRADES_PER_DAY_PER_INSTRUMENT\|SIGNAL_SPAM_RISK:MORE_THAN_50_PERCENT_CANDLES\|SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION_WITHOUT_COOLDOWN |

## Safety

- broker_api_called=false
- is_order_action=false
- allowed_for_live_execution=false
- read_only=true
