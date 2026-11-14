# Simple-strategy baseline campaign V1 — frozen, falsification-first

Status: **RESEARCH SPEC ONLY — NO STRATEGY CERTIFIED**. This change does not run on local historical data, call brokers, modify runtime, or grant trading authority.

## Why this campaign

Do not interpret failure of one MACD configuration or one ORB implementation as rejection of all trend following. Equally, do not interpret published crossover backtests as evidence for Indian index-option buying. Separate three failure classes: **signal absent**, **implementation invalid**, **signal present but options execution uneconomic**.

Existing repo evidence to preserve and NOT pool as comparable trials:
- `docs/research/strategy_backtesting/opening_range_breakout_validation.md`: the original 60-session candle backtest was invalidated by cross-session exits. A corrected run reported +0.403 underlying proxy bps/trade at 2 bps assumptions and turned negative at 5 bps; an ATR-derived field was incorrectly called volume. Its strict option-replay path lacked contract metadata. This is neither an executable option return nor a valid universal rejection of ORB.
- `docs/research/strategy_research_index.md`: describes `ORB_BREAKOUT` as rejected and `HTF_RANGE_EXPANSION` as ready for observation. These refer to their own contracts, not this baseline experiment.
- `docs/research/strategy_research_playbook.md`: regime-based amputation must be treated as model selection; selecting a profitable subset using all the data and then declaring that subset validated is leakage.

## Frozen questions (before inspecting results)

H1: on 5-minute NIFTY underlying bars, an end-of-bar EMA(9)/EMA(21) cross produces positive subsequent directional returns under a fixed, non-overlapping entry/exit policy.

H2: an end-of-bar breakout above/below the opening 15-minute range produces positive subsequent directional returns under the same policy, without pretending ATR is traded volume.

H3: a 20-bar, 2-population-standard-deviation Bollinger touch followed by reentry predicts price movement towards its rolling mean. Reentry, not an isolated band touch, triggers.

H4: price deviation of at least 0.4% from **genuine volume-weighted** session VWAP followed by movement back toward VWAP predicts directional returns. If only zero-volume index bars or proxy VWAP are available, H4 is `DATA_BLOCKED`, **not** zero-edge and not a synthetic-data PASS. Genuine representative volume and valid instrument mapping must be documented separately before an index-level VWAP claim.

These are deliberately simple **candidate definitions**, not recommended settings. No parameter search is authorized under V1. Only BUY_CALL/BUY_PUT direction hypotheses; never option selling. Options execution is a separate later study.

## Required data manifest before any result

- Dataset path, canonical source, first/last date, bar timezone, session calendar, adjustment semantics, 1/5-minute granularity, OHLC validation, data hash, missing/duplicate minutes and timestamps, constituent/instrument mapping where relevant.
- Freeze the exact development/validation/confirmation/untouched-holdout calendar boundaries **before opening outcomes**. Use chronological contiguous partitions, no randomly sampled candles; use entire sessions and purge boundary-crossing labels.
- Record whether bars are timestamped at **start or end**; normalize to an end-of-bar timestamp, available only after bar completion. An example 09:15–09:20 candle only becomes known at 09:20 IST.
- Freeze separate data-quality reports for each hypothesis. Zero volume is allowed for price-only H1–H3; it blocks genuine VWAP H4. Reject any attempt to substitute typical price or ATR and still call it VWAP/volume.

## Fixed signal/execution contract

