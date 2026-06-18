# Strategy Deep-Dive Checklist

This checklist enforces the exact rigorous research path utilized for `HTF_RANGE_EXPANSION`. No strategy may bypass these steps.

## Stage 1: Data Integrity Audit
- [ ] **Timezone Sync**: Confirm underlying data arrays natively align with IST (Asia/Kolkata).
- [ ] **Data Granularity**: Confirm structural evaluations use exact 1-minute aggregation logic internally.

## Stage 2: Lookahead Audit
- [ ] **Leakage Scan**: Confirm structural signals mathematically wait for candle closure.
- [ ] **Execution Shift**: Entry array must fire strictly on the `open` of the candle *after* the signal generated.

## Stage 3: Signal Frequency & Starvation RCA
- [ ] **Raw Setup Count**: Tally raw mathematical trigger occurrences.
- [ ] **Gate Starvation Matrix**: Map how many raw signals are rejected by session, regime, and volatility gates.

## Stage 4: Regime Isolation
- [ ] **Ablation Baseline**: Test the strategy against all regimes to ascertain native edge.
- [ ] **Isolation Matrix**: Classify edge presence exclusively by regime (`TREND_UP`, `TREND_DOWN`, `RANGE`, `CHOP`, `VOL_EXPANSION`).
- [ ] **Amputation**: Surgically sever the strategy from regimes where expectancy is native-negative.

## Stage 5: Cost Model Audit
- [ ] **Cost Subtraction**: Run trades through the absolute worst-case realistic NIFTY STT + Brokerage Option model.
- [ ] **Net Expectancy**: Ensure Expectancy `> 0.15R` post-friction.

## Stage 6: MFE/MAE Forensics
- [ ] **Target Probability**: Chart the percent of trades hitting `0.5R`, `1.0R`, `1.5R`, and `2.0R`.
- [ ] **Noise Matrix**: Ensure the average MAE before direction is mathematically smaller than the structural stop.

## Stage 7: Trade Management Lab
- [ ] **Exit Comparison**: Compare static RR exits against ATR-trailing and End-of-Day limiters.
- [ ] **Time-Decay**: Identify the maximum viable holding duration before Theta/Delta decay kills the momentum edge.

## Stage 8: Proxy Execution Validation
- [ ] **Asset Triangulation**: Test the signal via `FUTURES_PROXY` (Raw Nifty Pts), `ATM_OPTION_PROXY` (0.50 Delta), and `ITM_OPTION_PROXY` (0.75 Delta).

## Stage 9: Stress Testing
- [ ] **Friction Elasticity**: Multiply dynamic spread models up to `3.00x`. Ensure edge survives catastrophic slippage width.

## Stage 10: Distribution Analysis
- [ ] **Temporal Stability**: Verify the positive gross edge holds across Q1, Q2, Q3, and Q4 individually. 

## Stage 11: Real Paper Readiness Verdict
- [ ] Output `READY_FOR_REAL_PAPER` if the strategy mathematically survives all previous checks.

## Stage 12: Real-Paper Daemon & Safety Audit
- [ ] Deploy strategy into the decoupled Zero-Order Passive Monitor.
- [ ] Capture L1 Bid/Ask spread live proofs.
