mode: RESEARCH_ONLY_OPTION_CANDLE_CAMPAIGN
candidate_id: compression_breakout_option_campaign_v1
decision: IMPLEMENTATION_READY_RUNTIME_DATA_REQUIRED
reason: The campaign calls the canonical Compression Breakout strategy owner, emits a pre-outcome signal ledger, and connects selected signals to conservative CE/PE candle economics without reading sealed holdout option outcomes; campaign behaviour still requires Mac-local corpus execution before any performance claim.
timestamp: 2026-07-26T19:05:00+05:30
research_only: true
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
outcomes_read: false
pnl_read: false
holdout_outcomes_read: false
source: strategies/movement/compression_breakout.py; research/option_e2e_recertification_v4/compression_breakout_option_campaign_v1/; research/option_e2e_recertification_v4/option_candle_backtest_v1/

# Compression Breakout Option Campaign V1

## Agent Work Contract

Implement the first strategy-specific historical CE/PE campaign after the
generic candle engine became available. Use `compression_breakout_v1`, the
highest-priority strategy with a concrete canonical candidate-generator owner.
Do not use the prior placeholder historical audit or replay scripts.

## Scope Guard

Changed scope is limited to:

- `research/option_e2e_recertification_v4/compression_breakout_option_campaign_v1/`
- `scripts/run_compression_breakout_option_campaign.py`
- this review

No production strategy formula, profile threshold, broker, order, risk, feed,
candidate-pool runtime, dashboard, paper or live configuration is changed.

## Grill Me Review

The campaign imports and calls
`generate_compression_breakout_candidates`; it does not reproduce the strategy
formula. Context features are constructed by session. The breakout bar is
separated from the pre-breakout 15-bar resistance, support and range-width
window. ATR values are taken from the preceding completed bar.

The signal ledger contains no option outcomes or P&L. It records the parameter
hash, raw strategy score, confidence score, strategy-only rank score, feature
cutoff and earliest-entry time. Execution-quality ownership remains unset.

Synthetic market fixtures are not accepted as campaign-performance proof by the
publication gate. They were removed rather than relabelled. Runtime campaign
acceptance therefore remains explicitly dependent on the Mac-local historical
corpus and its emitted hash-bound evidence.

## Hermes Review

The implementation follows the intended owner sequence:

```text
underlying completed bars
→ canonical pre-outcome context
→ movement regime
→ Compression Breakout candidate
→ bullish CE / bearish PE research signal
→ deterministic contract selection
→ conservative option-candle economics
```

Historical candle rank is explicitly strategy-only. Quote freshness, spread,
depth and exact fill authority remain outside this lane.

## GSD Review

The campaign adds a one-command runner that can stop after signal generation or
continue through development/validation option candles. It emits compact
hash-bound JSON/CSV evidence, a chronological split manifest, cost sensitivity,
direction-flip control and delayed-entry control.

## QA / Safety Review

The implementation contains fail-closed guards for:

- duplicate underlying timestamps;
- invalid OHLC geometry;
- missing pre-signal warmup;
- zero-volume VWAP proxy disclosure;
- optional rejection of VWAP proxy sessions;
- duplicate signal identities;
- chronological split overlap;
- supplied holdout option data;
- duplicate option contract timestamps through the existing candle engine.

These guards are code-reviewed here but are not presented as market evidence.
Generic option fill mechanics and the canonical strategy owner retain their
existing independent test coverage. Campaign integration must be proven by the
Mac-local runtime evidence before publication as a strategy result.

Safety remains:

- `research_only=true`
- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
- `outcomes_read=false`
- `pnl_read=false`
- `holdout_outcomes_read=false`
- `executable_option_pnl_certified=false`

## Acceptance Proof

Implementation publication requires:

- existing canonical Compression Breakout strategy tests;
- existing option-candle backtest tests;
- existing option-E2E tests;
- Code Excellence;
- Agent Review Evidence Gate;
- CodeQL;
- strategy registry verification;
- repository CI.

Campaign-result publication additionally requires a successful Mac-local run,
portable artifact hashes, session counts, signal counts, rejection reasons,
contract-selection coverage, cost sensitivity and negative-control evidence.

## Runtime Proof Required After Merge

Run the campaign on the Mac-local historical underlying, session contract
catalogue and option OHLCV corpus. Development and validation runs must use
separate date-bound option inputs. Do not supply or open holdout option outcomes
until the campaign contract and negative controls are frozen.

## What This PR Does Not Prove

This implementation does not prove that Compression Breakout is profitable,
that a 60% win rate exists, that option candles equal bid/ask execution, or that
paper/live trading is ready. It establishes a research path to answer those
questions with local data.

## Human Approval

Human approval is not required for this read-only research implementation.
Human action is required only when the Mac-local corpus must be supplied or
executed and later before any holdout, paper or live promotion.
