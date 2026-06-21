# Strategy Truth Specs

## TradeBuilder Legacy Strategies

### ORB_BREAKOUT
- **Signal Domain**: Intraday Breakout
- **Required Inputs**: `ltp`, `orb_high`, `orb_low`
- **Direction Rules**: Bullish if `ltp > orb_high`, Bearish if `ltp < orb_low`.
- **CE/PE Mapping**: CE for Bullish, PE for Bearish.
- **Entry Trigger**: Price crosses the opening range.
- **Invalidation**: Price fails to hold the range breakout.
- **Regime Requirement**: TREND, EXPANSION
- **Freshness Requirement**: Standard 6.0s freshness.
- **Fallback/Advisory Behavior**: Soft-reject drops score, does not execute.
- **Executable Eligibility**: Yes, but requires strict verification.

### VWAP_ORB
- **Signal Domain**: Intraday Trend
- **Required Inputs**: `ltp`, `vwap`, `orb_high`, `orb_low`
- **Direction Rules**: Bullish if `ltp > vwap` and `ltp > orb_high`. Bearish if `ltp < vwap` and `ltp < orb_low`.
- **CE/PE Mapping**: CE for Bullish, PE for Bearish.
- **Entry Trigger**: Dual confirmation of VWAP + ORB.
- **Regime Requirement**: TREND, EXPANSION

### VOLATILITY_SCALED_TREND
- **Signal Domain**: High-TF Trend
- **Required Inputs**: `atr`, `ltp_change`

### INTRADAY_DIRECTIONAL
- **Signal Domain**: Trend Continuation
- **Required Inputs**: `ltp`, `ema`

### HTF_OPENING_DRIVE_CONT
- **Signal Domain**: High-Timeframe Momentum
- **Required Inputs**: `df_15m`, `df_1m`, `od_high`, `od_low`
- **Direction Rules**: Bullish if `close > od_high`. Bearish if `close < od_low`.
- **CE/PE Mapping**: `target > entry` (Bullish/CE) or `target < entry` (Bearish/PE).
- **Regime Requirement**: VOL_EXPANSION or matched 15m/30m trends.
- **Invalidation**: Price doesn't close outside opening drive range.
- **Fallback Behavior**: Bypasses TradeBuilder Phase-2 logic entirely (Pipeline Gap).
- **Missing Data**: NaN fails closed (REJECT). Missing data raises unhandled exceptions.

### HTF_15M_TREND_CONT
- **Signal Domain**: High-Timeframe Trend Continuation
- **Required Inputs**: `df_15m`, `df_1m`, `trend_15m`, `trend_30m`
- **Direction Rules**: Bullish if `close > prev_high` and candle is bullish. Bearish if `close < prev_low` and candle is bearish.
- **CE/PE Mapping**: `target > entry` (CE), `target < entry` (PE).
- **Regime Requirement**: Must match 15m and 30m trend direction.
- **Fallback Behavior**: Bypasses Phase-2 logic entirely (Pipeline Gap).

### HTF_15M_VWAP_PULLBACK
- **Signal Domain**: High-Timeframe VWAP Pullback
- **Required Inputs**: `df_15m`, `vwap`, `trend_15m`, `trend_30m`
- **Direction Rules**: Bullish if low pulls back to VWAP and closes above.
- **CE/PE Mapping**: `target > entry` (CE), `target < entry` (PE).
- **Regime Requirement**: Must match 15m and 30m trend direction.
- **Fallback Behavior**: Bypasses Phase-2 logic entirely (Pipeline Gap).

### HTF_FAILED_BREAKOUT_REVERSAL
- **Signal Domain**: Reversal
- **Required Inputs**: `df_15m`, `od_high`, `od_low`
- **Direction Rules**: Bearish if previous high > od_high but closes < od_high.
- **Regime Requirement**: RANGE, CHOP.
- **Fallback Behavior**: Bypasses Phase-2 logic entirely (Pipeline Gap).

### HTF_PDH_PDL_HOLD
- **Signal Domain**: Range Expansion
- **Required Inputs**: `pdh`, `pdl`, `df_15m`
- **Direction Rules**: Bullish if closes above PDH. Bearish if closes below PDL.
- **Regime Requirement**: Must hold structure across previous candles.
- **Fallback Behavior**: Bypasses Phase-2 logic entirely (Pipeline Gap).


## Pro Engine Strategies

### VOL_EXPANSION_NAIVE (VolatilityExpansionStrategy)
- **Signal Domain**: Directional Breakout
- **Required Inputs**: `atr`, `ltp_change_window`, `vol_z`
- **Direction Rules**: Follows `ltp_change`.
- **CE/PE Mapping**: CE for Up, PE for Down.
- **Entry Trigger**: `move_atr >= 0.75` or `vol_z >= 1.0`
- **Regime Requirement**: TREND, VOLATILE, EVENT, EXPIRY
- **Freshness Requirement**: Max age 6.0s, max spread 2%.

### LIQUIDITY_IMBALANCE
- **Signal Domain**: Order Flow
- **Required Inputs**: `bid_qty`, `ask_qty`, `spread_pct`
- **Direction Rules**: Bullish if `bid_qty > ask_qty`, Bearish otherwise.
- **CE/PE Mapping**: CE for Up, PE for Down.
- **Entry Trigger**: `abs(imbalance) >= 0.35`
- **Regime Requirement**: TREND, VOLATILE, EVENT, EXPIRY, NEUTRAL

### VWAP_MEAN_REVERSION
- **Signal Domain**: Mean Reversion
- **Required Inputs**: `ltp`, `vwap`, `rsi_mom`
- **Direction Rules**: Reverts to VWAP. Bearish if extended above VWAP.
- **CE/PE Mapping**: CE for Up, PE for Down.
- **Entry Trigger**: `abs(dev) >= 0.0045`. RSI confirmation required.
- **Regime Requirement**: RANGE, NEUTRAL

### OPTIONS_FLOW_ALIGNMENT
- **Signal Domain**: Options Flow
- **Required Inputs**: `call_oi_delta`, `put_oi_delta`, `iv_change`, `ltp_change`
- **Direction Rules**: Aligned with OI pressure.
- **CE/PE Mapping**: CE for Up, PE for Down.
- **Entry Trigger**: Price and OI pressure match.
- **Regime Requirement**: TREND, VOLATILE, EVENT, EXPIRY, NEUTRAL

## Core Candidate Generators

### MEAN_REVERSION
- **Signal Domain**: Mean Reversion
- **Required Inputs**: `ltp`, `vwap`, `oscillator`
- **Direction Rules**: Reverts to VWAP.
- **CE/PE Mapping**: CE for Up, PE for Down.
- **Entry Trigger**: Deviation > threshold.
- **Regime Requirement**: RANGE, SIDEWAYS, LOW_VOL