- Evaluate only at completed 5-minute closes after enough same-session warmup. No outcome or next-bar field can enter features.
- Opening range: first three **completed** bars (09:15–09:30 IST). Earliest ORB evaluation is at the first subsequent completed bar, and trade enters no earlier than the following bar's open. Do not use intrabar high to infer a fill at a price available before the bar closes.
- EMA 9/21: compare today's completed EMA pair against the previous completed pair within the session. No lookback through future rows.
- Bollinger: completed prior bar outside a band; just-completed bar back inside the same-side band. The current bar's rolling stats may be used only after its close.
- VWAP: cumulative sum(typical_price × genuine positive representative volume) / cumulative genuine volume, using only bars completed through the decision. Any missing/zero-volume or mismapped index series blocks H4 instead of silent fallback.
- Direction: upside EMA/ORB breakout => positive underlying direction (later BUY_CALL hypothesis); downside => negative (later BUY_PUT); upper Bollinger / above-VWAP reversal => negative; lower => positive.
- One active hypothesis per strategy per session; prevent repeat signals while a prior proxy trade is open. Never let an exit jump across a sampled day.
- Signal cutoff: 14:35 IST for 30-minute max observation + next-bar entry and conservative end-of-day handling. No entry in close/liquidity-restricted periods. Options order permission remains **off**.
- For underlying diagnostic, next completed 5-minute bar **open** is the earliest proxy entry; primary exit is three completed 5-minute bars after entry at bar close. State explicitly that bar-close exit and bps assumptions are **non-executable proxies**, especially for option buying. Also record 1-, 3-, 6-bar forward returns purely as prediction diagnostics, with overlapping labels disclosed.
- Require a zero-latency next-open oracle comparison and a deliberately delayed entry negative control. Log identical timestamp/order reconstruction under replay.

## Analysis: keep the tests independent of storytelling

1. Produce a per-session signal and no-signal ledger, including timestamp, exact frozen parameters, source-bar IDs, signal, future-label horizon, entry/exit bars, missing-data reason and no-cross-session assertion.
2. Before simulating exits, compare conditional next-bar/three-bar/six-bar directional returns with same-time/day block-permuted controls. Report raw and multiplicity-adjusted uncertainty across **all four** family hypotheses, not only apparent winners. Session-block bootstrap; never treat overlapping bars as IID observations.
3. Report gross underlying diagnostic bps, illustrative 2/5/10-bps *underlying proxy* scenarios, trade count, session coverage, drawdown and year-by-year stability. These cost scenarios are not evidence about executable option costs.
4. Segment by **causally measured** pre-entry trend/volatility. Show unconditional aggregate first. Any regime exclusion chosen after looking at outcomes becomes a **new V2 hypothesis**, must use a new untouched period, and counts toward research multiplicity.
5. Compare signal to no-signal/time-matched and direction-inverted placebos. Require event timestamps, independent arithmetic spot checks, and two matching hash-pinned replay runs.
6. Evaluate later chronological blocks once. Never reuse a consumed holdout by changing timeframe, indicator settings or exit duration after seeing its result. Record every variant and stopped trial.
7. Only after underlying evidence survives: join point-in-time option contract, contemporaneous quote bid/ask, quote age, expiry/strike and full actual fees/STT, then evaluate **buy-only** next-tradable-quote entries, feasible exit fills, latency and liquidity stress. No validated options quote history = `OPTIONS_ECONOMICS_UNDETERMINED`.

## Predeclared stop decisions

- `DATA_BLOCKED`: failed data quality, missing representative volume for genuine VWAP, or missing timestamp convention.
- `INVALID_METHOD`: timestamp leakage, sampled-session cross-over exits, overlap masquerading as independent N, hidden parameter changes, failed replay/oracle, or contaminated holdout.
- `UNDERLYING_NOT_SUPPORTED`: no robust directional evidence against time-matched controls after family-wide multiplicity correction across chronological validation.
- `UNDERLYING_RESEARCH_SIGNAL`: reproducible underlying prediction under frozen rules; **not** an option strategy.
- `OPTIONS_ECONOMICS_UNDETERMINED`: no synchronized option bid/ask/contract metadata; do not substitute index bps.
- `OPTIONS_RESEARCH_SUPPORTED`: only with independent option-replay evidence and all existing repo governance gates, never automatic live promotion.

**No experiment is permitted to be labeled a profitable strategy on the basis of this document.**

## Execution boundaries and handoff

This PR is intentionally documentation-only. The real local historical corpus described in prior research is **not present in this connected GitHub tool environment**, so no genuine sample counts, PnL, PASS, or holdout results are reported. This repo change does not modify protected datasets or the currently running PAPER process; does not stop watchdogs; does not invoke strategy discovery loops; and must not trigger live or paper orders.

Implementation follow-up, in isolated worktree after data access is established: write the four pure signal generators and unit tests for timestamp shift, missing-data refusal, same-session execution, one-position concurrency, and output determinism. First run **DEV only**. Have a separate auditor verify before chronologically unlocking validation; keep the existing TradeBot mandatory governance gates authoritative.
