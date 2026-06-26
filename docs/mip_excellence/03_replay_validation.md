# Phase 18: Replay Validation Report

## Execution Summary
The `IntelligenceReplayEngine` (`core/intelligence/replay/intelligence_replay.py`) was audited to prove its operational boundaries against TradeBot's historic tick data stores.

## Measurement Truths Verified
1. **No Data Invention**: If `valid_samples` (historical ticks that align temporally with intelligence timestamps) is less than `self.min_sample_size` (30), the engine definitively aborts and returns `INSUFFICIENT_EVIDENCE`.
2. **Explicit Risk Vectors**: The output signature strictly measures:
   - `forward_vol_multiplier_mean` (Volatility Spikes)
   - `iv_expansion_mean` (IV Expansion)
   - `liquidity_change_mean` (Liquidity Changes)
   - `spread_widening_bps` (Spread Widening)
   - `candidate_rejection_correlation` (Candidate Rejection)
   - `drawdown_correlation` (Drawdown)
   - `strategy_degradation_correlation` (Strategy Degradation)

## Result
Replay framework enforces operational honesty. If historic data is missing, the calibration drops gracefully without throwing exceptions or hallucinating a synthetic confidence score.
