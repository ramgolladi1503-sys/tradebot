# Reviewer A — Quant Mechanism & Signal Scientist Report

## 1. Mechanism Deconstruction
Sentinel uses a dual-regime architecture:
1. **Regime 1: Range-Reversal (GEAR 1)**
   - Mechanism: Rejection wick at Bollinger Band extreme or VWAP boundary.
   - Hypothesis: Intraday mean reversion from price exhaustion at boundary extremes.
   - Finding: Highly sensitive to parameter selection (`wick_min >= 4.0 pts`). In high-volatility chop, rejection wicks produce false breakouts against sharp second-wave trends.
2. **Regime 2: Opening Range Breakout / Trend (GEAR 2)**
   - Mechanism: Price close exceeding Opening Range (09:15–09:45) high or low.
   - Hypothesis: Institutional opening balance discovery drives directional persistence.
   - Finding: Strong predictive edge in morning expansion (09:45–11:00). Past 12:30 PM, continuation edge decays sharply due to volume evaporation and institutional writer pinning.

## 2. Mathematical Audit of Brownian Energy Diffusion Gate (SPVD)
The formula used in `check_session_energy_gate`:
$$\text{Expected Remaining Variance} = \text{ATR}_{1m} \times \sqrt{\Delta t_{\text{remaining}}}$$
- **Critique**: The formula assumes standard 1D Brownian diffusion ($E[|\Delta X|] \propto \sigma \sqrt{t}$). In financial time series, intraday volatility exhibits a pronounced U-shaped curve (high at open, flat at lunch, moderate at close). Treating $\text{ATR}_{1m}$ as constant across the remaining session overestimates afternoon variance by 20–35%.
- **Recommendation**: Apply session-progress decay weighting to scale $\text{ATR}_{1m}$ dynamically during the 11:30–13:30 lunch dead zone.

## 3. Alpha Source Decomposition
- **Directional Classification**: Strong (Win rate > 65% during 09:45–11:15 AM).
- **Option Execution Efficiency**: Mediocre without runner scaling. On fixed 15-point scalps, bid-ask friction and statutory charges consume 25–40% of gross gains. The introduction of the continuous trailing stop in PR #980 expanded right-tail payoffs, which is where 60% of today's alpha originated.
