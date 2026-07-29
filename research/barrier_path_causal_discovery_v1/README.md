# Barrier-Path Causal Discovery V1

Research-only discovery aligned to actual option scalping economics rather than a fixed candle-close label.

Frozen execution proxy:

- exact next-minute same-contract open entry;
- +10% premium target;
- -5% premium stop;
- ten-minute maximum hold;
- exact one-minute OHLC path;
- stop-first when target and stop touch in the same candle;
- 0.1% base and 1.0% stress total premium-return friction.

Discovery governance:

- one causally selected representative CE and PE per minute;
- depth-three interpretable trees;
- broad leaves checked across three chronological inner blocks;
- four expanding WFA folds;
- fixed shuffled-label negative control;
- at least 100 OOF signals across 70 sessions;
- latest 25% chronological holdout opened only after aggregate OOF passage;
- opposite-wing and five-minute-delay controls;
- no post-outcome adjustment to target, stop, horizon, model depth, leaves or gates;
- no broker, paper, live or production action.
