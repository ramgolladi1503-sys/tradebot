# Pairs Arbitrage Profitability Certification Blocker V1

## Status

`INSUFFICIENT_EVIDENCE_FOR_PROFITABILITY_CERTIFICATION`

Research only. Runtime authority remains `NONE`. Broker actions are not permitted.

## Frozen identity

- Strategy ID: `pairs_arbitrage`
- Frozen implementation source commit: `561041b2e11f03283ebca3fd5eb70e6ef6fc1d6d`
- Module: `strategies.pairs_arbitrage`
- Callable: `generate_signal`
- Synchronized dataset SHA-256: `66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32`
- Dataset reproduction: byte-for-byte locally reproduced from the three frozen underlying datasets using `EXACT_INTERSECTION` and `CURRENT_OR_PRIOR_ONLY` feature timing.

## Finding

The frozen implementation provides entry-signal semantics only. It emits `BUY_SPREAD` or `SELL_SPREAD` after causal checks for aligned history, freshness, cross-asset health, Kalman hedge ratio, spread z-score, ADF stationarity, and OU half-life.

Neither the frozen implementation nor the registered `StrategySpec` defines a complete exit/economic realization contract. There is no authoritative stop, target, spread mean-reversion exit threshold, maximum holding period, end-of-session liquidation rule, or other terminal position-closing rule.

The registry declares `LONG_SPREAD` / `SHORT_SPREAD` direction capabilities and required evidence keys, but does not supply exit semantics.

## Consequence

A profitability backtest cannot be run against the frozen strategy without inventing at least one material strategy parameter or execution semantic. Any such invented exit rule would create a new strategy passport identity under the frozen-generation rule.

Therefore the current frozen `pairs_arbitrage` strategy is **not eligible for profitability/edge certification** despite having sufficient synchronized price evidence for entry-signal reconstruction.

Allowed research work on the frozen identity is limited to entry-signal diagnostics or predictive studies that are explicitly labeled non-profitability evidence. Such studies must not be represented as structural edge certification.

## Required closure

To create a certifiable successor passport, define and freeze an explicit exit/economic contract before observing certification holdout results. At minimum it must specify:

- spread-entry semantics;
- spread-exit semantics;
- maximum holding period / session boundary behavior;
- two-leg sizing/notional convention;
- transaction-cost and slippage model for both legs;
- overlapping-signal / concurrent-position policy;
- failure behavior when hedge ratio, stationarity, freshness, or health truth deteriorates after entry.

After those semantics are frozen, the successor identity may enter causal replay, chronological OOS/walk-forward validation, robustness, negative-control, cost-stress, regime-stability, and sufficient-trade-count testing.

## Verdict

`PAIRS_ARBITRAGE_PROFITABILITY_CERTIFICATION_BLOCKED_MISSING_EXIT_CONTRACT`

`runtime_authority = NONE`
