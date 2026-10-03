# Deep-Dive Timeline: HTF_RANGE_EXPANSION

This is a historical narrative about `HTF_RANGE_EXPANSION`; it is not a current readiness authority.

> **Evidence and selection caveat:** This file is not an authenticated verification artifact. Its regime restriction was selected after reviewing an ablation matrix, so `VOL_EXPANSION`-only is an outcome-informed, exposed hypothesis. Preserve the all-regime parent, negative results, all tried subsets, and the selection denominator. Same-sample filtered metrics do not establish independent confirmation, untouched OOS, controlled-discovery readiness, or paper/live eligibility. Obtain original sources and exact artifacts before relying on quantitative claims below.

## 1. Initial Failure & Timezone Bug Discovery
- **Status**: The strategy originally produced erratic, negative-expectancy results.
- **Intervention**: A fundamental data ingestion bug was uncovered. The pandas `tz_localize` layer was misaligned between UTC and `Asia/Kolkata`, causing the backtest to incorrectly evaluate session times.
- **Resolution**: Timezone casting was explicitly standardized across all pipelines.

## 2. Lookahead Leakage Discovery
- **Status**: Upon fixing the timezone, the strategy miraculously displayed ~95% win rates.
- **Intervention**: The `Leakage Audit` was deployed. We discovered that the `15m` structural indicators were leaking into the `1m` entry candles prior to the 15m period closing.
- **Resolution**: `timestamp_closed` strict gating was enforced. Signals were explicitly shifted to fire on the *open* of the *following* 1m candle. Win-rates normalized to ~55%.

## 3. Higher-Timeframe (HTF) Pivot
- **Status**: The strategy was previously hunting 1m micro-breakouts. Edge was suffocated by slippage noise.
- **Intervention**: We halted 1m signals and pivoted to `15m` structure mapped down to `1m` execution granularity. The noise-to-signal ratio improved dramatically.

## 4. Regime Isolation & Starvation RCA
- **Status**: The new HTF engine was starving, producing only 4 signals.
- **Intervention (as reported in this narrative)**: An ablation matrix was inspected after producing outcomes; its source artifacts, trial denominator, and independent analysis are not attached here.
- **Disposition**: The resulting `VOL_EXPANSION`-only restriction is a new exposed child hypothesis. The all-regime parent and every inspected negative regime result remain part of the search history; the same outcomes cannot independently confirm the child.

## 5. Proxy Execution & Cost Model Audit
- **Status**: Was the edge an artifact of treating Options like Futures?
- **Intervention**: Tested identical signals against `FUTURES_PROXY`, `ATM_OPTION_PROXY` (0.50 delta), and `ITM_OPTION_PROXY` (0.75 delta), while aggressively applying the `Indian derivatives cost model` (STT strictly on sell premium).
- **Resolution**: The core +0.47R edge survived the mathematical decay of option-buy friction.

## 6. Stress Testing & Reconciliation
- **Status**: A prior stress test showed the strategy failed at 3x friction.
- **Intervention**: Reconciled the mathematical contradiction. The prior test included dead regimes. When properly gated to `VOL_EXPANSION` only, the strategy effortlessly absorbed `> 3.00x` friction.

## 7. Real Paper Daemon & Safety Audit
- **Status**: Ready for real markets.
- **Intervention**: Built `run_htf_real_paper_monitor.py`. A completely decoupled, zero-order daemon.
- **Resolution**: Proved statically via AST that no live orders could escape. Transitioned the strategy into final observational phase.

*This exact sequence must be replicated for all future candidates.*
