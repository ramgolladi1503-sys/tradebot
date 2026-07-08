# MEAN_REVERSION_EXTENSION V2 Design Note

## Context
MEAN_REVERSION_EXTENSION V1 (MRE V1) completely failed to survive Out-Of-Sample validation when factoring in real proxy option execution costs (8.5 underlying index point proxy for ~1.5 point option slippage constraint). 

MRE V2 will **not** simply be a retuning of V1 parameters. It requires structural paradigm shifts to increase trade selection quality and survivability in harsh transaction-cost environments. 

## Structural Upgrades

The following filters and contextual requirements must be integrated into V2:

### 1. Failed Breakout / Range Reclaim Context
- V1 simply triggered blindly when the distance from the mean crossed a raw ATR extension threshold.
- V2 will look for specific structure: a local breakout that fails, followed by a sharp reversion back inside the established range. This creates trapped liquidity to fuel the reversion momentum.

### 2. Higher-Timeframe (HTF) Regime Filter
- Mean reversion trades exhibit significantly higher win rates when aligned with the larger structural trend or when the higher timeframe is in a confirmed sideways channel.
- V2 must query a higher-timeframe baseline (e.g., 15m or 1H) and prohibit counter-HTF momentum trades unless specific exhaustion criteria are met.

### 3. Trend Exhaustion Confirmation
- V2 will require evidence that the extending move has exhausted itself (e.g., volume climax, consecutive shrinking candles, or long wicks rejecting the extension boundary) before entry is allowed.

### 4. Time-of-Day Specialization
- Mean reversion properties change drastically between the opening hour (high volatility, trend-setting), mid-day (chop/reversion), and closing hour (trend continuation/liquidation).
- V2 must apply time-of-day contextual gates to prohibit entries during structurally unfavorable windows (e.g., first 45 minutes of the session).

### 5. Option Quote / Liquidity Confirmation (When Available)
- V2 must eventually respect option liquidity depth. Execution should be blocked if the theoretical bid/ask spread on the proxy option breaches maximum allowable thresholds.

### 6. No Fallback Execution
- Strict continuation of the V1 rule: If the setup is absent, emit zero trades. No synthetic data, no "happy-path" default costs. The ledger must remain 100% faithful to the underlying data limitations.
