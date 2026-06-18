# Strategy Deep-Dive Recommendations

Based on the execution of the full Deep-Dive pipeline across the strategy fleet, here is the official classification and ranking for next-candidate prioritization.

## Priority Rankings

### 1. NEEDS_REGIME_ISOLATION: `ORB_BREAKOUT`
- **Gross Expectancy**: +0.60R
- **Net Expectancy (Overall)**: -0.15R
- **Verdict**: *Cost/Slippage Killed (Globally)*. However, the Regime Isolation Matrix reveals a massive hidden edge. While it bleeds in `TREND_DOWN` (-0.76R) and breaks even in `TREND_UP` (+0.03R), **in the `VOL_EXPANSION` regime, the Net Expectancy post-friction is +0.22R.**
- **Recommendation**: This strategy possesses structural edge. It must be strictly gated to the `VOL_EXPANSION` regime and re-run through the pipeline to confirm if it survives 3x Friction Stress Testing.

### 2. REJECTED: `HTF_OPENING_DRIVE_CONT`
- **Reason**: 0 signals generated under the current mathematical constraints. It is a dead signal in this temporal framework.

### 3. REJECTED: `HTF_15M_TREND_CONT`
- **Reason**: 0 signals generated. Dead signal.

### 4. REJECTED: `HTF_15M_VWAP_PULLBACK`
- **Reason**: 0 signals generated. Dead signal.

### 5. RESEARCH_ONLY: `HTF_PDH_PDL_HOLD`
- **Reason**: Only produced 3 total trades over the historical slice, resulting in massive negative edge (-5.78R Net). Too rare and too fragile to promote.

### 6. RESEARCH_ONLY: `HTF_FAILED_BREAKOUT_REVERSAL`
- **Reason**: Produced exactly 1 trade. While it technically reached its target, the sample size renders it statistically invalid. Needs broader testing, but currently unpromotable.

## Conclusion
The rigor of the pipeline successfully killed 5 out of 6 candidate variants, exactly as it should. The only strategy exhibiting true structural edge that survives friction is `ORB_BREAKOUT`, provided it is strictly amputated from trend regimes and gated purely to Volatility Expansion. 
