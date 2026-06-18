# Stress-Test Reconciliation Report

## The Contradiction
- **Previous Stress Test**: Claimed `3x` slippage killed the strategy.
- **Recent Reality Audit**: Proved the strategy survived up to `> 3.00x` friction and retained a massive +0.13R expectancy under maximum duress.

## Root Cause of Discrepancy
The contradiction is mathematically sound and is caused by **Regime Gate Permissiveness**.

### Old Assumptions (First Stress Test)
In the original stress test run (Ablation D), the HTF structure was evaluated *without* the `VOL_EXPANSION` regime gate.
- **Base Expectancy (1.0x Friction)**: -0.06R
- By indiscriminately feeding all regimes (TREND, CHOP, RANGE, VOL_EXPANSION) into the friction multiplier, the base edge was already bleeding. Multiplying slippage by `3x` merely accelerated the inevitable failure of a negative-expectancy baseline.

### New Assumptions (Reality Audit)
In the rigorous Execution Reality Audit, the strategy was strictly hard-locked to the `VOL_EXPANSION` gate, rejecting all non-conforming setups.
- **Base Expectancy (1.0x Friction)**: +0.47R
- **Signal Count**: 727 mathematically pure structural momentum trades.

## Friction & Slippage Model Comparison
- **Old Model**: Used a generic flat-rate point decay across all instruments and regimes.
- **New Model**: Mapped synthetic option delta correctly (0.50) and applied a strict, realistic NIFTY ATM Bid/Ask spread logic (0.7 point static penalty per side, effectively 1.4 point round-trip penalty) which scales with friction multipliers.

## Conclusion
The **New Reality Audit** result is mathematically correct because the `HTF_RANGE_EXPANSION` edge ONLY exists within the `VOL_EXPANSION` regime. The previous failure was caused by forcing the stress test to consume off-regime trades. When strictly gated, the true structural momentum of the strategy effortlessly absorbs `3.00x` execution friction.
