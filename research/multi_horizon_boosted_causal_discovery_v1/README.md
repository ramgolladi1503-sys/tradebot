# Multi-Horizon Boosted Causal Discovery V1

Research-only discovery of a higher-occurrence NIFTY buy-option mechanism.

A fixed shallow regularized model uses causal option and surface features to choose a confidence state and one exact exit horizon among 5, 10, 15 and 20 minutes. Horizon and confidence are selected on a chronological calibration slice inside each outer training period, then frozen before the next WFA fold.

Governance:

- one representative CE and PE per minute selected without outcomes;
- exact next-minute same-contract open entry;
- exact same-contract close at the selected horizon;
- 1% total premium-return friction is the training objective;
- fixed HistGradientBoostingRegressor configuration;
- four expanding outer WFA folds;
- full nested shuffled-label negative control;
- at least 100 OOF signals across 70 sessions;
- latest 25% holdout opened only after aggregate OOF passage;
- opposite-wing, five-minute-delay and non-model baseline controls;
- no post-outcome model, horizon, confidence or gate changes;
- no broker, paper, live or production action.
