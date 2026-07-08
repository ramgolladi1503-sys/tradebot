# MEAN_REVERSION_EXTENSION V2 - FAILED BASELINE

## Classification
**MRE_V2_PARAMETER_SPACE_FAILED**

## Phase 4.11B Discovery Grid Summary
- **V2 Configured Grid Size:** 486 Parameter Combinations
- **Train Pass Count:** 0
- **Validation Pass Count:** 0
- **Region Stable Count:** 0
- **Final Holdout Evaluated Count:** 0

## Reason for Failure
Structural failed-breakout mean reversion did not produce positive proxy-option net expectancy under rigorous next-open execution logic and strict option execution cost models. 

The previous V1 grid produced a false-positive train survival rate due to simulator edge-leakage (same-candle execution assumptions and unrealistic cost-target distance modeling). When the V2 architecture properly resampled the 15-minute HTF regime, delayed execution to the explicit *N+1* candle open, and exacted the $1.50 execution cost proxy against the true mathematical target distance, the expectancy collapsed entirely across all 486 configurations.

## Cost & PNL Model Verification
- **Cost Model Mode:** `PROXY_OPTION`
- **PNL Model Used for Gate:** `proxy_option_net_pnl`
- **Proxy Option Delta:** `0.50`
- **Proxy Option Execution Cost:** `1.5`
- **Expectancy Field Used for Pass/Fail:** `proxy_option_net_expectancy`

## Best Train Configurations (And Why They Failed)

Even the configurations with the lowest drawdown profiles and the strictest selection filters ultimately succumbed to the structural constraints:

1. **Config A:**
   - `opening_range_minutes`: 30
   - `min_wick_rejection_ratio`: 0.4
   - `htf_period_minutes`: 15
   - `stop_atr`: 1.0
   - `target_rr`: 2.0
   - **Why it failed:** Triggered only 70 trades across 525 days. The profit factor was heavily degraded (0.57) due to gap risks and next-candle slippage, producing a final `proxy_option_net_expectancy` of **-5.78**. Triggered `MINIMUM_DIMENSIONAL_EXPECTANCY_NOT_MET` and `LOW_SAMPLE_SIZE`.

2. **Config B:**
   - `opening_range_minutes`: 60
   - `min_wick_rejection_ratio`: 0.4
   - `htf_period_minutes`: 15
   - `stop_atr`: 0.8
   - `target_rr`: 2.0
   - **Why it failed:** Triggered 75 trades across 525 days. The profit factor dropped to 0.44 due to tighter stop-losses being frequently breached on the `N+1` entry candle itself. Final `proxy_option_net_expectancy` of **-7.02**. Triggered `MINIMUM_DIMENSIONAL_EXPECTANCY_NOT_MET` and `LOW_SAMPLE_SIZE`.

## Status
- **Final Holdout:** Untouched and Protected.
- **Phase 5 WFA:** Permanently blocked. 
- **Governance Note:** MEAN_REVERSION_EXTENSION is non-promotable unless a completely new thesis restarts from Phase 4 validation.
- Strategy V2 remains archived as a mathematical proof of execution leakage in naive structural momentum fading models.
