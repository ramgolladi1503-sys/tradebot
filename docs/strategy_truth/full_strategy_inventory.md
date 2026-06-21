# Full Strategy Inventory

This inventory documents the 14 explicitly implemented strategy components identified across TradeBuilder, ProStrategyEngine, and candidate generators.

| Strategy Name | Family | Current Status | Logic File |
|---|---|---|---|
| **ORB_BREAKOUT** | breakout | UNKNOWN | `strategies/trade_builder.py` |
| **VWAP_ORB** | breakout | UNKNOWN | `strategies/trade_builder.py` |
| **VWAP_MEAN_REVERSION** | mean_reversion | IMPLEMENTATION_BUG_FOUND (Fixed) | `strategies/pro_layer/pro_strategy_engine.py` |
| **MEAN_REVERSION** | mean_reversion | IMPLEMENTATION_VERIFIED | `core/mean_reversion_candidate_generator.py` |
| **VOL_EXPANSION_NAIVE** | volatility_expansion | IMPLEMENTATION_BUG_FOUND (Fixed) | `strategies/pro_layer/pro_strategy_engine.py` |
| **VOLATILITY_SCALED_TREND** | trend | UNKNOWN | `strategies/trade_builder.py` |
| **OPTIONS_FLOW_ALIGNMENT** | options_flow | UNKNOWN | `strategies/pro_layer/pro_strategy_engine.py` |
| **LIQUIDITY_IMBALANCE** | order_flow | IMPLEMENTATION_BUG_FOUND (Fixed) | `strategies/pro_layer/pro_strategy_engine.py` |
| **INTRADAY_DIRECTIONAL** | trend | UNKNOWN | `strategies/trade_builder.py` |
| **HTF_OPENING_DRIVE_CONT** | htf_continuation | UNKNOWN | `strategies/trade_builder.py` |
| **HTF_15M_TREND_CONT** | htf_continuation | UNKNOWN | `strategies/trade_builder.py` |
| **HTF_15M_VWAP_PULLBACK** | pullback | UNKNOWN | `strategies/trade_builder.py` |
| **HTF_FAILED_BREAKOUT_REVERSAL** | reversal | UNKNOWN | `strategies/trade_builder.py` |
| **HTF_PDH_PDL_HOLD** | range | UNKNOWN | `strategies/trade_builder.py` |

## Notes
The `VWAP_MEAN_REVERSION`, `VOL_EXPANSION_NAIVE`, and `LIQUIDITY_IMBALANCE` strategies were discovered to have intent gating and NaN validation bugs. These have been patched on `main`. We will verify their execution logic in Phase 2.
